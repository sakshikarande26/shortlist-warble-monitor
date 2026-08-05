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
from app.detector.evaluate import find_breakouts

logger = logging.getLogger("collector.loop")

# Fault isolation, top to bottom:
#  - Each tick (heartbeat/discovery/live-sampling) runs inside its own
#    try/except in the run_*_loop wrappers below, so a bug in one tick is
#    logged and the loop moves on to the next scheduled run instead of
#    taking the whole process down.
#  - Within the live-sampling tick specifically: capture (sample_live) runs
#    and commits FIRST, then detection (evaluate_posts) and alerting
#    (fire_alerts) run in a second, separately-guarded step. Raw samples are
#    irreplaceable — once a moment passes without being captured, it's gone
#    for good. A detection or alerting bug, on the other hand, is fully
#    recoverable: the samples are already safely on disk, so we can fix the
#    bug and re-evaluate that same stored history later. So detection/
#    alerting failures are never allowed to look like — or cause — a
#    sampling failure.

# Cadences. The loop's own scheduling clock is wall-clock time, because the
# 250 req/rolling-hour budget it's pacing against is itself a wall-clock
# window (CLAUDE.md) — see the plan/README for the full cadence rationale.
DISCOVERY_INTERVAL_S = 6 * 3600
HEARTBEAT_INTERVAL_S = 30 * 60
LIVE_SAMPLE_INTERVAL_S = 15 * 60

DEFAULT_RATE_LIMIT_PAUSE_S = 60.0


class CollectorState:
    """Shared scheduling state, including this process's view of the sim clock.

    The sim clock is ANCHORED at each heartbeat and interpolated in between,
    rather than frozen at whatever /me last said. That matters more than it
    sounds:

    /me is the only source of sim_hours, and we only call it every 30
    minutes (it costs budget). Live sampling runs every 15. So freezing the
    value meant two consecutive live rounds — genuinely 15 minutes and real
    view growth apart — were both stamped with the *same* sim_hours. The
    detector then deduplicates by timestamp (momentum._dedupe_samples), so
    one of every two rounds was silently collapsed away. Against live data
    that showed up as 283 stored samples per post flattening to 151 usable
    points: half the resolution the collector actually paid for, and every
    breakout confirmed roughly one full round later than the evidence
    allowed. Latency is scored, so that was real cost.

    Interpolating between anchors costs nothing, needs no extra requests,
    and is what the clock is genuinely doing — /me reports a multiplier, and
    every heartbeat re-anchors so error can't accumulate.
    """

    def __init__(self) -> None:
        self.shutdown = asyncio.Event()
        self.pause_until: float = 0.0
        self._sim_anchor_hours: float = 0.0
        self._sim_anchor_at: float = time.monotonic()
        self._clock_multiplier: float = 1.0

    @property
    def current_sim_hours(self) -> float:
        elapsed_real_hours = (time.monotonic() - self._sim_anchor_at) / 3600.0
        return self._sim_anchor_hours + elapsed_real_hours * self._clock_multiplier

    @current_sim_hours.setter
    def current_sim_hours(self, sim_hours: float) -> None:
        """Re-anchor. Assigning a known-good sim_hours (from /me, or from a
        test) restarts the interpolation from that point."""
        self.anchor_sim_clock(sim_hours)

    def anchor_sim_clock(self, sim_hours: float, clock_multiplier: float | None = None) -> None:
        self._sim_anchor_hours = sim_hours
        self._sim_anchor_at = time.monotonic()
        # Only ever taken from the server; a missing/zero value leaves the
        # last known rate in place rather than stalling the clock at 0x.
        if clock_multiplier:
            self._clock_multiplier = clock_multiplier

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
        state.anchor_sim_clock(me.sim_hours, me.clock_multiplier)


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

    # Capture. This is the irreplaceable part — sample_live() commits its
    # writes before returning, so by the time we get past this block, this
    # tick's samples are durably on disk no matter what happens next.
    #
    # An empty watchlist skips capture but must NOT skip the tick: detection
    # runs over stored history, which exists whether or not there was
    # anything new to sample this round. Returning early here meant a
    # tick with nothing to poll also did no detecting and fired no alerts.
    if post_ids:
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

    # Detection + alerting. Best-effort from here on: a detector bug, a DB
    # hiccup, or an alert-firing failure must never propagate out of this
    # tick — the samples above are already safe, and a stored history can
    # always be re-evaluated on a later tick once the bug is fixed.
    try:
        async with get_session() as session:
            # Two different scopes, deliberately. We SAMPLED only the active
            # watchlist above (post_ids) — no point spending requests on a
            # post that's been taken down. But we DETECT over every post we
            # have history for, including removed ones: a post that broke out
            # and was later deleted still broke out.
            #
            # And "every post that has EVER broken out", not just those in
            # BREAKOUT at this instant. Momentum fades between 15-minute
            # ticks, and a post that cooled before we looked is still one the
            # brand needed to hear about — filtering on the current state was
            # silently dropping those on the floor. The alerter dedupes
            # against the alerts table, so already-reported posts cost
            # nothing; this only ever adds the ones we'd otherwise miss.
            breakouts = await find_breakouts(session, await dao.get_all_post_ids(session))
            if not breakouts:
                return
            alert_stats = await alerter.fire_alerts(session, breakouts, state.current_sim_hours)
    except WarbleRateLimitError as exc:
        await _handle_rate_limit(state, exc)
        return
    except Exception:
        logger.exception(
            "detection/alerting failed after live sampling succeeded — "
            "samples are safe, will retry detection next cycle"
        )
        return
    logger.info(
        "alerts: %d fired, %d deduped, %d queued, %d failed",
        alert_stats.fired, alert_stats.deduped, alert_stats.queued, alert_stats.failed,
    )


async def run_heartbeat_loop(client: WarbleClient, budget: BudgetTracker, state: CollectorState) -> None:
    # Sleep first: main()'s startup sequence already ran a heartbeat, and
    # ticking again immediately would spend a call to re-read what we just
    # read. Same reasoning as the discovery loop below.
    while not state.shutdown.is_set():
        if await state.sleep_or_stop(HEARTBEAT_INTERVAL_S):
            break
        try:
            await _heartbeat_tick(client, budget, state)
        except Exception:
            # Fault isolation: an unexpected failure in one tick must not
            # kill this loop (or, via asyncio.gather, the other two loops).
            # Log it and pick back up on the next scheduled run.
            logger.exception("heartbeat tick failed unexpectedly, will retry next cycle")


async def run_discovery_loop(client: WarbleClient, budget: BudgetTracker, state: CollectorState) -> None:
    # Sleep before the first tick. main() already performed a full startup
    # discovery sweep, so ticking immediately here ran a second identical
    # sweep seconds later — roughly 40 wasted calls against a 250/hour
    # ceiling, which is what starved live sampling into "budget too low,
    # deferring" on the very first cycle.
    while not state.shutdown.is_set():
        if await state.sleep_or_stop(DISCOVERY_INTERVAL_S):
            break
        try:
            await _discovery_tick(client, budget, state)
        except Exception:
            logger.exception("discovery tick failed unexpectedly, will retry next cycle")


async def run_live_sample_loop(
    client: WarbleClient, budget: BudgetTracker, state: CollectorState, alerter: Alerter
) -> None:
    while not state.shutdown.is_set():
        try:
            await _live_sample_tick(client, budget, state, alerter)
        except Exception:
            logger.exception("live-sampling tick failed unexpectedly, will retry next cycle")
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
            state.anchor_sim_clock(me.sim_hours, me.clock_multiplier)
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
