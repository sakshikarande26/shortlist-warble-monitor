import pytest

from app.client.models import Alert, Creator, CreatorPostsPage, Post, PostMetrics, PostsBatchResult
from app.collector import sampler
from app.collector.budget import BudgetTracker
from app.db import dao
from app.db.base import get_session
from app.db.models import Alert as AlertRow
from app.db.models import Post as PostRow
from tests.collector.fakes import FakeWarbleClient


def make_post(
    id: str,
    *,
    metrics_cached_at: str | None = None,
    metrics_at: str | None = None,
    views: int = 10,
    likes: int = 1,
    comments: int = 0,
    **overrides,
) -> Post:
    defaults = dict(
        creator_id="wc_0000000001",
        creator_handle="handle",
        creator_name="Name",
        platform="clip",
        published_at="2026-07-05T00:00:00.000Z",
        caption="caption",
    )
    defaults.update(overrides)
    return Post(
        id=id,
        metrics=PostMetrics(views=views, likes=likes, comments=comments),
        metrics_cached_at=metrics_cached_at,
        metrics_at=metrics_at,
        **defaults,
    )


def make_creator(id: str = "wc_0000000001", **overrides) -> Creator:
    defaults = dict(
        handle="test", name="Test", category="lifestyle", bio="bio",
        platform="clip", followers=5000,
    )
    defaults.update(overrides)
    return Creator(id=id, **defaults)


@pytest.mark.asyncio
async def test_discover_follows_next_cursor_and_upserts_idempotently():
    client = FakeWarbleClient()
    client.creators_response = [make_creator()]
    client.pages_by_creator["wc_0000000001"] = [
        CreatorPostsPage(
            data=[make_post("wp_0000000001", metrics_cached_at="2026-07-06T00:00:00.000Z")],
            next_cursor="page2",
        ),
        CreatorPostsPage(
            data=[make_post("wp_0000000002", metrics_cached_at="2026-07-06T00:00:00.000Z")],
            next_cursor=None,
        ),
    ]
    budget = BudgetTracker()

    stats = await sampler.discover(client, budget, sim_hours=1.0)

    assert stats.creators_seen == 1
    assert stats.posts_seen == 2

    async with get_session() as session:
        watchlist = await dao.get_watchlist_post_ids(session)
        samples = await dao.get_samples_for_post(session, "wp_0000000001")
    assert set(watchlist) == {"wp_0000000001", "wp_0000000002"}
    assert samples[0].metrics_at == "2026-07-06T00:00:00.000Z"
    assert samples[0].source == "cache"

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
        PostsBatchResult(
            posts=[make_post("wp_0000000001", metrics_at="2026-07-06T01:00:00.000Z")],
            missing_ids=["wp_0000000002"],
        )
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
    assert samples[0].metrics_at == "2026-07-06T01:00:00.000Z"


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
    client.alerts_response = [
        Alert(
            post_id="wp_0000000001", note="server note",
            received_sim_hours=3.0, received_at="2026-07-06T00:30:00.000Z",
        )
    ]
    budget = BudgetTracker()

    await sampler.sync_alerts(client, budget, sim_hours=99.0)

    async with get_session() as session:
        alerted = await dao.get_alerted_post_ids(session)
        row = await session.get(AlertRow, "wp_0000000001")
    assert alerted == {"wp_0000000001"}
    assert row.decided_sim_hours == 5.0  # first decision stands
    # NOT a duplicate: this is startup reconciliation reading back an alert
    # we ourselves sent, not the API telling us we sent one twice. Flagging
    # it here marked all three real alerts in the live DB as duplicates,
    # which is not what the field means.
    assert row.is_duplicate is False
    # The server's receipt details still get backfilled onto our row.
    assert row.received_sim_hours == 3.0


@pytest.mark.asyncio
async def test_upsert_post_never_rewrites_first_seen():
    """Real bug: first_seen_sim_hours was in the update set, so every 6-hourly
    discovery sweep rewrote it to "now". 210 of 211 live posts ended up
    sharing the last sweep's timestamp, leaving no post with a real age —
    and _creator_pace_ratio picks its baseline from "other posts at a
    similar age", so everything was compared at age ~0.
    """
    async with get_session() as session:
        await dao.upsert_creator(
            session, id="wc_0000000001", handle="h", name="n", platform="p",
            followers=0, fetched_at_sim_hours=0.0,
        )
        await dao.upsert_post(
            session, id="wp_0000000001", creator_id="wc_0000000001",
            platform="p", first_seen_sim_hours=3.5, caption="original",
        )
        await session.commit()

        # A later sweep sees the same post again, much later in the run.
        await dao.upsert_post(
            session, id="wp_0000000001", creator_id="wc_0000000001",
            platform="p", first_seen_sim_hours=136.7, caption="edited caption",
        )
        await session.commit()
        post = await session.get(PostRow, "wp_0000000001")

    assert post.first_seen_sim_hours == 3.5  # when we FIRST saw it, not last
    assert post.caption == "edited caption"  # mutable fields still refresh


@pytest.mark.asyncio
async def test_api_reported_duplicate_does_set_the_flag():
    """The flag still means what it says when the API actually says it."""
    async with get_session() as session:
        await dao.upsert_creator(
            session, id="wc_0000000001", handle="h", name="n", platform="p",
            followers=0, fetched_at_sim_hours=0.0,
        )
        await dao.upsert_post(
            session, id="wp_0000000001", creator_id="wc_0000000001",
            platform="p", first_seen_sim_hours=0.0,
        )
        await dao.record_alert(session, post_id="wp_0000000001", decided_sim_hours=5.0)
        await dao.record_alert(
            session, post_id="wp_0000000001", decided_sim_hours=9.0,
            api_reported_duplicate=True,
        )
        await session.commit()
        row = await session.get(AlertRow, "wp_0000000001")

    assert row.is_duplicate is True
    assert row.decided_sim_hours == 5.0  # first timestamp is still final
