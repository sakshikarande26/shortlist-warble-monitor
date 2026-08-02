"""Read-only dashboard API. Reads from the existing DB + detector only —
never calls the Warble API, never touches collector/detector/alert logic.
"""

import statistics
from collections import defaultdict
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    NEEDS_ATTENTION_STATES,
    STATE_LABELS,
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
    PostDetail,
    TrajectoryPoint,
)
from app.db import dao
from app.db.base import get_session
from app.db.models import Creator, Post, Sample
from app.detector.evaluate import evaluate_post, evaluate_post_from_db
from app.detector.momentum import SamplePoint, _dedupe_samples, compute_interval_signals
from app.detector.states import run_state_machine

router = APIRouter()

SPARKLINE_POINTS = 12

# --- Comparative ranking (Home only — presentation-layer, not the detector).
# A post has to meaningfully beat the creator's own norm to count as a
# "mover," not just edge past 1.0x on noise — this is what lets Home say so
# honestly when nothing is actually moving instead of padding the list with
# flat posts.
_MOVER_RATIO_THRESHOLD = 1.15
_SECTION_CAP = 5  # triage list, not a leaderboard
_MIN_BASELINE_POINTS = 2  # fewer than this and there's no real "typical" to compare against
_BASELINE_NEIGHBORS = 5  # nearest-by-age points from the creator's other posts used for the baseline
_MIN_BASELINE_VELOCITY = 1.0  # views/sim-hour below which "typical" is too close to zero to divide by


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


def _build_evidence(
    sample_points: list[SamplePoint],
    followers: int,
    *,
    creator_pace_ratio: float | None = None,
    creator_pace_basis: str | None = None,
) -> EvidenceDetail | None:
    signals = compute_interval_signals(sample_points, followers)
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
        creator_pace_ratio=creator_pace_ratio,
        creator_pace_basis=creator_pace_basis,
    )


def _creator_pace_ratio(
    post_age: float,
    post_velocity: float,
    self_trajectory_ratio: float,
    other_points: list[tuple[float, float]],
) -> tuple[float, str]:
    """Compare a post's current velocity against how fast this creator's
    OTHER posts were typically growing at a similar age — "that creator's
    typical trajectory for posts of a similar age." `other_points` is
    (age, velocity) drawn from every other post's own interval signals.
    Falls back to the post's own earlier pace (trajectory_ratio, already
    computed by the detector) when the creator doesn't have enough other
    posts with signals to build a meaningful baseline from, OR when the
    other posts' baseline pace is itself too close to zero to be a
    meaningful denominator — most of a creator's posts sitting flat isn't
    "a typical trajectory," and dividing by a near-zero baseline would
    produce a huge, meaningless ratio rather than an honest comparison.
    """
    if len(other_points) < _MIN_BASELINE_POINTS:
        return self_trajectory_ratio, "self"

    nearest = sorted(other_points, key=lambda p: abs(p[0] - post_age))[:_BASELINE_NEIGHBORS]
    baseline_velocity = statistics.median(v for _, v in nearest)
    if baseline_velocity < _MIN_BASELINE_VELOCITY:
        return self_trajectory_ratio, "self"
    return post_velocity / baseline_velocity, "creator"


@router.get("/home", response_model=HomeResponse)
async def get_home(session: AsyncSession = Depends(get_db)) -> HomeResponse:
    creators = {c.id: c for c in (await session.execute(select(Creator))).scalars().all()}
    posts = (await session.execute(select(Post))).scalars().all()
    post_ids = [p.id for p in posts]
    samples_by_post = await _samples_by_post(session, post_ids)

    # Pass 1: each post's own detector result + interval signals. Signals
    # are needed twice — once for this post's own evidence, once as raw
    # material for every OTHER post-of-the-same-creator's baseline below —
    # so they're computed once here and reused rather than recomputed.
    signals_by_post: dict[str, list] = {}
    results_by_post = {}
    for post in posts:
        creator = creators.get(post.creator_id)
        followers = creator.followers if creator else 1
        samples = samples_by_post.get(post.id, [])
        sample_points = [SamplePoint(sim_hours=s.sim_hours, views=s.views) for s in samples]
        signals_by_post[post.id] = compute_interval_signals(sample_points, followers)
        results_by_post[post.id] = evaluate_post(sample_points, followers)

    # Pass 2: per-creator pool of (age, velocity) points from every active
    # post's signals — "that creator's other posts' sample histories," the
    # baseline the comparative ranking is measured against. Gone posts are
    # excluded: a post's history after it was taken down isn't a fair
    # picture of this creator's normal, ongoing pace.
    points_by_creator: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for post in posts:
        if post.status == "gone":
            continue
        for signal in signals_by_post[post.id]:
            age = signal.sim_hours - post.first_seen_sim_hours
            points_by_creator[post.creator_id].append((post.id, age, signal.velocity))

    # Pass 3: assemble each HomePost, including its comparative pace against
    # the creator-level baseline from pass 2 (excluding the post's own
    # points from its own baseline).
    home_posts: dict[str, HomePost] = {}
    for post in posts:
        creator = creators.get(post.creator_id)
        followers = creator.followers if creator else 1
        samples = samples_by_post.get(post.id, [])
        sample_points = [SamplePoint(sim_hours=s.sim_hours, views=s.views) for s in samples]
        signals = signals_by_post[post.id]
        result = results_by_post[post.id]
        latest = _latest_reading(samples)
        sparkline = [p.views for p in _dedupe_samples(sample_points)[-SPARKLINE_POINTS:]]

        pace_ratio: float | None = None
        pace_basis: str | None = None
        if signals and post.status != "gone":
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

        home_posts[post.id] = HomePost(
            post_id=post.id,
            creator_handle=creator.handle if creator else "unknown",
            creator_followers=followers,
            caption=post.caption,
            published_at=post.published_at,
            views=latest.views if latest else 0,
            likes=latest.likes if latest else 0,
            comments=latest.comments if latest else 0,
            state=result.state,
            score=result.score,
            reason=result.reason,
            status_label=STATE_LABELS[result.state],
            evidence=_build_evidence(
                sample_points, followers, creator_pace_ratio=pace_ratio, creator_pace_basis=pace_basis
            ),
            is_gone=post.status == "gone",
            latest_sim_hours=latest.sim_hours if latest else None,
            sparkline=sparkline,
        )

    # Selection: BREAKOUT is unconditional and unranked by comparison
    # ("posts in confirmed BREAKOUT state (unchanged)"). Everything else is
    # ranked purely by comparative pace against the creator's own norm,
    # never by absolute state — a post the detector has never flagged can
    # still surface here if it's genuinely outperforming what's typical for
    # that specific creator, which is the actual fix for quiet days.
    active_posts = [p for p in home_posts.values() if not p.is_gone]
    breakout_posts = [p for p in active_posts if p.state == "BREAKOUT"]
    breakout_ids = {p.post_id for p in breakout_posts}

    def pace(p: HomePost) -> float:
        if p.evidence is None or p.evidence.creator_pace_ratio is None:
            return float("-inf")
        return p.evidence.creator_pace_ratio

    movers = sorted(
        (p for p in active_posts if p.post_id not in breakout_ids and pace(p) >= _MOVER_RATIO_THRESHOLD),
        key=pace,
        reverse=True,
    )

    act_now_extra_slots = max(0, _SECTION_CAP - len(breakout_posts))
    act_now_movers = movers[:act_now_extra_slots]
    act_now = sorted(breakout_posts + act_now_movers, key=pace, reverse=True)
    watch_closely = movers[act_now_extra_slots:][:_SECTION_CAP]

    return HomeResponse(
        act_now=act_now,
        watch_closely=watch_closely,
        total_posts=len(posts),
        unavailable_count=sum(1 for p in home_posts.values() if p.is_gone),
        current_sim_hours=await _current_sim_hours(session),
    )


@router.get("/posts/{post_id}", response_model=PostDetail)
async def get_post_detail(post_id: str, session: AsyncSession = Depends(get_db)) -> PostDetail:
    post = await session.get(Post, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail=f"post {post_id!r} not found")

    creator = await session.get(Creator, post.creator_id)
    followers = creator.followers if creator else 1

    samples = await dao.get_samples_for_post(session, post_id)
    sample_points = [SamplePoint(sim_hours=s.sim_hours, views=s.views) for s in samples]

    trajectory = [
        TrajectoryPoint(sim_hours=p.sim_hours, views=p.views) for p in _dedupe_samples(sample_points)
    ]

    result = await evaluate_post_from_db(session, post_id)

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
        state=result.state,
        score=result.score,
        status_label=STATE_LABELS[result.state],
        reason=result.reason,
        evidence=_build_evidence(sample_points, followers),
        current_sim_hours=await _current_sim_hours(session),
    )


@router.get("/creators", response_model=CreatorsResponse)
async def get_creators(session: AsyncSession = Depends(get_db)) -> CreatorsResponse:
    creators = (await session.execute(select(Creator))).scalars().all()
    posts = (await session.execute(select(Post))).scalars().all()
    post_ids = [p.id for p in posts]
    samples_by_post = await _samples_by_post(session, post_ids)

    posts_by_creator: dict[str, list[Post]] = defaultdict(list)
    for post in posts:
        posts_by_creator[post.creator_id].append(post)

    entries: list[CreatorRosterEntry] = []
    for creator in creators:
        active_posts = [p for p in posts_by_creator.get(creator.id, []) if p.status != "gone"]

        results = {}
        for post in active_posts:
            samples = samples_by_post.get(post.id, [])
            sample_points = [SamplePoint(sim_hours=s.sim_hours, views=s.views) for s in samples]
            results[post.id] = evaluate_post(sample_points, creator.followers)

        needs_attention_count = sum(1 for r in results.values() if r.state in NEEDS_ATTENTION_STATES)

        strongest_post = None
        if results:
            strongest_id = max(results, key=lambda pid: results[pid].score)
            strongest_result = results[strongest_id]
            strongest_post_row = next(p for p in active_posts if p.id == strongest_id)
            strongest_post = CreatorRosterPost(
                post_id=strongest_id,
                caption=strongest_post_row.caption,
                state=strongest_result.state,
                status_label=STATE_LABELS[strongest_result.state],
                score=strongest_result.score,
            )

        entries.append(
            CreatorRosterEntry(
                id=creator.id,
                handle=creator.handle,
                followers=creator.followers,
                active_post_count=len(active_posts),
                needs_attention_count=needs_attention_count,
                strongest_post=strongest_post,
            )
        )

    entries.sort(key=lambda e: (e.needs_attention_count, e.followers), reverse=True)
    return CreatorsResponse(creators=entries)


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
    post_ids = [p.id for p in posts]
    samples_by_post = await _samples_by_post(session, post_ids)

    active_posts: list[CreatorPostSummary] = []
    unavailable_posts: list[CreatorPostSummary] = []
    ever_took_off = 0
    latest_views: list[int] = []

    for post in posts:
        samples = samples_by_post.get(post.id, [])
        sample_points = [SamplePoint(sim_hours=s.sim_hours, views=s.views) for s in samples]

        # Full history (not just the latest state) — a post's current state
        # may have cooled off since it broke out, but "ever took off" is
        # still true and is what the roster stat is meant to answer.
        signals = compute_interval_signals(sample_points, creator.followers)
        history = run_state_machine(signals)
        if any(s.state == "BREAKOUT" for s in history):
            ever_took_off += 1

        result = evaluate_post(sample_points, creator.followers)
        latest = _latest_reading(samples)
        if latest is not None and post.status != "gone":
            latest_views.append(latest.views)
        sparkline = [p.views for p in _dedupe_samples(sample_points)[-SPARKLINE_POINTS:]]

        summary = CreatorPostSummary(
            post_id=post.id,
            caption=post.caption,
            published_at=post.published_at,
            state=result.state,
            status_label=STATE_LABELS[result.state],
            score=result.score,
            evidence=_build_evidence(sample_points, creator.followers),
            is_gone=post.status == "gone",
            latest_sim_hours=latest.sim_hours if latest else None,
            sparkline=sparkline,
        )
        (unavailable_posts if post.status == "gone" else active_posts).append(summary)

    active_posts.sort(key=lambda p: p.score, reverse=True)
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
