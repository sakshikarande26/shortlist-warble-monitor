"""Evaluator: samples in, current state + score + reason out.

`evaluate_post` is pure (no DB/network) and is what the unit tests exercise
directly with synthetic data, and what the future allocator/alert layer
calls once it has samples in hand. `evaluate_post_from_db` is the one
DB-touching function in this module — it never calls a Warble endpoint,
only reads what the collector already persisted via the DAO.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.detector.momentum import SamplePoint, compute_interval_signals
from app.detector.states import PostState, run_state_machine


@dataclass(frozen=True)
class EvaluationResult:
    state: PostState
    score: float
    reason: str
    sim_hours: float


def evaluate_post(samples: list[SamplePoint], followers: int) -> EvaluationResult:
    # Checked on the deduped interval count, not the raw sample count:
    # compute_interval_signals collapses duplicate-timestamp rows internally
    # (cache + live landing at the same sim_hours), so e.g. 3 raw samples
    # that are all the same timestamp still have to fall through to
    # insufficient_data rather than reach history[-1] on an empty history.
    signals = compute_interval_signals(samples, followers)
    history = run_state_machine(signals)
    if not history:
        last_sim_hours = samples[-1].sim_hours if samples else 0.0
        return EvaluationResult(state="NEW", score=0.0, reason="insufficient_data", sim_hours=last_sim_hours)

    latest = history[-1]
    return EvaluationResult(
        state=latest.state, score=latest.score, reason=latest.reason, sim_hours=latest.sim_hours
    )


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
    """Batch wrapper — what loop.py calls each live-sampling tick to get
    current states for the whole watchlist."""
    return {post_id: await evaluate_post_from_db(session, post_id) for post_id in post_ids}
