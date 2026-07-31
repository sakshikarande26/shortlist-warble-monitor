import pytest
from sqlalchemy import select

from app.alerts.alerter import Alerter
from app.client.exceptions import WarbleNotFoundError
from app.collector.budget import BudgetTracker
from app.db import dao
from app.db.base import get_session
from app.db.models import Alert as AlertRow
from app.db.models import RequestLog
from app.detector.evaluate import EvaluationResult
from tests.collector.fakes import FakeWarbleClient


async def _seed_post(post_id: str = "wp_0000000001") -> None:
    async with get_session() as session:
        await dao.upsert_creator(
            session, id="wc_0000000001", handle="h", name="n", platform="p",
            followers=10_000, fetched_at_sim_hours=0.0,
        )
        await dao.upsert_post(
            session, id=post_id, creator_id="wc_0000000001",
            platform="p", first_seen_sim_hours=0.0,
        )
        await session.commit()


def breakout(post_id: str, sim_hours: float = 10.0) -> dict[str, EvaluationResult]:
    return {
        post_id: EvaluationResult(
            state="BREAKOUT", score=0.9, reason="sustained_growth_breakout", sim_hours=sim_hours
        )
    }


@pytest.mark.asyncio
async def test_clean_breakout_fires_once():
    await _seed_post()
    client = FakeWarbleClient()
    alerter = Alerter(client, BudgetTracker())

    async with get_session() as session:
        stats = await alerter.fire_alerts(session, breakout("wp_0000000001"), sim_hours=10.0)

    assert stats.fired == 1
    assert stats.deduped == 0
    assert len(client.post_alert_calls) == 1
    assert client.post_alert_calls[0][0] == "wp_0000000001"

    async with get_session() as session:
        row = await session.get(AlertRow, "wp_0000000001")
    assert row is not None
    assert row.submitted is True
    assert row.is_duplicate is False
    assert row.decided_sim_hours == 10.0


@pytest.mark.asyncio
async def test_duplicate_does_not_double_fire():
    await _seed_post()
    client = FakeWarbleClient()
    alerter = Alerter(client, BudgetTracker())

    async with get_session() as session:
        await alerter.fire_alerts(session, breakout("wp_0000000001"), sim_hours=10.0)

    async with get_session() as session:
        stats2 = await alerter.fire_alerts(session, breakout("wp_0000000001"), sim_hours=11.0)

    assert stats2.fired == 0
    assert stats2.deduped == 1
    assert len(client.post_alert_calls) == 1  # still just the one real call

    async with get_session() as session:
        row = await session.get(AlertRow, "wp_0000000001")
    assert row.decided_sim_hours == 10.0  # first decision stands


@pytest.mark.asyncio
async def test_over_budget_breakout_queues_then_fires():
    await _seed_post()
    client = FakeWarbleClient()
    budget = BudgetTracker(reserve=40, ceiling=250)
    budget._last_remaining = 40  # remaining() == 0, can_spend(1) is False
    alerter = Alerter(client, budget)

    async with get_session() as session:
        stats1 = await alerter.fire_alerts(session, breakout("wp_0000000001"), sim_hours=10.0)

    assert stats1.fired == 0
    assert stats1.queued == 1
    assert client.post_alert_calls == []

    budget._last_remaining = 250  # budget recovers

    async with get_session() as session:
        stats2 = await alerter.fire_alerts(session, {}, sim_hours=99.0)

    assert stats2.fired == 1
    assert len(client.post_alert_calls) == 1

    async with get_session() as session:
        row = await session.get(AlertRow, "wp_0000000001")
    assert row.decided_sim_hours == 10.0  # preserved from when it was first queued


@pytest.mark.asyncio
async def test_terminal_error_drops_after_one_attempt_not_requeued():
    await _seed_post()
    client = FakeWarbleClient()
    client.post_alert_responses = [
        WarbleNotFoundError("post gone", status_code=404, body="")
    ]
    budget = BudgetTracker()
    alerter = Alerter(client, budget)

    async with get_session() as session:
        stats1 = await alerter.fire_alerts(session, breakout("wp_0000000001"), sim_hours=10.0)

    assert stats1.failed == 1
    assert stats1.queued == 0
    assert len(client.post_alert_calls) == 1

    async with get_session() as session:
        row = await session.get(AlertRow, "wp_0000000001")
        result = await session.execute(select(RequestLog).where(RequestLog.endpoint == "/alerts"))
        log_rows = result.scalars().all()
    assert row is None  # never recorded as a real alert
    assert any(r.status_code == 404 for r in log_rows)  # terminal drop was logged

    # A subsequent tick must NOT retry it — it was dropped, not queued.
    async with get_session() as session:
        stats2 = await alerter.fire_alerts(session, {}, sim_hours=11.0)

    assert stats2.fired == 0
    assert stats2.queued == 0
    assert len(client.post_alert_calls) == 1  # still just the one attempt


@pytest.mark.asyncio
async def test_malformed_post_id_rejected_pre_call():
    client = FakeWarbleClient()
    alerter = Alerter(client, BudgetTracker())

    async with get_session() as session:
        stats = await alerter.fire_alerts(session, breakout("not-a-valid-id"), sim_hours=10.0)

    assert stats.failed == 1
    assert stats.fired == 0
    assert client.calls == []
    assert client.post_alert_calls == []
