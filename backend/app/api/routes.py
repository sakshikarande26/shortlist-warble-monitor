"""Read-only dashboard API. Reads from the existing DB + detector only —
never calls the Warble API, never touches collector/detector/alert logic.
"""

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    NEEDS_ATTENTION_STATES,
    STATE_LABELS,
    CreatorContext,
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

router = APIRouter()


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


@router.get("/home", response_model=HomeResponse)
async def get_home(session: AsyncSession = Depends(get_db)) -> HomeResponse:
    creators = {c.id: c for c in (await session.execute(select(Creator))).scalars().all()}
    posts = (await session.execute(select(Post))).scalars().all()

    attention_queue: list[HomePost] = []
    other_posts: list[HomePost] = []

    for post in posts:
        creator = creators.get(post.creator_id)
        followers = creator.followers if creator else 1

        samples = await dao.get_samples_for_post(session, post.id)
        sample_points = [SamplePoint(sim_hours=s.sim_hours, views=s.views) for s in samples]
        # Calls the pure scorer directly (not evaluate_post_from_db) reusing
        # the samples/creator already fetched above — avoids re-querying
        # samples/post/creator per post across the whole watchlist.
        result = evaluate_post(sample_points, followers)

        latest = _latest_reading(samples)

        home_post = HomePost(
            post_id=post.id,
            creator_handle=creator.handle if creator else "unknown",
            creator_followers=followers,
            caption=post.caption,
            views=latest.views if latest else 0,
            likes=latest.likes if latest else 0,
            comments=latest.comments if latest else 0,
            state=result.state,
            score=result.score,
            status_label=STATE_LABELS[result.state],
            needs_attention=result.state in NEEDS_ATTENTION_STATES,
            is_gone=post.status == "gone",
        )
        (attention_queue if home_post.needs_attention else other_posts).append(home_post)

    attention_queue.sort(key=lambda p: p.score, reverse=True)
    other_posts.sort(key=lambda p: p.score, reverse=True)

    return HomeResponse(attention_queue=attention_queue, other_posts=other_posts)


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

    signals = compute_interval_signals(sample_points, followers)
    evidence = None
    if signals:
        latest_signal = signals[-1]
        evidence = EvidenceDetail(
            sim_hours=latest_signal.sim_hours,
            absolute_gain=latest_signal.absolute_gain,
            relative_growth_pct=latest_signal.relative_growth_pct,
            velocity=latest_signal.velocity,
            follower_velocity=latest_signal.follower_velocity,
            trajectory_ratio=latest_signal.trajectory_ratio,
        )

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
        evidence=evidence,
    )
