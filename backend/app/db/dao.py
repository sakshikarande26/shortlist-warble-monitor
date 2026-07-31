import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, Creator, Post, RequestLog, Sample


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# --- samples: insert-only. No update_sample/delete_sample exists here on purpose;
# combined with the event listeners in models.py, append-only is enforced at both
# the DAO surface and the ORM level. ---


async def insert_sample(
    session: AsyncSession,
    *,
    post_id: str,
    views: int,
    likes: int,
    comments: int,
    metrics_at: str,
    sim_hours: float,
    source: str,
    captured_at: datetime.datetime | None = None,
) -> Sample:
    sample = Sample(
        post_id=post_id,
        views=views,
        likes=likes,
        comments=comments,
        metrics_at=metrics_at,
        sim_hours=sim_hours,
        source=source,
        captured_at=captured_at or _utcnow(),
    )
    session.add(sample)
    await session.flush()
    return sample


async def get_samples_for_post(session: AsyncSession, post_id: str) -> list[Sample]:
    result = await session.execute(
        select(Sample).where(Sample.post_id == post_id).order_by(Sample.sim_hours)
    )
    return list(result.scalars().all())


# --- creators / posts: portable upsert (get-then-update-or-insert) so the same
# code runs unmodified on SQLite (dev) and Postgres (prod). ---


async def upsert_creator(
    session: AsyncSession,
    *,
    id: str,
    handle: str,
    name: str,
    platform: str,
    followers: int,
    fetched_at_sim_hours: float,
    category: str | None = None,
    bio: str | None = None,
    fetched_at: datetime.datetime | None = None,
) -> Creator:
    creator = await session.get(Creator, id)
    fields = dict(
        handle=handle,
        name=name,
        category=category,
        bio=bio,
        platform=platform,
        followers=followers,
        fetched_at_sim_hours=fetched_at_sim_hours,
        fetched_at=fetched_at or _utcnow(),
    )
    if creator is None:
        creator = Creator(id=id, **fields)
        session.add(creator)
    else:
        for key, value in fields.items():
            setattr(creator, key, value)
    await session.flush()
    return creator


async def upsert_post(
    session: AsyncSession,
    *,
    id: str,
    creator_id: str,
    platform: str,
    first_seen_sim_hours: float,
    caption: str | None = None,
    published_at: str | None = None,
    first_seen_at: datetime.datetime | None = None,
) -> Post:
    post = await session.get(Post, id)
    fields = dict(
        creator_id=creator_id,
        caption=caption,
        published_at=published_at,
        platform=platform,
        first_seen_sim_hours=first_seen_sim_hours,
        first_seen_at=first_seen_at or _utcnow(),
    )
    if post is None:
        post = Post(id=id, **fields)
        session.add(post)
    else:
        for key, value in fields.items():
            setattr(post, key, value)
    await session.flush()
    return post


async def mark_post_gone(session: AsyncSession, *, post_id: str, sim_hours: float) -> Post:
    post = await session.get(Post, post_id)
    if post is None:
        raise ValueError(f"unknown post_id {post_id!r}")
    if post.status != "gone":
        post.status = "gone"
        post.gone_sim_hours = sim_hours
    await session.flush()
    return post


async def get_watchlist_post_ids(session: AsyncSession) -> list[str]:
    result = await session.execute(select(Post.id).where(Post.status == "active"))
    return list(result.scalars().all())


# --- alerts: post_id is the PK, so "insert" and "idempotent per post" are the
# same operation. First decision (decided_sim_hours/note/submitted) is final;
# repeat calls only backfill received_* fields and flag is_duplicate. ---


async def record_alert(
    session: AsyncSession,
    *,
    post_id: str,
    decided_sim_hours: float,
    note: str | None = None,
    submitted: bool = True,
    received_sim_hours: float | None = None,
    received_at: datetime.datetime | None = None,
) -> Alert:
    alert = await session.get(Alert, post_id)
    if alert is None:
        alert = Alert(
            post_id=post_id,
            decided_sim_hours=decided_sim_hours,
            note=note,
            submitted=submitted,
            received_sim_hours=received_sim_hours,
            received_at=received_at,
            is_duplicate=False,
        )
        session.add(alert)
    else:
        alert.is_duplicate = True
        if alert.received_sim_hours is None and received_sim_hours is not None:
            alert.received_sim_hours = received_sim_hours
        if alert.received_at is None and received_at is not None:
            alert.received_at = received_at
    await session.flush()
    return alert


async def get_alerted_post_ids(session: AsyncSession) -> set[str]:
    result = await session.execute(select(Alert.post_id).where(Alert.submitted.is_(True)))
    return set(result.scalars().all())


async def log_request(
    session: AsyncSession,
    *,
    endpoint: str,
    method: str,
    status_code: int,
    sim_hours: float | None = None,
    rate_remaining: int | None = None,
    retry_after: int | None = None,
    called_at: datetime.datetime | None = None,
) -> RequestLog:
    entry = RequestLog(
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        sim_hours=sim_hours,
        rate_remaining=rate_remaining,
        retry_after=retry_after,
        called_at=called_at or _utcnow(),
    )
    session.add(entry)
    await session.flush()
    return entry
