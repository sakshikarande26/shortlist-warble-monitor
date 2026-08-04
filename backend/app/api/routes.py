"""Read-only dashboard API. Reads from the existing DB + detector only —
never calls the Warble API, never touches collector/detector/alert logic.
"""

import statistics
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AlertSummary,
    BreakoutLogEntry,
    BreakoutLogResponse,
    CreatorContext,
    CreatorDetailResponse,
    CreatorPostSummary,
    CreatorRosterEntry,
    CreatorRosterPost,
    CreatorStats,
    CreatorsResponse,
    EvidenceDetail,
    HomePost,
    HomeResponse,
    NotablePost,
    PostDetail,
    SystemStatus,
    TrajectoryPoint,
)
from app.db.base import get_session
from app.db.models import Alert, Creator, Post, Sample
from app.detector.evaluate import evaluate_post
from app.detector.momentum import IntervalSignal, SamplePoint, _dedupe_samples, compute_interval_signals
from app.detector.states import PostState, run_state_machine

router = APIRouter()

SPARKLINE_POINTS = 12

# --- Canonical status vocabulary (presentation-layer, not the detector).
# Exactly one function computes this, and every endpoint calls it — the
# whole point is that the headline, section a post lands in, its own card
# badge, its detail page, and the right-hand panel can never disagree,
# because they're never each computing their own opinion of "what state is
# this post in."
_TAKING_OFF = "Taking off"
_WORTH_WATCHING = "Worth watching"
_STEADY = "Steady"
_UNAVAILABLE = "Unavailable"

# A post has to meaningfully beat the creator's own norm to count as
# "worth watching," not just edge past 1.0x on noise — this is what lets
# Home (and every other surface) say so honestly when nothing is actually
# moving instead of padding the list with flat posts.
_MOVER_RATIO_THRESHOLD = 1.15
_SECTION_CAP = 5  # triage list, not a leaderboard
_MIN_BASELINE_POINTS = 2  # fewer than this and there's no real "typical" to compare against
_BASELINE_NEIGHBORS = 5  # nearest-by-age points from the creator's other posts used for the baseline
_MIN_BASELINE_VELOCITY = 1.0  # views/sim-hour below which "typical" is too close to zero to divide by
# Ratios past this point can only come from a near-zero baseline blowing up
# the division, not a real signal — treated the same as "can't be
# computed" (None) rather than displayed as a fake precise-looking multiple.
_MAX_SANE_PACE_RATIO = 20.0


async def get_db() -> AsyncIterator[AsyncSession]:
    async with get_session() as session:
        yield session


def _latest_reading(samples: list[Sample]) -> Sample | None:
    """Latest (max sim_hours) reading, breaking ties by max views — same
    tie-break policy as the detector's own dedup, so the dashboard's
    "latest" numbers never disagree with what the detector actually scored.
    """
    if not samples:
        return None
    max_hour = max(s.sim_hours for s in samples)
    return max((s for s in samples if s.sim_hours == max_hour), key=lambda s: s.views)


async def _current_sim_hours(session: AsyncSession) -> float | None:
    """Most recently known sim_hours across every sample — the "now" the
    frontend needs to phrase last-updated times honestly, since sim time
    isn't wall-clock time and can't be derived from Date.now()."""
    return (await session.execute(select(func.max(Sample.sim_hours)))).scalar()


async def _samples_by_post(session: AsyncSession, post_ids: list[str]) -> dict[str, list[Sample]]:
    """One bulk query for every sample of the given posts, grouped by post_id
    — instead of a per-post round trip. At watchlist scale (~180+ posts, some
    with hundreds of rows after hours of continuous collection), a per-post
    query loop was slow enough to hit Supabase's statement_timeout."""
    samples_by_post: dict[str, list[Sample]] = defaultdict(list)
    if not post_ids:
        return samples_by_post
    all_samples = (
        await session.execute(
            select(Sample).where(Sample.post_id.in_(post_ids)).order_by(Sample.post_id, Sample.sim_hours)
        )
    ).scalars().all()
    for sample in all_samples:
        samples_by_post[sample.post_id].append(sample)
    return samples_by_post


def _window_hours(sample_points: list[SamplePoint]) -> float | None:
    """Duration of the latest interval, read directly off the two samples
    that produced it — never derived by dividing gain by velocity, which
    would itself divide by zero on a flat (zero-gain) interval."""
    deduped = _dedupe_samples(sample_points)
    if len(deduped) < 2:
        return None
    return deduped[-1].sim_hours - deduped[-2].sim_hours


def _consecutive_qualifying(signals: list[IntervalSignal]) -> int:
    """How many checks in a row, ending at the latest, showed qualifying
    momentum — reads compute_interval_signals' own `qualifies` flag
    (already computed by the detector for the state machine), it doesn't
    reimplement the detector's qualification logic."""
    count = 0
    for signal in reversed(signals):
        if not signal.qualifies:
            break
        count += 1
    return count


def _sane_ratio(value: float) -> float | None:
    """Reject a ratio rather than display it when it can't be trusted:
    NaN/inf (bad arithmetic), zero-or-negative (shouldn't happen for a
    velocity ratio but never trust that blindly), or absurdly large (a
    near-zero baseline blew up the division). "Not enough history" is the
    honest story in every one of these cases — never a fabricated number.
    """
    if value != value or value in (float("inf"), float("-inf")):
        return None
    if value <= 0 or value > _MAX_SANE_PACE_RATIO:
        return None
    return value


def _build_evidence(
    sample_points: list[SamplePoint],
    followers: int,
    signals: list[IntervalSignal],
    *,
    creator_pace_ratio: float | None = None,
    creator_pace_basis: str | None = None,
) -> EvidenceDetail | None:
    if not signals:
        return None
    latest_signal = signals[-1]
    return EvidenceDetail(
        sim_hours=latest_signal.sim_hours,
        absolute_gain=latest_signal.absolute_gain,
        relative_growth_pct=latest_signal.relative_growth_pct,
        velocity=latest_signal.velocity,
        follower_velocity=latest_signal.follower_velocity,
        trajectory_ratio=latest_signal.trajectory_ratio,
        window_hours=_window_hours(sample_points),
        consecutive_qualifying_checks=_consecutive_qualifying(signals),
        creator_pace_ratio=creator_pace_ratio,
        creator_pace_basis=creator_pace_basis,
    )


def _creator_pace_ratio(
    post_age: float,
    post_velocity: float,
    self_trajectory_ratio: float,
    other_points: list[tuple[float, float]],
) -> tuple[float | None, str | None]:
    """Compare a post's current velocity against how fast this creator's
    OTHER posts were typically growing at a similar age — "that creator's
    typical trajectory for posts of a similar age." `other_points` is
    (age, velocity) drawn from every other post's own interval signals.
    Falls back to the post's own earlier pace (trajectory_ratio, already
    computed by the detector) when the creator doesn't have enough other
    posts with signals to build a meaningful baseline from, OR when the
    other posts' baseline pace is itself too close to zero to be a
    meaningful denominator. Returns (None, None) — "not enough history" —
    rather than a fabricated number whenever neither comparison holds up.
    """
    if len(other_points) >= _MIN_BASELINE_POINTS:
        nearest = sorted(other_points, key=lambda p: abs(p[0] - post_age))[:_BASELINE_NEIGHBORS]
        baseline_velocity = statistics.median(v for _, v in nearest)
        if baseline_velocity >= _MIN_BASELINE_VELOCITY:
            ratio = _sane_ratio(post_velocity / baseline_velocity)
            if ratio is not None:
                return ratio, "creator"

    self_ratio = _sane_ratio(self_trajectory_ratio)
    if self_ratio is not None:
        return self_ratio, "self"
    return None, None


def _sparkline(sample_points: list[SamplePoint]) -> list[int]:
    """Last few deduped view counts for a card's small trend line — not
    full history, just enough to show a shape at a glance."""
    return [p.views for p in _dedupe_samples(sample_points)[-SPARKLINE_POINTS:]]


def _pace_sort_key(evidence: EvidenceDetail | None) -> float:
    """Sort/rank key for "current momentum": -inf when there's no
    trustworthy creator_pace_ratio, so a post without one always sorts
    last instead of crashing a numeric sort. Shared by every ranking
    across Home, Creators, and the agent's facts builder so they can
    never rank the same posts in different orders."""
    if evidence is None or evidence.creator_pace_ratio is None:
        return float("-inf")
    return evidence.creator_pace_ratio


def _unified_status(state: PostState, is_gone: bool, pace_ratio: float | None) -> str:
    """The one canonical status shown everywhere — headline, section
    membership, row badge, detail page, right panel. Nothing else computes
    its own opinion of what state a post is in, so nothing can disagree
    with it."""
    if is_gone:
        return _UNAVAILABLE
    if state == "BREAKOUT":
        return _TAKING_OFF
    if pace_ratio is not None and pace_ratio >= _MOVER_RATIO_THRESHOLD:
        return _WORTH_WATCHING
    return _STEADY


@dataclass
class _PostComputation:
    state: PostState
    score: float
    reason: str
    status_label: str
    evidence: EvidenceDetail | None
    signals: list[IntervalSignal]
    sample_points: list[SamplePoint]
    latest: Sample | None


def _compute_posts(
    posts: list[Post],
    samples_by_post: dict[str, list[Sample]],
    followers_by_creator: dict[str, int],
) -> dict[str, _PostComputation]:
    """Evaluates every post in `posts`, comparing each one against every
    OTHER post that shares its creator_id within this same set. Works for
    the whole watchlist (Home, system status) or a single creator's posts
    (creator roster/detail, a post's own detail alongside its siblings) —
    the comparison is always scoped by creator_id, not by how many posts
    happen to be passed in. This is the one place status/evidence gets
    computed; every endpoint calls it instead of computing its own.
    """
    signals_by_post: dict[str, list[IntervalSignal]] = {}
    results_by_post = {}
    for post in posts:
        followers = followers_by_creator.get(post.creator_id, 1)
        samples = samples_by_post.get(post.id, [])
        sample_points = [SamplePoint(sim_hours=s.sim_hours, views=s.views) for s in samples]
        signals_by_post[post.id] = compute_interval_signals(sample_points, followers)
        results_by_post[post.id] = evaluate_post(sample_points, followers)

    # Per-creator pool of (age, velocity) points from every active post's
    # signals — "that creator's other posts' sample histories," the
    # baseline the comparison is measured against. Gone posts are excluded:
    # a post's history after it was taken down isn't a fair picture of this
    # creator's normal, ongoing pace.
    points_by_creator: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for post in posts:
        if post.status == "gone":
            continue
        for signal in signals_by_post[post.id]:
            age = signal.sim_hours - post.first_seen_sim_hours
            points_by_creator[post.creator_id].append((post.id, age, signal.velocity))

    computations: dict[str, _PostComputation] = {}
    for post in posts:
        followers = followers_by_creator.get(post.creator_id, 1)
        samples = samples_by_post.get(post.id, [])
        sample_points = [SamplePoint(sim_hours=s.sim_hours, views=s.views) for s in samples]
        signals = signals_by_post[post.id]
        result = results_by_post[post.id]
        is_gone = post.status == "gone"

        pace_ratio: float | None = None
        pace_basis: str | None = None
        if signals and not is_gone:
            latest_signal = signals[-1]
            post_age = latest_signal.sim_hours - post.first_seen_sim_hours
            other_points = [
                (age, velocity)
                for pid, age, velocity in points_by_creator.get(post.creator_id, [])
                if pid != post.id
            ]
            pace_ratio, pace_basis = _creator_pace_ratio(
                post_age, latest_signal.velocity, latest_signal.trajectory_ratio, other_points
            )

        status_label = _unified_status(result.state, is_gone, pace_ratio)
        evidence = _build_evidence(
            sample_points,
            followers,
            signals,
            creator_pace_ratio=pace_ratio,
            creator_pace_basis=pace_basis,
        )
        computations[post.id] = _PostComputation(
            state=result.state,
            score=result.score,
            reason=result.reason,
            status_label=status_label,
            evidence=evidence,
            signals=signals,
            sample_points=sample_points,
            latest=_latest_reading(samples),
        )
    return computations


@router.get("/home", response_model=HomeResponse)
async def get_home(session: AsyncSession = Depends(get_db)) -> HomeResponse:
    creators = {c.id: c for c in (await session.execute(select(Creator))).scalars().all()}
    posts = (await session.execute(select(Post))).scalars().all()
    post_ids = [p.id for p in posts]
    samples_by_post = await _samples_by_post(session, post_ids)
    followers_by_creator = {cid: c.followers for cid, c in creators.items()}

    computations = _compute_posts(posts, samples_by_post, followers_by_creator)

    home_posts: dict[str, HomePost] = {}
    for post in posts:
        creator = creators.get(post.creator_id)
        comp = computations[post.id]
        sparkline = _sparkline(comp.sample_points)

        home_posts[post.id] = HomePost(
            post_id=post.id,
            creator_handle=creator.handle if creator else "unknown",
            creator_followers=creator.followers if creator else 1,
            caption=post.caption,
            published_at=post.published_at,
            views=comp.latest.views if comp.latest else 0,
            likes=comp.latest.likes if comp.latest else 0,
            comments=comp.latest.comments if comp.latest else 0,
            state=comp.state,
            score=comp.score,
            reason=comp.reason,
            status_label=comp.status_label,
            evidence=comp.evidence,
            is_gone=post.status == "gone",
            latest_sim_hours=comp.latest.sim_hours if comp.latest else None,
            sparkline=sparkline,
        )

    # Section membership matches status_label exactly: Act now is only
    # "Taking off" posts, Watch closely is only "Worth watching" posts — a
    # section header and every card inside it can never disagree, because
    # membership IS the same canonical label the card displays.
    active_posts = [p for p in home_posts.values() if not p.is_gone]

    taking_off = [p for p in active_posts if p.status_label == _TAKING_OFF]
    worth_watching = [p for p in active_posts if p.status_label == _WORTH_WATCHING]
    act_now = sorted(taking_off, key=lambda p: _pace_sort_key(p.evidence), reverse=True)[:_SECTION_CAP]
    watch_closely = sorted(worth_watching, key=lambda p: _pace_sort_key(p.evidence), reverse=True)[:_SECTION_CAP]

    unavailable_posts = sorted(
        (p for p in home_posts.values() if p.is_gone),
        key=lambda p: p.latest_sim_hours or 0,
        reverse=True,
    )

    return HomeResponse(
        act_now=act_now,
        watch_closely=watch_closely,
        unavailable_posts=unavailable_posts,
        total_posts=len(posts),
        unavailable_count=sum(1 for p in home_posts.values() if p.is_gone),
        current_sim_hours=await _current_sim_hours(session),
    )


@router.get("/status", response_model=SystemStatus)
async def get_status(session: AsyncSession = Depends(get_db)) -> SystemStatus:
    """Backs the right-hand panel's idle state — real system context
    instead of a placeholder, when no post is selected."""
    creators = {c.id: c for c in (await session.execute(select(Creator))).scalars().all()}
    posts = (await session.execute(select(Post))).scalars().all()
    post_ids = [p.id for p in posts]
    samples_by_post = await _samples_by_post(session, post_ids)
    followers_by_creator = {cid: c.followers for cid, c in creators.items()}

    computations = _compute_posts(posts, samples_by_post, followers_by_creator)

    # "Most recent status change" without persisting a transition-event
    # log: the most recently-updated post that's currently notable is an
    # honest, cheap stand-in — every input to it (status_label,
    # latest_sim_hours) is real, nothing here is invented.
    notable = [
        post
        for post in posts
        if computations[post.id].status_label in (_TAKING_OFF, _WORTH_WATCHING)
        and computations[post.id].latest is not None
    ]
    most_notable_post = None
    if notable:
        best = max(notable, key=lambda p: computations[p.id].latest.sim_hours)  # type: ignore[union-attr]
        comp = computations[best.id]
        creator = creators.get(best.creator_id)
        most_notable_post = NotablePost(
            post_id=best.id,
            creator_handle=creator.handle if creator else "unknown",
            caption=best.caption,
            status_label=comp.status_label,
            sim_hours=comp.latest.sim_hours,  # type: ignore[union-attr]
        )

    alert_row = (
        await session.execute(select(Alert).order_by(Alert.decided_sim_hours.desc()).limit(1))
    ).scalar_one_or_none()
    most_recent_alert = None
    if alert_row is not None:
        alert_post = next((p for p in posts if p.id == alert_row.post_id), None)
        creator = creators.get(alert_post.creator_id) if alert_post else None
        most_recent_alert = AlertSummary(
            post_id=alert_row.post_id,
            creator_handle=creator.handle if creator else "unknown",
            caption=alert_post.caption if alert_post else None,
            sim_hours=alert_row.decided_sim_hours,
        )

    return SystemStatus(
        posts_tracked=len(posts),
        last_checked_sim_hours=await _current_sim_hours(session),
        most_notable_post=most_notable_post,
        most_recent_alert=most_recent_alert,
    )


@router.get("/breakouts", response_model=BreakoutLogResponse)
async def get_breakout_log(session: AsyncSession = Depends(get_db)) -> BreakoutLogResponse:
    """Every post that reached BREAKOUT at any point, found by replaying the
    current detector over each post's full stored sample history. Entirely
    derived from stored samples — the alerts table is consulted only to
    mark which of these were officially submitted at the time, never to
    decide membership. A post can therefore appear here without an alert:
    it broke out under logic that wasn't deployed yet when it happened.
    """
    creators = {c.id: c for c in (await session.execute(select(Creator))).scalars().all()}
    posts = (await session.execute(select(Post))).scalars().all()
    samples_by_post = await _samples_by_post(session, [p.id for p in posts])
    followers_by_creator = {cid: c.followers for cid, c in creators.items()}
    computations = _compute_posts(posts, samples_by_post, followers_by_creator)

    submitted_ids = {
        row.post_id
        for row in (
            await session.execute(select(Alert).where(Alert.submitted.is_(True)))
        ).scalars().all()
    }

    entries: list[BreakoutLogEntry] = []
    for post in posts:
        comp = computations[post.id]
        history = run_state_machine(comp.signals)
        first_breakout = next((s for s in history if s.state == "BREAKOUT"), None)
        if first_breakout is None:
            continue

        points = _dedupe_samples(comp.sample_points)
        if not points:
            continue
        # First reading at or after the breakout moment; the signal's
        # sim_hours is the later sample of its interval, so this normally
        # lands exactly on it.
        views_at_breakout = next(
            (p.views for p in points if p.sim_hours >= first_breakout.sim_hours),
            points[-1].views,
        )
        peak_views = max(p.views for p in points)
        growth_multiple = peak_views / views_at_breakout if views_at_breakout > 0 else None

        # The real timestamp of the breakout reading, read straight off the
        # stored sample rather than derived from sim_hours.
        breakout_sample = next(
            (
                s
                for s in sorted(samples_by_post.get(post.id, []), key=lambda s: s.sim_hours)
                if s.sim_hours >= first_breakout.sim_hours
            ),
            None,
        )

        creator = creators.get(post.creator_id)
        entries.append(
            BreakoutLogEntry(
                post_id=post.id,
                creator_handle=creator.handle if creator else "unknown",
                caption=post.caption,
                breakout_sim_hours=first_breakout.sim_hours,
                breakout_at=breakout_sample.metrics_at if breakout_sample else None,
                views_at_breakout=views_at_breakout,
                peak_views=peak_views,
                growth_multiple=growth_multiple,
                current_status_label=comp.status_label,
                alert_submitted=post.id in submitted_ids,
            )
        )

    entries.sort(key=lambda e: e.breakout_sim_hours, reverse=True)
    return BreakoutLogResponse(entries=entries, current_sim_hours=await _current_sim_hours(session))


@router.get("/posts/{post_id}", response_model=PostDetail)
async def get_post_detail(post_id: str, session: AsyncSession = Depends(get_db)) -> PostDetail:
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"post {post_id!r} not found")

    creator = await session.get(Creator, post.creator_id)
    followers = creator.followers if creator else 1

    # Every post from the same creator, not just this one — needed so this
    # post's comparative pace (and therefore its status_label) is computed
    # exactly the same way it would be on Home or the creator's own page.
    creator_posts = (
        await session.execute(select(Post).where(Post.creator_id == post.creator_id))
    ).scalars().all()
    samples_by_post = await _samples_by_post(session, [p.id for p in creator_posts])
    computations = _compute_posts(creator_posts, samples_by_post, {post.creator_id: followers})
    comp = computations[post.id]

    trajectory = [
        TrajectoryPoint(sim_hours=p.sim_hours, views=p.views)
        for p in _dedupe_samples(comp.sample_points)
    ]

    alert_row = (
        await session.execute(select(Alert).where(Alert.post_id == post_id))
    ).scalar_one_or_none()

    # When this post first reached BREAKOUT, if ever — for the chart marker.
    # Full history (not just the latest state), same as "ever took off" on
    # the creator detail page.
    history = run_state_machine(comp.signals)
    breakout_sim_hours = next((s.sim_hours for s in history if s.state == "BREAKOUT"), None)

    creator_context = CreatorContext(
        id=creator.id if creator else post.creator_id,
        handle=creator.handle if creator else "unknown",
        name=creator.name if creator else "unknown",
        followers=followers,
        category=creator.category if creator else None,
        platform=creator.platform if creator else "unknown",
    )

    return PostDetail(
        post_id=post.id,
        caption=post.caption,
        published_at=post.published_at,
        platform=post.platform,
        is_gone=post.status == "gone",
        gone_sim_hours=post.gone_sim_hours,
        creator=creator_context,
        trajectory=trajectory,
        state=comp.state,
        score=comp.score,
        status_label=comp.status_label,
        reason=comp.reason,
        evidence=comp.evidence,
        alert_sent=alert_row is not None and alert_row.submitted,
        breakout_sim_hours=breakout_sim_hours,
        current_sim_hours=await _current_sim_hours(session),
    )


@router.get("/creators", response_model=CreatorsResponse)
async def get_creators(session: AsyncSession = Depends(get_db)) -> CreatorsResponse:
    creators = (await session.execute(select(Creator))).scalars().all()
    posts = (await session.execute(select(Post))).scalars().all()
    post_ids = [p.id for p in posts]
    samples_by_post = await _samples_by_post(session, post_ids)
    followers_by_creator = {c.id: c.followers for c in creators}

    posts_by_creator: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        posts_by_creator[post.creator_id].append(post)

    entries: list[CreatorRosterEntry] = []
    for creator in creators:
        creator_posts = posts_by_creator.get(creator.id, [])
        active_posts = [p for p in creator_posts if p.status != "gone"]
        unavailable_post_count = len(creator_posts) - len(active_posts)
        computations = _compute_posts(creator_posts, samples_by_post, followers_by_creator)

        taking_off_count = sum(1 for p in active_posts if computations[p.id].status_label == _TAKING_OFF)
        worth_watching_count = sum(
            1 for p in active_posts if computations[p.id].status_label == _WORTH_WATCHING
        )

        latest_hours = [
            computations[p.id].latest.sim_hours  # type: ignore[union-attr]
            for p in active_posts
            if computations[p.id].latest is not None
        ]
        latest_sim_hours = max(latest_hours) if latest_hours else None

        # "Strongest current signal" is current momentum, not lifetime
        # views — ranked by comparative pace, never by absolute score. If
        # nothing has a trustworthy comparative signal, there's honestly
        # nothing to call out, rather than defaulting to an arbitrary pick.
        movers = [
            p
            for p in active_posts
            if computations[p.id].evidence is not None
            and computations[p.id].evidence.creator_pace_ratio is not None  # type: ignore[union-attr]
        ]
        strongest_post = None
        if movers:
            best = max(
                movers,
                key=lambda p: computations[p.id].evidence.creator_pace_ratio,  # type: ignore[union-attr]
            )
            comp = computations[best.id]
            sparkline = _sparkline(comp.sample_points)
            strongest_post = CreatorRosterPost(
                post_id=best.id,
                caption=best.caption,
                state=comp.state,
                status_label=comp.status_label,
                score=comp.score,
                evidence=comp.evidence,
                sparkline=sparkline,
            )

        entries.append(
            CreatorRosterEntry(
                id=creator.id,
                handle=creator.handle,
                followers=creator.followers,
                active_post_count=len(active_posts),
                taking_off_count=taking_off_count,
                worth_watching_count=worth_watching_count,
                needs_attention_count=taking_off_count + worth_watching_count,
                unavailable_post_count=unavailable_post_count,
                strongest_post=strongest_post,
                latest_sim_hours=latest_sim_hours,
            )
        )

    entries.sort(key=lambda e: (e.needs_attention_count, e.followers), reverse=True)
    return CreatorsResponse(creators=entries, current_sim_hours=await _current_sim_hours(session))


@router.get("/creators/{creator_id}", response_model=CreatorDetailResponse)
async def get_creator_detail(
    creator_id: str, session: AsyncSession = Depends(get_db)
) -> CreatorDetailResponse:
    creator = await session.get(Creator, creator_id)
    if creator is None:
        raise HTTPException(status_code=404, detail=f"creator {creator_id!r} not found")

    posts = (
        await session.execute(select(Post).where(Post.creator_id == creator_id))
    ).scalars().all()
    samples_by_post = await _samples_by_post(session, [p.id for p in posts])
    computations = _compute_posts(posts, samples_by_post, {creator_id: creator.followers})

    active_posts: list[CreatorPostSummary] = []
    unavailable_posts: list[CreatorPostSummary] = []
    ever_took_off = 0
    latest_views: list[int] = []

    for post in posts:
        comp = computations[post.id]
        is_gone = post.status == "gone"

        # Full history (not just latest state) for "ever took off" — a
        # post's current state may have cooled off since it broke out.
        history = run_state_machine(comp.signals)
        if any(s.state == "BREAKOUT" for s in history):
            ever_took_off += 1

        if comp.latest is not None and not is_gone:
            latest_views.append(comp.latest.views)
        sparkline = _sparkline(comp.sample_points)

        summary = CreatorPostSummary(
            post_id=post.id,
            caption=post.caption,
            published_at=post.published_at,
            state=comp.state,
            status_label=comp.status_label,
            score=comp.score,
            evidence=comp.evidence,
            is_gone=is_gone,
            latest_sim_hours=comp.latest.sim_hours if comp.latest else None,
            sparkline=sparkline,
        )
        (unavailable_posts if is_gone else active_posts).append(summary)

    active_posts.sort(key=lambda p: _pace_sort_key(p.evidence), reverse=True)
    unavailable_posts.sort(key=lambda p: p.latest_sim_hours or 0, reverse=True)

    stats = CreatorStats(
        posts_tracked=len(posts),
        posts_that_took_off=ever_took_off,
        typical_views=int(statistics.median(latest_views)) if latest_views else 0,
    )

    creator_context = CreatorContext(
        id=creator.id,
        handle=creator.handle,
        name=creator.name,
        followers=creator.followers,
        category=creator.category,
        platform=creator.platform,
    )

    return CreatorDetailResponse(
        creator=creator_context,
        active_posts=active_posts,
        unavailable_posts=unavailable_posts,
        stats=stats,
        current_sim_hours=await _current_sim_hours(session),
    )
