import datetime
import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.client.client import WarbleClient
from app.client.exceptions import WarbleAPIError, WarbleRateLimitError
from app.client.models import Me
from app.collector.budget import BudgetTracker
from app.db import dao
from app.db.base import get_session

logger = logging.getLogger("collector.sampler")

LIVE_BATCH_SIZE = 10


def _parse_iso(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value)


@dataclass
class DiscoverStats:
    creators_seen: int = 0
    posts_seen: int = 0


@dataclass
class LiveSampleStats:
    sampled: int = 0
    gone: int = 0
    deferred_chunks: int = 0


async def _log_call(session, budget: BudgetTracker, client: WarbleClient, *, endpoint: str, method: str, sim_hours: float | None, status_code: int) -> None:
    rate_limit = client.last_rate_limit
    budget.update(rate_limit)
    await dao.log_request(
        session,
        endpoint=endpoint,
        method=method,
        status_code=status_code,
        sim_hours=sim_hours,
        rate_remaining=rate_limit.remaining if rate_limit else None,
    )


async def heartbeat(client: WarbleClient, budget: BudgetTracker) -> Me:
    """GET /me — the only source of sim_hours for stamping every other table."""
    async with get_session() as session:
        try:
            me = await client.get_me()
        except WarbleAPIError as exc:
            await _log_call(
                session, budget, client, endpoint="/me", method="GET",
                sim_hours=None, status_code=exc.status_code or 599,
            )
            await session.commit()
            raise
        await _log_call(
            session, budget, client, endpoint="/me", method="GET",
            sim_hours=me.sim_hours, status_code=200,
        )
        await session.commit()
        return me


async def discover(client: WarbleClient, budget: BudgetTracker, sim_hours: float) -> DiscoverStats:
    """Cheap/wide sweep over the (cached) creator + post listings.

    Enrolling a post in the watchlist is just upserting it as an
    (implicitly) status="active" Post row — there's no separate watchlist
    table, `dao.get_watchlist_post_ids` is the watchlist.
    """
    stats = DiscoverStats()
    async with get_session() as session:
        try:
            creators = await client.get_creators()
        except WarbleAPIError as exc:
            await _log_call(
                session, budget, client, endpoint="/creators", method="GET",
                sim_hours=sim_hours, status_code=exc.status_code or 599,
            )
            await session.commit()
            raise
        await _log_call(
            session, budget, client, endpoint="/creators", method="GET",
            sim_hours=sim_hours, status_code=200,
        )

        for creator in creators:
            await dao.upsert_creator(
                session,
                id=creator.id,
                handle=creator.handle,
                name=creator.name,
                category=creator.category,
                bio=creator.bio,
                platform=creator.platform,
                followers=creator.followers,
                fetched_at_sim_hours=sim_hours,
            )
            stats.creators_seen += 1

            cursor: str | None = None
            while True:
                endpoint = f"/creators/{creator.id}/posts"
                try:
                    page = await client.get_creator_posts(creator.id, cursor=cursor)
                except WarbleAPIError as exc:
                    await _log_call(
                        session, budget, client, endpoint=endpoint, method="GET",
                        sim_hours=sim_hours, status_code=exc.status_code or 599,
                    )
                    if isinstance(exc, WarbleRateLimitError):
                        # A 429 applies to the whole API key, not just this
                        # creator's pagination — propagate so the loop pauses
                        # everything instead of ploughing on to the next creator.
                        await session.commit()
                        raise
                    break
                await _log_call(
                    session, budget, client, endpoint=endpoint, method="GET",
                    sim_hours=sim_hours, status_code=200,
                )

                for post in page.data:
                    await dao.upsert_post(
                        session,
                        id=post.id,
                        creator_id=post.creator_id,
                        platform=post.platform,
                        first_seen_sim_hours=sim_hours,
                        caption=post.caption,
                        published_at=post.published_at,
                    )
                    await dao.insert_sample(
                        session,
                        post_id=post.id,
                        views=post.metrics.views,
                        likes=post.metrics.likes,
                        comments=post.metrics.comments,
                        # Cache-sourced listing: use metrics_cached_at, never
                        # the (absent, on this endpoint) live metrics_at.
                        metrics_at=post.metrics_cached_at,
                        sim_hours=sim_hours,
                        source="cache",
                    )
                    stats.posts_seen += 1

                if not page.next_cursor:
                    break
                cursor = page.next_cursor

            await session.commit()

    return stats


async def sample_live(
    client: WarbleClient, budget: BudgetTracker, post_ids: list[str], sim_hours: float
) -> LiveSampleStats:
    stats = LiveSampleStats()
    chunks = [post_ids[i : i + LIVE_BATCH_SIZE] for i in range(0, len(post_ids), LIVE_BATCH_SIZE)]

    async with get_session() as session:
        for i, chunk in enumerate(chunks):
            if not budget.can_spend(1):
                stats.deferred_chunks += len(chunks) - i
                logger.warning(
                    "budget exhausted, deferring %d remaining chunk(s) to next cycle",
                    len(chunks) - i,
                )
                break

            try:
                result = await client.get_posts_batch(chunk)
            except WarbleAPIError as exc:
                await _log_call(
                    session, budget, client, endpoint="/posts/batch", method="GET",
                    sim_hours=sim_hours, status_code=exc.status_code or 599,
                )
                await session.commit()
                raise
            await _log_call(
                session, budget, client, endpoint="/posts/batch", method="GET",
                sim_hours=sim_hours, status_code=200,
            )

            for post in result.posts:
                await dao.insert_sample(
                    session,
                    post_id=post.id,
                    views=post.metrics.views,
                    likes=post.metrics.likes,
                    comments=post.metrics.comments,
                    # Live batch endpoint: always metrics_at, never metrics_cached_at.
                    metrics_at=post.metrics_at,
                    sim_hours=sim_hours,
                    source="live",
                )
                stats.sampled += 1

            for missing_id in result.missing_ids:
                await dao.mark_post_gone(session, post_id=missing_id, sim_hours=sim_hours)
                stats.gone += 1

            await session.commit()

    return stats


async def sync_alerts(client: WarbleClient, budget: BudgetTracker, sim_hours: float) -> None:
    """Rehydrate local alert state from the server on startup. Existing local
    rows keep their original decided_sim_hours (first timestamp is final) —
    that guarantee already lives in dao.record_alert.
    """
    async with get_session() as session:
        try:
            alerts = await client.get_alerts()
        except WarbleAPIError as exc:
            await _log_call(
                session, budget, client, endpoint="/alerts", method="GET",
                sim_hours=sim_hours, status_code=exc.status_code or 599,
            )
            await session.commit()
            raise
        await _log_call(
            session, budget, client, endpoint="/alerts", method="GET",
            sim_hours=sim_hours, status_code=200,
        )

        for alert in alerts:
            # sync_alerts runs before discover() on startup (per spec), so a
            # server-known alert can in principle reference a post we haven't
            # discovered locally yet (fresh DB, or an alert from a prior
            # process). alerts.post_id is a FK — skip and warn rather than
            # crash startup over a reconciliation edge case; discover() will
            # backfill the post shortly and the alert can reconcile next sync.
            try:
                await dao.record_alert(
                    session,
                    post_id=alert.post_id,
                    # The server's own receipt time is the true original
                    # decision time — more accurate than stamping "now" for
                    # something we're only just learning about on reconcile.
                    decided_sim_hours=alert.received_sim_hours,
                    note=alert.note,
                    submitted=True,
                    received_sim_hours=alert.received_sim_hours,
                    received_at=_parse_iso(alert.received_at),
                )
                await session.commit()
            except IntegrityError:
                await session.rollback()
                logger.warning(
                    "alert for unknown post_id %r skipped (not yet discovered locally)",
                    alert.post_id,
                )
