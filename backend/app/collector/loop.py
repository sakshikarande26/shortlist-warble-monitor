import asyncio
import logging
import signal
import time

from app.alerts.alerter import Alerter
from app.client.client import WarbleClient
from app.client.exceptions import WarbleAPIError, WarbleRateLimitError
from app.collector import sampler
from app.collector.budget import BudgetTracker
from app.config import settings
from app.db import dao
from app.db.base import engine, get_session
from app.detector.evaluate import evaluate_posts

logger = logging.getLogger("collector.loop")

# Cadences. The loop's own scheduling clock is wall-clock time, because the
# 250 req/rolling-hour budget it's pacing against is itself a wall-clock
# window (CLAUDE.md) — see the plan/README for the full cadence rationale.
DISCOVERY_INTERVAL_S = 6 * 3600
HEARTBEAT_INTERVAL_S = 30 * 60
LIVE_SAMPLE_INTERVAL_S = 15 * 60

DEFAULT_RATE_LIMIT_PAUSE_S = 60.0


class CollectorState:
    def __init__(self) -> None:
        self.shutdown = asyncio.Event()
        self.pause_until: float = 0.0
        self.current_sim_hours: float = 0.0

    def is_paused(self) -> bool:
        return time.monotonic() < self.pause_until

    def pause_for(self, seconds: float) -> None:
        self.pause_until = max(self.pause_until, time.monotonic() + seconds)

    async def sleep_or_stop(self, seconds: float) -> bool:
        """Sleep up to `seconds`, waking immediately on shutdown.

        Returns True if woken by shutdown (caller should stop looping).
        """
        try:
            await asyncio.wait_for(self.shutdown.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False


async def _handle_rate_limit(state: CollectorState, exc: WarbleRateLimitError) -> None:
    pause_seconds = exc.retry_after_seconds or DEFAULT_RATE_LIMIT_PAUSE_S
    logger.warning("rate limited, pausing all collector tasks for %.1fs", pause_seconds)
    state.pause_for(pause_seconds)


async def _heartbeat_tick(client: WarbleClient, budget: BudgetTracker, state: CollectorState) -> None:
    if state.is_paused():
        return
    try:
        me = await sampler.heartbeat(client, budget)
    except WarbleRateLimitError as exc:
        await _handle_rate_limit(state, exc)
        return
    except WarbleAPIError as exc:
        logger.error("heartbeat failed: %s", exc)
        return
    if me.sim_hours is not None:
        state.current_sim_hours = me.sim_hours


async def _discovery_tick(client: WarbleClient, budget: BudgetTracker, state: CollectorState) -> None:
    if state.is_paused():
        return
    if not budget.can_spend(1):
        logger.warning("budget too low, deferring discovery sweep to next cycle")
        return
    try:
        stats = await sampler.discover(client, budget, state.current_sim_hours)
    except WarbleRateLimitError as exc:
        await _handle_rate_limit(state, exc)
        return
    except WarbleAPIError as exc:
        logger.error("discovery sweep failed: %s", exc)
        return
    logger.info("discovery sweep: %d creators, %d posts seen", stats.creators_seen, stats.posts_seen)


async def _live_sample_tick(
    client: WarbleClient, budget: BudgetTracker, state: CollectorState, alerter: Alerter
) -> None:
    if state.is_paused():
        return
    if not budget.can_spend(1):
        logger.warning("budget too low, deferring live sampling to next cycle")
        return

    async with get_session() as session:
        post_ids = await dao.get_watchlist_post_ids(session)

    if not post_ids:
        return

    try:
        stats = await sampler.sample_live(client, budget, post_ids, state.current_sim_hours)
    except WarbleRateLimitError as exc:
        await _handle_rate_limit(state, exc)
        return
    except WarbleAPIError as exc:
        logger.error("live sampling failed: %s", exc)
        return
    logger.info(
        "live sampling: %d sampled, %d gone, %d chunks deferred",
        stats.sampled, stats.gone, stats.deferred_chunks,
    )

    async with get_session() as session:
        evaluations = await evaluate_posts(session, post_ids)
        breakouts = {pid: ev for pid, ev in evaluations.items() if ev.state == "BREAKOUT"}
        if not breakouts:
            return
        try:
            alert_stats = await alerter.fire_alerts(session, breakouts, state.current_sim_hours)
        except WarbleRateLimitError as exc:
            await _handle_rate_limit(state, exc)
            return
        except WarbleAPIError as exc:
            logger.error("alert firing failed: %s", exc)
            return
    logger.info(
        "alerts: %d fired, %d deduped, %d queued, %d failed",
        alert_stats.fired, alert_stats.deduped, alert_stats.queued, alert_stats.failed,
    )


async def run_heartbeat_loop(client: WarbleClient, budget: BudgetTracker, state: CollectorState) -> None:
    while not state.shutdown.is_set():
        await _heartbeat_tick(client, budget, state)
        if await state.sleep_or_stop(HEARTBEAT_INTERVAL_S):
            break


async def run_discovery_loop(client: WarbleClient, budget: BudgetTracker, state: CollectorState) -> None:
    while not state.shutdown.is_set():
        await _discovery_tick(client, budget, state)
        if await state.sleep_or_stop(DISCOVERY_INTERVAL_S):
            break


async def run_live_sample_loop(
    client: WarbleClient, budget: BudgetTracker, state: CollectorState, alerter: Alerter
) -> None:
    while not state.shutdown.is_set():
        await _live_sample_tick(client, budget, state, alerter)
        if await state.sleep_or_stop(LIVE_SAMPLE_INTERVAL_S):
            break


async def _startup_step(state: CollectorState, coro_factory):
    """Retry a startup step across 429s (honoring retry_after) instead of
    crashing the process before it's even scheduled anything."""
    while True:
        try:
            return await coro_factory()
        except WarbleRateLimitError as exc:
            pause_seconds = exc.retry_after_seconds or DEFAULT_RATE_LIMIT_PAUSE_S
            logger.warning("startup step rate limited, retrying in %.1fs", pause_seconds)
            if await state.sleep_or_stop(pause_seconds):
                raise


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    state = CollectorState()
    budget = BudgetTracker()
    client = WarbleClient(api_key=settings.warble_api_key, base_url=settings.warble_base_url)
    alerter = Alerter(client, budget)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, state.shutdown.set)

    async with client:
        # Startup sequence per spec: reconcile alert state, then a full
        # discovery sweep, unconditionally (budget is unknown before the
        # first response header is ever seen).
        me = await _startup_step(state, lambda: sampler.heartbeat(client, budget))
        if me.sim_hours is not None:
            state.current_sim_hours = me.sim_hours
        await _startup_step(
            state, lambda: sampler.sync_alerts(client, budget, state.current_sim_hours)
        )
        await _startup_step(
            state, lambda: sampler.discover(client, budget, state.current_sim_hours)
        )

        await asyncio.gather(
            run_heartbeat_loop(client, budget, state),
            run_discovery_loop(client, budget, state),
            run_live_sample_loop(client, budget, state, alerter),
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
