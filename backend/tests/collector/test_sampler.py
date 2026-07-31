import pytest

from app.client.models import Alert, Creator, CreatorPostsPage, Post, PostsBatchResult
from app.collector import sampler
from app.collector.budget import BudgetTracker
from app.db import dao
from app.db.base import get_session
from app.db.models import Alert as AlertRow
from tests.collector.fakes import FakeWarbleClient


def make_post(id: str, **kwargs) -> Post:
    defaults = dict(creator_id="wc_0000000001", views=10, likes=1, comments=0, metrics_at="t0")
    defaults.update(kwargs)
    return Post(id=id, **defaults)


@pytest.mark.asyncio
async def test_discover_follows_next_cursor_and_upserts_idempotently():
    client = FakeWarbleClient()
    client.creators_response = [Creator(id="wc_0000000001", name="Test", handle="test")]
    client.pages_by_creator["wc_0000000001"] = [
        CreatorPostsPage(posts=[make_post("wp_0000000001")], next_cursor="page2"),
        CreatorPostsPage(posts=[make_post("wp_0000000002")], next_cursor=None),
    ]
    budget = BudgetTracker()

    stats = await sampler.discover(client, budget, sim_hours=1.0)

    assert stats.creators_seen == 1
    assert stats.posts_seen == 2

    async with get_session() as session:
        watchlist = await dao.get_watchlist_post_ids(session)
    assert set(watchlist) == {"wp_0000000001", "wp_0000000002"}

    request_calls = [c for c in client.calls if c.startswith("GET /creators")]
    assert len(request_calls) == 3  # /creators + 2 pages


@pytest.mark.asyncio
async def test_sample_live_marks_missing_gone_and_inserts_samples_for_rest():
    client = FakeWarbleClient()
    budget = BudgetTracker()

    async with get_session() as session:
        await dao.upsert_creator(
            session, id="wc_0000000001", handle="h", name="n", platform="p",
            followers=0, fetched_at_sim_hours=0.0,
        )
        await dao.upsert_post(
            session, id="wp_0000000001", creator_id="wc_0000000001",
            platform="p", first_seen_sim_hours=0.0,
        )
        await dao.upsert_post(
            session, id="wp_0000000002", creator_id="wc_0000000001",
            platform="p", first_seen_sim_hours=0.0,
        )
        await session.commit()

    client.batch_responses = [
        PostsBatchResult(posts=[make_post("wp_0000000001")], missing_ids=["wp_0000000002"])
    ]

    stats = await sampler.sample_live(
        client, budget, ["wp_0000000001", "wp_0000000002"], sim_hours=2.0
    )

    assert stats.sampled == 1
    assert stats.gone == 1

    async with get_session() as session:
        watchlist = await dao.get_watchlist_post_ids(session)
        samples = await dao.get_samples_for_post(session, "wp_0000000001")
    assert watchlist == ["wp_0000000001"]
    assert len(samples) == 1
    assert samples[0].source == "live"


@pytest.mark.asyncio
async def test_sync_alerts_preserves_first_decided_sim_hours():
    async with get_session() as session:
        await dao.upsert_creator(
            session, id="wc_0000000001", handle="h", name="n", platform="p",
            followers=0, fetched_at_sim_hours=0.0,
        )
        await dao.upsert_post(
            session, id="wp_0000000001", creator_id="wc_0000000001",
            platform="p", first_seen_sim_hours=0.0,
        )
        await dao.record_alert(session, post_id="wp_0000000001", decided_sim_hours=5.0, note="original")
        await session.commit()

    client = FakeWarbleClient()
    client.alerts_response = [Alert(id="a1", post_id="wp_0000000001", note="server note")]
    budget = BudgetTracker()

    await sampler.sync_alerts(client, budget, sim_hours=99.0)

    async with get_session() as session:
        alerted = await dao.get_alerted_post_ids(session)
        row = await session.get(AlertRow, "wp_0000000001")
    assert alerted == {"wp_0000000001"}
    assert row.decided_sim_hours == 5.0  # first decision stands
    assert row.is_duplicate is True
