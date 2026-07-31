"""Wires the detector's BREAKOUT decisions to POST /v1/alerts and the local
alerts table. Two dedupe layers (local DB table + in-memory cache) and a
budget-aware queue-don't-drop policy — see the plan/README for the
rationale. No Warble endpoint is ever called except through the injected
client, and this module makes no decisions about *whether* to alert — that's
the detector's job; this module only ever alerts on what it's told.
"""

import datetime
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.client.client import POST_ID_PATTERN, WarbleClient
from app.client.exceptions import (
    WarbleAPIError,
    WarbleNotFoundError,
    WarblePayloadTooLargeError,
    WarbleRateLimitError,
    WarbleUnauthorizedError,
    WarbleValidationError,
)
from app.collector.budget import BudgetTracker
from app.db import dao
from app.detector.evaluate import EvaluationResult

logger = logging.getLogger("alerts.alerter")

# 401/404/413 (and a client-side validation failure that somehow slipped
# past our own pre-check) can never succeed on retry — per
# app/client/exceptions.py these are explicitly "not retried" / "callers
# should drop the post/id." Requeuing them would burn alert budget forever
# on a call that's dead on arrival. Anything else (WarbleServerError/5xx,
# etc.) is presumed transient and stays in the requeue path below.
_TERMINAL_ERRORS = (
    WarbleUnauthorizedError,
    WarbleNotFoundError,
    WarblePayloadTooLargeError,
    WarbleValidationError,
)


@dataclass
class PendingAlert:
    post_id: str
    note: str
    decided_sim_hours: float  # fixed at first-queued time; never re-stamped on retry


@dataclass
class AlertFireStats:
    fired: int = 0
    deduped: int = 0
    queued: int = 0
    failed: int = 0


def _build_note(evaluation: EvaluationResult) -> str:
    # TODO: replace with an LLM-generated brief (why + recommended play —
    # boost/reshare/extend deal, per docs/PRODUCT.md) once that layer exists.
    # This is the exact hook point: swap this function's body only.
    return f"Breakout detected: {evaluation.reason} (score={evaluation.score:.2f})"


def _parse_received_at(value: str | None) -> datetime.datetime | None:
    if value is None:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except ValueError:
        return None


class Alerter:
    def __init__(self, client: WarbleClient, budget: BudgetTracker):
        self.client = client
        self.budget = budget
        self._alerted: set[str] = set()  # layer 2: fast in-process cache
        self._pending: list[PendingAlert] = []

    async def fire_alerts(
        self, session: AsyncSession, breakouts: dict[str, EvaluationResult], sim_hours: float
    ) -> AlertFireStats:
        stats = AlertFireStats()

        already_alerted = await dao.get_alerted_post_ids(session)  # layer 1
        already_alerted |= self._alerted

        work: list[PendingAlert] = []
        for item in self._pending:
            if item.post_id in already_alerted:
                stats.deduped += 1
                continue
            work.append(item)
        self._pending = []

        for post_id, evaluation in breakouts.items():
            if post_id in already_alerted:
                stats.deduped += 1
                continue
            if any(p.post_id == post_id for p in work):
                continue  # already queued this tick via _pending carryover
            work.append(
                PendingAlert(post_id=post_id, note=_build_note(evaluation), decided_sim_hours=sim_hours)
            )

        for i, item in enumerate(work):
            if not POST_ID_PATTERN.match(item.post_id):
                logger.error("dropping malformed post_id %r, will not retry", item.post_id)
                stats.failed += 1
                continue

            if not self.budget.can_spend(1):
                remaining = work[i:]
                self._pending.extend(remaining)
                stats.queued += len(remaining)
                logger.warning("budget exhausted, queuing %d alert(s) for next tick", len(remaining))
                break

            try:
                response = await self.client.post_alert(item.post_id, note=item.note)
            except WarbleRateLimitError:
                self._pending.extend(work[i:])
                stats.queued += len(work[i:])
                self.budget.update(self.client.last_rate_limit)
                await dao.log_request(
                    session, endpoint="/alerts", method="POST", status_code=429,
                    sim_hours=sim_hours, rate_remaining=self._remaining(),
                )
                await session.commit()
                raise
            except _TERMINAL_ERRORS as exc:
                # Dead on arrival — drop it, log it to request_log so the
                # dashboard/README can show the system correctly stopped
                # retrying a dead post instead of silently going quiet on it.
                status_code = getattr(exc, "status_code", None) or 599
                logger.error(
                    "terminal error firing alert for %s (status %s), dropping — will not retry: %s",
                    item.post_id, status_code, exc,
                )
                stats.failed += 1
                self.budget.update(self.client.last_rate_limit)
                await dao.log_request(
                    session, endpoint="/alerts", method="POST",
                    status_code=status_code,
                    sim_hours=sim_hours, rate_remaining=self._remaining(),
                )
                await session.commit()
                continue
            except WarbleAPIError as exc:
                logger.error("failed to fire alert for %s: %s", item.post_id, exc)
                self._pending.append(item)
                stats.queued += 1
                self.budget.update(self.client.last_rate_limit)
                await dao.log_request(
                    session, endpoint="/alerts", method="POST",
                    status_code=exc.status_code or 599,
                    sim_hours=sim_hours, rate_remaining=self._remaining(),
                )
                await session.commit()
                continue

            self.budget.update(self.client.last_rate_limit)
            await dao.log_request(
                session, endpoint="/alerts", method="POST", status_code=200,
                sim_hours=sim_hours, rate_remaining=self._remaining(),
            )
            await dao.record_alert(
                session,
                post_id=item.post_id,
                decided_sim_hours=item.decided_sim_hours,
                note=item.note,
                submitted=True,
                received_sim_hours=response.sim_hours,
                received_at=_parse_received_at(response.received_at),
                api_reported_duplicate=bool(response.duplicate),
            )
            await session.commit()
            self._alerted.add(item.post_id)
            stats.fired += 1

        return stats

    def _remaining(self) -> int | None:
        rate_limit = self.client.last_rate_limit
        return rate_limit.remaining if rate_limit else None
