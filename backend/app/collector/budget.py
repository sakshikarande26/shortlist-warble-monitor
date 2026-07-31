from app.client.models import RateLimitInfo

CEILING_PER_HOUR = 250
RESERVE = 40
EFFECTIVE_CEILING = CEILING_PER_HOUR - RESERVE  # 210


class BudgetTracker:
    """Tracks how many requests we can still safely spend in the current
    rolling hour.

    Deliberately does NOT reimplement a local rolling-hour window: the
    server already tracks that (CLAUDE.md: 250 req/rolling hour, every
    admitted call counts) and reports it via X-RateLimit-Remaining on every
    response. We just read that off `client.last_rate_limit` and subtract a
    safety reserve, so our view can never drift from the server's.
    """

    def __init__(self, reserve: int = RESERVE, ceiling: int = CEILING_PER_HOUR):
        self.reserve = reserve
        self.ceiling = ceiling
        # Optimistic default before we've seen any response headers yet —
        # only the unconditional startup calls (sync_alerts, discover) run
        # before this is ever updated. remaining() subtracts the reserve on
        # top of this, so start at the full ceiling here (not ceiling-reserve,
        # which would double-subtract).
        self._last_remaining = ceiling

    def update(self, rate_limit: RateLimitInfo | None) -> None:
        if rate_limit is not None and rate_limit.remaining is not None:
            self._last_remaining = rate_limit.remaining

    def remaining(self) -> int:
        return max(0, self._last_remaining - self.reserve)

    def can_spend(self, n: int) -> bool:
        return self.remaining() >= n
