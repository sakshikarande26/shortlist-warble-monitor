import asyncio
import re
from types import TracebackType

import httpx

from app.client.exceptions import (
    WarbleAPIError,
    WarbleNotFoundError,
    WarblePayloadTooLargeError,
    WarbleRateLimitError,
    WarbleServerError,
    WarbleUnauthorizedError,
    WarbleValidationError,
)
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

POST_ID_PATTERN = re.compile(r"^wp_[0-9a-f]{10}$")

DEFAULT_BASE_URL = "https://warble.shortlistos.com/v1"
MAX_BATCH_IDS = 10
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 0.5


class WarbleClient:
    """Async client for the Warble API.

    Every response's rate-limit headers are recorded on `last_rate_limit`,
    win or lose, so a caller (e.g. a polling scheduler) can self-throttle
    against the 250 req/rolling-hour budget without this client having to
    make scheduling decisions itself.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.AsyncClient | None = None,
    ):
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )
        self.last_rate_limit: RateLimitInfo | None = None

    async def __aenter__(self) -> "WarbleClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _record_rate_limit(self, response: httpx.Response) -> None:
        headers = response.headers

        def _int_or_none(value: str | None) -> int | None:
            return int(value) if value is not None else None

        self.last_rate_limit = RateLimitInfo(
            limit=_int_or_none(headers.get("X-RateLimit-Limit")),
            remaining=_int_or_none(headers.get("X-RateLimit-Remaining")),
            reset=_int_or_none(headers.get("X-RateLimit-Reset")),
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict | None = None,
    ) -> httpx.Response:
        attempt = 0
        while True:
            response = await self._client.request(method, path, params=params, json=json)
            self._record_rate_limit(response)

            if response.status_code < 400:
                return response

            if response.status_code == 401:
                raise WarbleUnauthorizedError(
                    "Unauthorized — check WARBLE_API_KEY",
                    status_code=401,
                    body=response.text,
                )

            if response.status_code == 404:
                raise WarbleNotFoundError(
                    f"Not found: {path}", status_code=404, body=response.text
                )

            if response.status_code == 413:
                raise WarblePayloadTooLargeError(
                    "Payload too large", status_code=413, body=response.text
                )

            if response.status_code == 429:
                if attempt >= MAX_RETRIES:
                    raise WarbleRateLimitError(
                        "Rate limited and retries exhausted",
                        status_code=429,
                        body=response.text,
                        retry_after_seconds=self._retry_after_seconds(response),
                    )
                await asyncio.sleep(self._retry_after_seconds(response) or BACKOFF_BASE_SECONDS)
                attempt += 1
                continue

            if response.status_code >= 500:
                if attempt >= MAX_RETRIES:
                    raise WarbleServerError(
                        f"Server error {response.status_code} and retries exhausted",
                        status_code=response.status_code,
                        body=response.text,
                    )
                await asyncio.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
                attempt += 1
                continue

            raise WarbleAPIError(
                f"Unexpected status {response.status_code}",
                status_code=response.status_code,
                body=response.text,
            )

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return float(retry_after)
            except ValueError:
                pass
        try:
            body = response.json()
            value = body.get("retry_after_seconds")
            if value is not None:
                return float(value)
        except ValueError:
            pass
        return None

    async def get_me(self) -> Me:
        response = await self._request("GET", "/me")
        return Me.model_validate(response.json())

    async def get_creators(self) -> list[Creator]:
        response = await self._request("GET", "/creators")
        return [Creator.model_validate(item) for item in response.json()]

    async def get_creator_posts(
        self, creator_id: str, cursor: str | None = None
    ) -> CreatorPostsPage:
        params = {"cursor": cursor} if cursor else None
        response = await self._request(
            "GET", f"/creators/{creator_id}/posts", params=params
        )
        return CreatorPostsPage.model_validate(response.json())

    async def get_post(self, post_id: str) -> Post:
        response = await self._request("GET", f"/posts/{post_id}")
        return Post.model_validate(response.json())

    async def get_posts_batch(self, ids: list[str]) -> PostsBatchResult:
        if not ids:
            raise ValueError("ids must be non-empty")
        if len(ids) > MAX_BATCH_IDS:
            raise ValueError(f"ids must contain at most {MAX_BATCH_IDS} items, got {len(ids)}")

        response = await self._request("GET", "/posts/batch", params={"ids": ",".join(ids)})
        posts = [Post.model_validate(item) for item in response.json()]
        returned_ids = {post.id for post in posts}
        missing_ids = [post_id for post_id in ids if post_id not in returned_ids]
        return PostsBatchResult(posts=posts, missing_ids=missing_ids)

    async def get_alerts(self) -> list[Alert]:
        response = await self._request("GET", "/alerts")
        return [Alert.model_validate(item) for item in response.json()]

    async def post_alert(self, post_id: str, note: str | None = None) -> AlertCreateResponse:
        if not POST_ID_PATTERN.match(post_id):
            raise WarbleValidationError(
                f"post_id {post_id!r} does not match ^wp_[0-9a-f]{{10}}$"
            )
        payload: dict = {"post_id": post_id}
        if note is not None:
            payload["note"] = note
        response = await self._request("POST", "/alerts", json=payload)
        return AlertCreateResponse.model_validate(response.json())
