import asyncio
import time

import pytest

from app.alerts.alerter import Alerter
from app.client.models import Creator, Me, MeRateLimit, PostsBatchResult
from app.collector import loop as collector_loop
from app.collector.budget import BudgetTracker
from app.db import dao
from app.db.base import get_session
from app.db.models import Alert as AlertRow
from app.detector.evaluate import EvaluationResult
from tests.collector.fakes import FakeWarbleClient, rate_limited_error
from tests.collector.test_sampler import make_post


def make_me(**overrides) -> Me:
    defaults = dict(
        label="x",
        activated=True,
        sim_hours=12.5,
        server_time="2026-07-06T00:00:00.000Z",
        clock_multiplier=1.0,
        key_expires_at=None,
        rate_limit=MeRateLimit(limit_per_hour=250, used=1, remaining=249),
    )
    defaults.update(overrides)
    return Me(**defaults)


def make_creator(id: str = "wc_0000000001", **overrides) -> Creator:
    defaults = dict(
        handle="h", name="n", category="lifestyle", bio="bio", platform="clip", followers=1000,
    )
    defaults.update(overrides)
    return Creator(id=id, **defaults)


@pytest.mark.asyncio
async def test_heartbeat_tick_updates_sim_hours():
    client = FakeWarbleClient()
    client.me_response = make_me(sim_hours=12.5)
    budget = BudgetTracker()
    state = collector_loop.CollectorState()

    await collector_loop._heartbeat_tick(client, budget, state)

    # Anchored at what /me said. Not exactly equal any more: the clock keeps
    # advancing from that anchor, so a microsecond of test runtime counts.
    assert state.current_sim_hours == pytest.approx(12.5, abs=1e-3)


@pytest.mark.asyncio
async def test_sim_clock_advances_between_heartbeats():
    """The regression this exists to prevent: /me is only called every 30
    minutes, live sampling runs every 15, so a frozen sim_hours stamped two
    consecutive sampling rounds with the SAME timestamp — and the detector's
    dedup then collapsed one of every two rounds away. Against live data,
    283 stored samples per post became 151 usable points.
    """
    state = collector_loop.CollectorState()
    state.anchor_sim_clock(10.0, clock_multiplier=1.0)

    first = state.current_sim_hours
    # Rewind the anchor by 15 real minutes: exactly one live-sampling gap.
    state._sim_anchor_at -= 15 * 60
    second = state.current_sim_hours

    assert second > first
    assert second - 10.0 == pytest.approx(0.25, abs=1e-3)  # 15 min at 1x


@pytest.mark.asyncio
async def test_sim_clock_honours_the_servers_multiplier():
    state = collector_loop.CollectorState()
    state.anchor_sim_clock(10.0, clock_multiplier=4.0)
    state._sim_anchor_at -= 3600  # one real hour

    assert state.current_sim_hours == pytest.approx(14.0, abs=1e-3)


@pytest.mark.asyncio
async def test_sim_clock_keeps_last_multiplier_when_server_omits_it():
    state = collector_loop.CollectorState()
    state.anchor_sim_clock(10.0, clock_multiplier=4.0)
    state.anchor_sim_clock(20.0, clock_multiplier=None)
    state._sim_anchor_at -= 3600

    assert state.current_sim_hours == pytest.approx(24.0, abs=1e-3)  # still 4x, not reset to 1x


@pytest.mark.asyncio
async def test_rate_limit_pauses_all_ticks():
    client = FakeWarbleClient()
    client.me_response = rate_limited_error(retry_after_seconds=30.0)
    budget = BudgetTracker()
    state = collector_loop.CollectorState()

    assert state.is_paused() is False
    await collector_loop._heartbeat_tick(client, budget, state)
    assert state.is_paused() is True

    # A different tick should now no-op because the loop is paused.
    client.creators_response = [make_creator()]
    await collector_loop._discovery_tick(client, budget, state)
    assert not any(c.startswith("GET /creators") for c in client.calls)


@pytest.mark.asyncio
async def test_discovery_tick_skips_when_budget_exhausted():
    client = FakeWarbleClient()
    client.creators_response = [make_creator()]
    budget = BudgetTracker(reserve=40, ceiling=250)
    budget._last_remaining = 40  # remaining() == 0
    state = collector_loop.CollectorState()

    await collector_loop._discovery_tick(client, budget, state)

    assert client.calls == []


@pytest.mark.asyncio
async def test_sleep_or_stop_returns_immediately_on_shutdown():
    state = collector_loop.CollectorState()
    state.shutdown.set()

    start = time.monotonic()
    woken_by_shutdown = await state.sleep_or_stop(3600)
    elapsed = time.monotonic() - start

    assert woken_by_shutdown is True
    assert elapsed < 1.0


@pytest.mark.asyncio
async def test_sleep_or_stop_times_out_when_no_shutdown():
    state = collector_loop.CollectorState()
    woken_by_shutdown = await state.sleep_or_stop(0.05)
    assert woken_by_shutdown is False


async def _seed_watchlist_post(post_id: str = "wp_0000000001") -> None:
    async with get_session() as session:
        await dao.upsert_creator(
            session, id="wc_0000000001", handle="h", name="n", platform="p",
            followers=1000, fetched_at_sim_hours=0.0,
        )
        await dao.upsert_post(
            session, id=post_id, creator_id="wc_0000000001",
            platform="p", first_seen_sim_hours=0.0,
        )
        await session.commit()


@pytest.mark.asyncio
async def test_evaluate_failure_does_not_lose_samples(monkeypatch):
    # Capture must survive a detector bug: sample_live() writes and commits
    # first, and evaluate_posts() blowing up afterward must not undo that.
    await _seed_watchlist_post()
    client = FakeWarbleClient()
    client.batch_responses = [
        PostsBatchResult(
            posts=[make_post("wp_0000000001", metrics_at="2026-07-06T00:00:00.000Z")],
            missing_ids=[],
        )
    ]
    budget = BudgetTracker()
    state = collector_loop.CollectorState()
    alerter = Alerter(client, budget)

    async def raising_find_breakouts(session, post_ids):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(collector_loop, "find_breakouts", raising_find_breakouts)

    await collector_loop._live_sample_tick(client, budget, state, alerter)  # must not raise

    async with get_session() as session:
        samples = await dao.get_samples_for_post(session, "wp_0000000001")
    assert len(samples) == 1


@pytest.mark.asyncio
async def test_fire_alerts_failure_does_not_lose_samples_or_propagate(monkeypatch):
    await _seed_watchlist_post()
    client = FakeWarbleClient()
    client.batch_responses = [
        PostsBatchResult(
            posts=[make_post("wp_0000000001", metrics_at="2026-07-06T00:00:00.000Z")],
            missing_ids=[],
        )
    ]
    budget = BudgetTracker()
    state = collector_loop.CollectorState()
    alerter = Alerter(client, budget)

    async def fake_find_breakouts(session, post_ids):
        return {
            pid: EvaluationResult(
                state="BREAKOUT", score=0.9, reason="sustained_growth_breakout", sim_hours=0.0
            )
            for pid in post_ids
        }

    async def raising_fire_alerts(session, breakouts, sim_hours):
        raise RuntimeError("alerting exploded")

    monkeypatch.setattr(collector_loop, "find_breakouts", fake_find_breakouts)
    monkeypatch.setattr(alerter, "fire_alerts", raising_fire_alerts)

    await collector_loop._live_sample_tick(client, budget, state, alerter)  # must not raise

    async with get_session() as session:
        samples = await dao.get_samples_for_post(session, "wp_0000000001")
    assert len(samples) == 1


@pytest.mark.asyncio
async def test_tick_alerts_a_post_that_broke_out_and_has_since_cooled():
    """The recall regression, end to end.

    This post's momentum is long gone by the time the tick runs — its
    current state is not BREAKOUT — but it did break out, so the brand has
    to be told. The old behaviour (filter on the current state) reported
    nothing here at all, which is how 7 of 10 real breakouts went out
    unreported during a live run.
    """
    await _seed_watchlist_post("wp_0000000001")
    async with get_session() as session:
        # Climbs hard, then goes flat: BREAKOUT at sim hour 4, cooled by 8.
        for i, views in enumerate([2000, 3000, 4500, 6750, 10125, 15187, 15190, 15192, 15194]):
            await dao.insert_sample(
                session, post_id="wp_0000000001", views=views, likes=0, comments=0,
                metrics_at="2026-07-06T00:00:00.000Z", sim_hours=float(i), source="live",
            )
        await session.commit()

    client = FakeWarbleClient()
    client.batch_responses = [
        PostsBatchResult(
            posts=[make_post("wp_0000000001", metrics_at="2026-07-06T00:00:00.000Z")],
            missing_ids=[],
        )
    ]
    budget = BudgetTracker()
    state = collector_loop.CollectorState()
    state.current_sim_hours = 99.0  # "now" is far past the breakout
    alerter = Alerter(client, budget)

    await collector_loop._live_sample_tick(client, budget, state, alerter)

    assert [call[0] for call in client.post_alert_calls] == ["wp_0000000001"]

    async with get_session() as session:
        row = await session.get(AlertRow, "wp_0000000001")
    assert row is not None
    assert row.submitted is True
    # Stamped with when it actually broke out, not when we noticed.
    assert row.decided_sim_hours == 4.0


@pytest.mark.asyncio
async def test_tick_alerts_a_breakout_on_a_post_that_was_later_removed():
    """Removed posts are excluded from SAMPLING (no point polling a dead
    post) but must not be excluded from DETECTION — it broke out before it
    came down, and that's a breakout we owe the brand."""
    await _seed_watchlist_post("wp_0000000009")
    async with get_session() as session:
        for i, views in enumerate([2000, 3000, 4500, 6750, 10125, 15187]):
            await dao.insert_sample(
                session, post_id="wp_0000000009", views=views, likes=0, comments=0,
                metrics_at="2026-07-06T00:00:00.000Z", sim_hours=float(i), source="live",
            )
        await dao.mark_post_gone(session, post_id="wp_0000000009", sim_hours=6.0)
        await session.commit()

    async with get_session() as session:
        assert await dao.get_watchlist_post_ids(session) == []  # not sampled any more

    client = FakeWarbleClient()
    alerter = Alerter(client, BudgetTracker())
    state = collector_loop.CollectorState()
    state.current_sim_hours = 50.0

    await collector_loop._live_sample_tick(client, BudgetTracker(), state, alerter)

    assert [call[0] for call in client.post_alert_calls] == ["wp_0000000009"]


@pytest.mark.asyncio
async def test_tick_does_not_alert_a_post_that_never_broke_out():
    await _seed_watchlist_post("wp_0000000002")
    async with get_session() as session:
        for i, views in enumerate([1000, 1005, 1010, 1015, 1020]):
            await dao.insert_sample(
                session, post_id="wp_0000000002", views=views, likes=0, comments=0,
                metrics_at="2026-07-06T00:00:00.000Z", sim_hours=float(i), source="live",
            )
        await session.commit()

    client = FakeWarbleClient()
    client.batch_responses = [
        PostsBatchResult(
            posts=[make_post("wp_0000000002", metrics_at="2026-07-06T00:00:00.000Z")],
            missing_ids=[],
        )
    ]
    alerter = Alerter(client, BudgetTracker())

    await collector_loop._live_sample_tick(
        client, BudgetTracker(), collector_loop.CollectorState(), alerter
    )

    assert client.post_alert_calls == []


@pytest.mark.asyncio
async def test_repeated_ticks_never_double_alert_the_same_breakout():
    """find_breakouts re-offers every historical breakout on every tick —
    the dedupe layers have to make that free, or the 200/day alert cap
    would be burned down in an afternoon."""
    await _seed_watchlist_post("wp_0000000003")
    async with get_session() as session:
        for i, views in enumerate([2000, 3000, 4500, 6750, 10125, 15187]):
            await dao.insert_sample(
                session, post_id="wp_0000000003", views=views, likes=0, comments=0,
                metrics_at="2026-07-06T00:00:00.000Z", sim_hours=float(i), source="live",
            )
        await session.commit()

    client = FakeWarbleClient()
    budget = BudgetTracker()
    state = collector_loop.CollectorState()
    alerter = Alerter(client, budget)

    for _ in range(3):
        client.batch_responses = [
            PostsBatchResult(
                posts=[make_post("wp_0000000003", metrics_at="2026-07-06T00:00:00.000Z")],
                missing_ids=[],
            )
        ]
        await collector_loop._live_sample_tick(client, budget, state, alerter)

    assert len(client.post_alert_calls) == 1


@pytest.mark.asyncio
async def test_tick_failure_does_not_stop_subsequent_ticks(monkeypatch):
    call_count = 0

    async def flaky_tick(client, budget, state):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(collector_loop, "_heartbeat_tick", flaky_tick)
    monkeypatch.setattr(collector_loop, "HEARTBEAT_INTERVAL_S", 0.01)

    client = FakeWarbleClient()
    budget = BudgetTracker()
    state = collector_loop.CollectorState()

    task = asyncio.create_task(collector_loop.run_heartbeat_loop(client, budget, state))
    await asyncio.sleep(0.1)  # enough time for several 0.01s intervals
    state.shutdown.set()
    await task

    assert call_count >= 2  # the failing first tick did not stop later ones
