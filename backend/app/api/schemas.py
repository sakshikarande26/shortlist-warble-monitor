"""Response models for the read-only dashboard API. Presentation-layer
only — the canonical status vocabulary and comparative-ranking logic live
in routes.py, not the detector.
"""

from typing import Literal

from pydantic import BaseModel

from app.detector.states import PostState


class CreatorContext(BaseModel):
    id: str
    handle: str
    name: str
    followers: int
    category: str | None
    platform: str


class EvidenceDetail(BaseModel):
    sim_hours: float
    absolute_gain: int
    relative_growth_pct: float
    velocity: float
    follower_velocity: float
    trajectory_ratio: float
    window_hours: float | None  # duration of the latest interval, for "+3,420 views in 2h"
    consecutive_qualifying_checks: int  # how many checks in a row showed qualifying momentum
    # Comparative-to-creator pace. "creator" = compared against this
    # creator's OTHER posts at a similar age; "self" = fell back to this
    # post's own trajectory_ratio because the creator has too few other
    # posts to build a baseline from. Both null when neither comparison can
    # be trusted ("not enough history") — never a fabricated number. Never
    # rendered as a standalone stat — the frontend folds it into one
    # sentence, same as trajectory_ratio already is.
    creator_pace_ratio: float | None = None
    creator_pace_basis: Literal["creator", "self"] | None = None


class HomePost(BaseModel):
    post_id: str
    creator_handle: str
    creator_followers: int
    caption: str | None
    published_at: str | None
    views: int
    likes: int
    comments: int
    state: PostState
    score: float
    reason: str
    status_label: str  # canonical: "Taking off" / "Worth watching" / "Steady" / "Unavailable"
    evidence: EvidenceDetail | None  # grounds each card's performance line in this post's own numbers
    is_gone: bool
    latest_sim_hours: float | None
    sparkline: list[int]  # last few deduped view counts, for a small trend line — not full history


class HomeResponse(BaseModel):
    # Both already ranked and capped server-side, and each filtered to
    # exactly the status_label its section is named for — the UI renders
    # them as given, it never re-derives groupings from state client-side.
    act_now: list[HomePost]
    watch_closely: list[HomePost]
    total_posts: int  # distinguishes "nothing tracked yet" from "nothing moving right now"
    unavailable_count: int
    current_sim_hours: float | None


class TrajectoryPoint(BaseModel):
    sim_hours: float
    views: int


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
    alert_sent: bool  # whether an official alert was ever submitted for this post
    breakout_sim_hours: float | None  # when this post first reached BREAKOUT, if ever
    current_sim_hours: float | None


class CreatorRosterPost(BaseModel):
    post_id: str
    caption: str | None
    state: PostState
    status_label: str
    score: float
    evidence: EvidenceDetail | None  # grounds "why it's strongest": gain, window, baseline comparison
    sparkline: list[int]


class CreatorRosterEntry(BaseModel):
    id: str
    handle: str
    followers: int
    active_post_count: int
    taking_off_count: int
    worth_watching_count: int
    needs_attention_count: int  # = taking_off_count + worth_watching_count
    strongest_post: CreatorRosterPost | None  # by current momentum, not lifetime views; null if none
    latest_sim_hours: float | None  # most recent check across this creator's active posts


class CreatorsResponse(BaseModel):
    creators: list[CreatorRosterEntry]
    current_sim_hours: float | None


class CreatorPostSummary(BaseModel):
    post_id: str
    caption: str | None
    published_at: str | None
    state: PostState
    status_label: str
    score: float
    evidence: EvidenceDetail | None
    is_gone: bool
    latest_sim_hours: float | None
    sparkline: list[int]


class CreatorStats(BaseModel):
    posts_tracked: int
    posts_that_took_off: int  # ever reached BREAKOUT, not just currently in it
    typical_views: int  # median latest views across active posts


class CreatorDetailResponse(BaseModel):
    creator: CreatorContext
    active_posts: list[CreatorPostSummary]
    unavailable_posts: list[CreatorPostSummary]
    stats: CreatorStats
    current_sim_hours: float | None


class NotablePost(BaseModel):
    post_id: str
    creator_handle: str
    caption: str | None
    status_label: str
    sim_hours: float


class AlertSummary(BaseModel):
    post_id: str
    creator_handle: str
    caption: str | None
    sim_hours: float


class SystemStatus(BaseModel):
    """Backs the right-hand panel's idle state — real system context
    instead of a placeholder, when no post is selected."""

    posts_tracked: int
    last_checked_sim_hours: float | None
    most_notable_post: NotablePost | None  # most recently-updated Taking off / Worth watching post
    most_recent_alert: AlertSummary | None


class BreakoutLogEntry(BaseModel):
    post_id: str
    creator_handle: str
    caption: str | None
    breakout_sim_hours: float  # when it FIRST reached BREAKOUT on replay
    breakout_at: str | None  # real timestamp of that reading, straight off the sample
    views_at_breakout: int
    peak_views: int
    growth_multiple: float | None  # peak / at-breakout; None when not computable
    current_status_label: str  # may have cooled since
    alert_submitted: bool  # from the alerts table, never inferred


class BreakoutLogResponse(BaseModel):
    entries: list[BreakoutLogEntry]
    current_sim_hours: float | None
