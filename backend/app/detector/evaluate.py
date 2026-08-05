"""Evaluator: samples in, current state + score + reason out.

`evaluate_post` is pure (no DB/network) and is what the unit tests exercise
directly with synthetic data, and what the future allocator/alert layer
calls once it has samples in hand. `evaluate_post_from_db` is the one
DB-touching function in this module — it never calls a Warble endpoint,
only reads what the collector already persisted via the DAO.
"""

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.detector.momentum import SamplePoint, compute_interval_signals
from app.detector.states import PostState, run_state_machine


@dataclass(frozen=True)
class EvaluationResult:
    state: PostState
    score: float
    reason: str
    sim_hours: float


@dataclass(frozen=True)
class PostHistory:
    """A post's current read plus the moment it FIRST broke out, if it ever did.

    These are two different questions and conflating them is what cost us
    recall: `current` answers "what is this post doing now", `first_breakout`
    answers "did this post ever break out". A post that broke out and has
    since cooled has a `current.state` of COOLING/NEW but a real
    `first_breakout` — and it is still a breakout the brand needed to hear
    about. Alerting reads `first_breakout`; the dashboard reads `current`.
    """

    current: EvaluationResult
    first_breakout: EvaluationResult | None


def evaluate_post_history(samples: list[SamplePoint], followers: int) -> PostHistory:
    """One state-machine walk, both answers. See PostHistory.

    Checked on the deduped interval count, not the raw sample count:
    compute_interval_signals collapses duplicate-timestamp rows internally
    (cache + live landing at the same sim_hours), so e.g. 3 raw samples that
    are all the same timestamp still have to fall through to
    insufficient_data rather than reach history[-1] on an empty history.
    """
    signals = compute_interval_signals(samples, followers)
    history = run_state_machine(signals)
    if not history:
        last_sim_hours = samples[-1].sim_hours if samples else 0.0
        return PostHistory(
            current=EvaluationResult(
                state="NEW", score=0.0, reason="insufficient_data", sim_hours=last_sim_hours
            ),
            first_breakout=None,
        )

    latest = history[-1]
    current = EvaluationResult(
        state=latest.state, score=latest.score, reason=latest.reason, sim_hours=latest.sim_hours
    )

    # The FIRST time it crossed into BREAKOUT — not the latest, and not
    # "is it in BREAKOUT right now". sim_hours here is the moment it broke
    # out, so an alert we're only just catching up on is still stamped
    # locally with when it actually happened rather than when we noticed.
    first = next((s for s in history if s.state == "BREAKOUT"), None)
    first_breakout = (
        None
        if first is None
        else EvaluationResult(
            state="BREAKOUT", score=first.score, reason=first.reason, sim_hours=first.sim_hours
        )
    )
    return PostHistory(current=current, first_breakout=first_breakout)


def evaluate_post(samples: list[SamplePoint], followers: int) -> EvaluationResult:
    """The current read only — what every dashboard surface asks for."""
    return evaluate_post_history(samples, followers).current


async def _load_histories(
    session: AsyncSession, post_ids: list[str]
) -> dict[str, PostHistory]:
    """Bulk-load every sample for the given posts in ONE query, then evaluate.

    Deliberately not a per-post query loop: at watchlist scale (200+ posts,
    hundreds of samples each) that was 200+ sequential Supabase round trips
    inside a single collector tick — slow enough to risk a statement timeout
    and to push detection well past the sampling cadence it's supposed to
    keep up with. Same fix, and the same reasoning, as routes._samples_by_post.
    """
    from app.db.models import Creator, Post, Sample

    if not post_ids:
        return {}

    posts = (
        await session.execute(select(Post).where(Post.id.in_(post_ids)))
    ).scalars().all()
    followers_by_creator = {
        c.id: c.followers for c in (await session.execute(select(Creator))).scalars().all()
    }

    samples_by_post: dict[str, list[SamplePoint]] = defaultdict(list)
    rows = (
        await session.execute(
            select(Sample.post_id, Sample.sim_hours, Sample.views)
            .where(Sample.post_id.in_(post_ids))
            .order_by(Sample.post_id, Sample.sim_hours)
        )
    ).all()
    for post_id, sim_hours, views in rows:
        samples_by_post[post_id].append(SamplePoint(sim_hours=sim_hours, views=views))

    return {
        post.id: evaluate_post_history(
            samples_by_post.get(post.id, []), followers_by_creator.get(post.creator_id, 1)
        )
        for post in posts
    }


async def evaluate_post_from_db(session: AsyncSession, post_id: str) -> EvaluationResult:
    from app.db import dao
    from app.db.models import Creator, Post

    rows = await dao.get_samples_for_post(session, post_id)
    samples = [SamplePoint(sim_hours=row.sim_hours, views=row.views) for row in rows]

    post = await session.get(Post, post_id)
    if post is None:
        raise ValueError(f"unknown post_id {post_id!r}")
    creator = await session.get(Creator, post.creator_id)
    followers = creator.followers if creator is not None else 1

    return evaluate_post(samples, followers)


async def evaluate_posts(session: AsyncSession, post_ids: list[str]) -> dict[str, EvaluationResult]:
    """Batch wrapper — current state for the whole watchlist."""
    return {post_id: history.current for post_id, history in (await _load_histories(session, post_ids)).items()}


async def find_breakouts(session: AsyncSession, post_ids: list[str]) -> dict[str, EvaluationResult]:
    """Every post that has EVER reached BREAKOUT in its stored history, keyed
    by post_id, valued by the moment it first broke out.

    This — not "which posts are in BREAKOUT right now" — is what the alerter
    is asking. Momentum fades: a post can break out at sim hour 8, cool off
    by sim hour 10, and be sitting in COOLING by the time the next tick runs.
    Filtering on the current state meant those never got reported at all,
    which is a recall miss, not a judgement call. The detector's decision
    rule is untouched (same thresholds, same state machine, same
    confirmations) — only the window we look through changed, from the
    latest state to the whole history.

    Alerts are idempotent per post and their first timestamp is final, so
    re-offering an already-reported post costs nothing: the alerter dedupes
    against the alerts table before spending a request.
    """
    return {
        post_id: history.first_breakout
        for post_id, history in (await _load_histories(session, post_ids)).items()
        if history.first_breakout is not None
    }
