"""Response models for the read-only dashboard API. Presentation-layer
only — status labels and grouping live here, not in the detector.
"""

from pydantic import BaseModel

from app.detector.states import PostState

STATE_LABELS: dict[PostState, str] = {
    "BREAKOUT": "Act now",
    "RISING": "Watch closely",
    "WATCH": "Rising",
    "COOLING": "Cooling",
    "NEW": "Quiet",
}

NEEDS_ATTENTION_STATES: frozenset[PostState] = frozenset({"BREAKOUT", "RISING"})


class CreatorContext(BaseModel):
    id: str
    handle: str
    name: str
    followers: int
    category: str | None
    platform: str


class HomePost(BaseModel):
    post_id: str
    creator_handle: str
    creator_followers: int
    caption: str | None
    views: int
    likes: int
    comments: int
    state: PostState
    score: float
    status_label: str
    needs_attention: bool
    is_gone: bool


class HomeResponse(BaseModel):
    attention_queue: list[HomePost]
    other_posts: list[HomePost]


class TrajectoryPoint(BaseModel):
    sim_hours: float
    views: int


class EvidenceDetail(BaseModel):
    sim_hours: float
    absolute_gain: int
    relative_growth_pct: float
    velocity: float
    follower_velocity: float
    trajectory_ratio: float


class PostDetail(BaseModel):
    post_id: str
    caption: str | None
    published_at: str | None
    platform: str
    is_gone: bool
    gone_sim_hours: float | None
    creator: CreatorContext
    trajectory: list[TrajectoryPoint]
    state: PostState
    score: float
    status_label: str
    reason: str
    evidence: EvidenceDetail | None
