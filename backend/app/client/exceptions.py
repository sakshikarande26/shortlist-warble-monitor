class WarbleAPIError(Exception):
    """Base error for any non-2xx response from the Warble API."""

    def __init__(self, message: str, status_code: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class WarbleUnauthorizedError(WarbleAPIError):
    """401 — bad or missing API key. Not retried."""


class WarbleNotFoundError(WarbleAPIError):
    """404 — resource doesn't exist. Callers should drop the post/id."""


class WarblePayloadTooLargeError(WarbleAPIError):
    """413 — request body too large (e.g. batch request). Not retried."""


class WarbleRateLimitError(WarbleAPIError):
    """429 — rate limited and retries were exhausted."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: str | None = None,
        retry_after_seconds: float | None = None,
    ):
        super().__init__(message, status_code, body)
        self.retry_after_seconds = retry_after_seconds


class WarbleServerError(WarbleAPIError):
    """5xx — server error and retries were exhausted."""


class WarbleValidationError(Exception):
    """Client-side validation failure (e.g. malformed post_id). No request was made."""
