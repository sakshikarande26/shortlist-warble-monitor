import time

import pytest

from app.client.models import Creator, Me
from app.collector import loop as collector_loop
from app.collector.budget import BudgetTracker
from tests.collector.fakes import FakeWarbleClient, rate_limited_error


@pytest.mark.asyncio
async def test_heartbeat_tick_updates_sim_hours():
    client = FakeWarbleClient()
    client.me_response = Me(label="x", activated=True, sim_hours=12.5)
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
    client.creators_response = [Creator(id="wc_0000000001", name="n", handle="h")]
    await collector_loop._discovery_tick(client, budget, state)
    assert not any(c.startswith("GET /creators") for c in client.calls)


@pytest.mark.asyncio
async def test_discovery_tick_skips_when_budget_exhausted():
    client = FakeWarbleClient()
    client.creators_response = [Creator(id="wc_0000000001", name="n", handle="h")]
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
