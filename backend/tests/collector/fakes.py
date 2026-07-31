from app.client.exceptions import WarbleRateLimitError
from app.client.models import (
    Alert,
    AlertCreateResponse,
    Creator,
    CreatorPostsPage,
    Me,
    Post,
    PostsBatchResult,
    RateLimitInfo,
)


class FakeWarbleClient:
    """Duck-types WarbleClient's public surface for sampler/loop tests.
    No network involved — every method returns pre-seeded canned data or
    raises a pre-seeded exception.
    """

    def __init__(self):
        self.last_rate_limit = RateLimitInfo(limit=250, remaining=210, reset=3600)
        self.calls: list[str] = []

        self.me_response: Me | Exception | None = None
        self.creators_response: list[Creator] | Exception = []
        # creator_id -> list of CreatorPostsPage, served in order per call
        self.pages_by_creator: dict[str, list[CreatorPostsPage]] = {}
        self._page_index: dict[str, int] = {}
        self.batch_responses: list[PostsBatchResult | Exception] = []
        self.alerts_response: list[Alert] | Exception = []
        self.post_alert_responses: list[AlertCreateResponse | Exception] = []
        self.post_alert_calls: list[tuple[str, str | None]] = []

    def _record_and_maybe_raise(self, response):
        if isinstance(response, Exception):
            raise response
        return response

    async def get_me(self) -> Me:
        self.calls.append("GET /me")
        return self._record_and_maybe_raise(self.me_response)

    async def get_creators(self) -> list[Creator]:
        self.calls.append("GET /creators")
        return self._record_and_maybe_raise(self.creators_response)

    async def get_creator_posts(self, creator_id: str, cursor: str | None = None) -> CreatorPostsPage:
        self.calls.append(f"GET /creators/{creator_id}/posts?cursor={cursor}")
        pages = self.pages_by_creator.get(creator_id, [])
        idx = self._page_index.get(creator_id, 0)
        if idx >= len(pages):
            return CreatorPostsPage(data=[], next_cursor=None)
        page = pages[idx]
        self._page_index[creator_id] = idx + 1
        return page

    async def get_posts_batch(self, ids: list[str]) -> PostsBatchResult:
        self.calls.append(f"GET /posts/batch?ids={','.join(ids)}")
        if not self.batch_responses:
            return PostsBatchResult(posts=[], missing_ids=list(ids))
        response = self.batch_responses.pop(0)
        return self._record_and_maybe_raise(response)

    async def get_alerts(self) -> list[Alert]:
        self.calls.append("GET /alerts")
        return self._record_and_maybe_raise(self.alerts_response)

    async def post_alert(self, post_id: str, note: str | None = None) -> AlertCreateResponse:
        self.calls.append(f"POST /alerts {post_id}")
        self.post_alert_calls.append((post_id, note))
        if not self.post_alert_responses:
            return AlertCreateResponse(
                ok=True,
                post_id=post_id,
                received_sim_hours=0.0,
                received_at="2026-07-06T00:00:00.000Z",
                duplicate=False,
            )
        response = self.post_alert_responses.pop(0)
        return self._record_and_maybe_raise(response)


def rate_limited_error(retry_after_seconds: float = 5.0) -> WarbleRateLimitError:
    return WarbleRateLimitError(
        "rate limited", status_code=429, body="", retry_after_seconds=retry_after_seconds
    )
