from pydantic import BaseModel, ConfigDict


class WarbleModel(BaseModel):
    """Base for all Warble response models.

    `extra="forbid"` on purpose: these shapes are now taken directly from
    the real API docs, so any field the server sends that we don't expect
    (or any required field it omits) should fail loudly at parse time
    instead of silently vanishing.
    """

    model_config = ConfigDict(extra="forbid")


class RateLimitInfo(BaseModel):
    """Parsed from response headers, not a documented JSON body shape —
    stays lenient since header presence isn't governed by the same contract
    as the JSON payloads below."""

    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None


class MeRateLimit(WarbleModel):
    limit_per_hour: int
    used: int
    remaining: int


class Me(WarbleModel):
    label: str
    activated: bool
    activation_note: str | None = None  # present only when activated is false
    sim_hours: float
    server_time: str
    clock_multiplier: float
    key_expires_at: str | None  # required key, null until activated
    activation_deadline: str | None = None  # present only when activated is false
    rate_limit: MeRateLimit


class Creator(WarbleModel):
    id: str  # wc_<10 lowercase hex>
    handle: str
    name: str
    category: str
    bio: str
    platform: str
    followers: int


class PostMetrics(WarbleModel):
    views: int
    likes: int
    comments: int


class Post(WarbleModel):
    id: str  # wp_<10 lowercase hex>
    creator_id: str
    creator_handle: str
    creator_name: str
    platform: str
    published_at: str
    caption: str
    metrics: PostMetrics
    # Only one of these is ever present on a given response: metrics_cached_at
    # on the (cached) listing endpoint, metrics_at on the live endpoints.
    metrics_cached_at: str | None = None
    metrics_at: str | None = None


class CreatorPostsPage(WarbleModel):
    data: list[Post]
    next_cursor: str | None


class PostsBatchResult(BaseModel):
    """Not a raw API model: `posts` is what the API returned, `missing_ids`
    is computed client-side (requested - returned) since the API may
    silently omit ids from a batch response.
    """

    posts: list[Post]
    missing_ids: list[str]


class Alert(WarbleModel):
    post_id: str
    note: str | None
    received_sim_hours: float
    received_at: str


class AlertCreateResponse(WarbleModel):
    ok: bool
    post_id: str
    received_sim_hours: float  # original receipt time, unchanged on duplicates
    received_at: str
    duplicate: bool
