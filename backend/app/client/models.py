from pydantic import BaseModel, ConfigDict


class WarbleModel(BaseModel):
    """Base for all Warble response models.

    `extra="allow"` because we don't have a formal schema doc for this API —
    fields below are inferred from CLAUDE.md/docs; unknown real fields are
    kept rather than silently dropped so nothing is lost before models are
    corrected against live responses.
    """

    model_config = ConfigDict(extra="allow")


class RateLimitInfo(BaseModel):
    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None


class MeRateLimit(BaseModel):
    limit_per_hour: int
    used: int
    remaining: int


class Me(WarbleModel):
    label: str
    activated: bool
    activation_note: str | None = None
    sim_hours: float | None = None
    server_time: str | None = None
    clock_multiplier: float | None = None
    key_expires_at: str | None = None
    activation_deadline: str | None = None
    rate_limit: MeRateLimit | None = None


class Creator(WarbleModel):
    id: str
    name: str | None = None
    handle: str | None = None


class Post(WarbleModel):
    id: str
    creator_id: str | None = None
    # Sim-clock timestamp of when these metrics were captured — NOT wall-clock.
    # Exact field name to be confirmed against a live response.
    metrics_at: str | int | float | None = None
    views: int | None = None
    likes: int | None = None
    shares: int | None = None
    comments: int | None = None


class CreatorPostsPage(WarbleModel):
    posts: list[Post]
    next_cursor: str | None = None


class PostsBatchResult(BaseModel):
    """Not a raw API model: `posts` is what the API returned, `missing_ids`
    is computed client-side (requested - returned) since the API may
    silently omit ids from a batch response.
    """

    posts: list[Post]
    missing_ids: list[str]


class Alert(WarbleModel):
    id: str | None = None
    post_id: str
    note: str | None = None


class AlertCreateResponse(WarbleModel):
    id: str | None = None
    post_id: str
    note: str | None = None
    # Best-effort/inferred, like Me before the live /me probe corrected it —
    # no confirmed docs for this response shape yet. duplicate signals the
    # server already had this post_id recorded (CLAUDE.md: idempotent per
    # post, first timestamp is final).
    duplicate: bool | None = None
    sim_hours: float | None = None
    received_at: str | None = None
