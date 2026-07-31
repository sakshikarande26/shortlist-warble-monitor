import asyncio
import time

import pytest

from app.alerts.alerter import Alerter
from app.client.models import Creator, Me, MeRateLimit, PostsBatchResult
from app.collector import loop as collector_loop
from app.collector.budget import BudgetTracker
from app.db import dao
from app.db.base import get_session
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

    assert state.current_sim_hours == 12.5


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

    async def raising_evaluate_posts(session, post_ids):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(collector_loop, "evaluate_posts", raising_evaluate_posts)

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

    async def fake_evaluate_posts(session, post_ids):
        return {
            pid: EvaluationResult(
                state="BREAKOUT", score=0.9, reason="sustained_growth_breakout", sim_hours=0.0
            )
            for pid in post_ids
        }

    async def raising_fire_alerts(session, breakouts, sim_hours):
        raise RuntimeError("alerting exploded")

    monkeypatch.setattr(collector_loop, "evaluate_posts", fake_evaluate_posts)
    monkeypatch.setattr(alerter, "fire_alerts", raising_fire_alerts)

    await collector_loop._live_sample_tick(client, budget, state, alerter)  # must not raise

    async with get_session() as session:
        samples = await dao.get_samples_for_post(session, "wp_0000000001")
    assert len(samples) == 1


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
