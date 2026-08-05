// Mirrors backend/app/api/schemas.py exactly. If the API shape changes,
// update here first — everything else in the app is typed off this file.

export type PostState = "NEW" | "WATCH" | "RISING" | "BREAKOUT" | "COOLING";

export interface CreatorContext {
  id: string;
  handle: string;
  name: string;
  followers: number;
  category: string | null;
  platform: string;
}

export interface EvidenceDetail {
  sim_hours: number;
  absolute_gain: number;
  relative_growth_pct: number;
  velocity: number;
  follower_velocity: number;
  trajectory_ratio: number;
  window_hours: number | null; // duration of the latest interval, for "+3,420 views in 2h"
  consecutive_qualifying_checks: number;
  // Comparative-to-creator pace. "creator" = compared against this
  // creator's other posts at a similar age; "self" = fell back to this
  // post's own trajectory_ratio (too few other posts to build a baseline
  // from). Both null when neither comparison can be trusted — "not enough
  // history," never a fabricated number.
  creator_pace_ratio: number | null;
  creator_pace_basis: "creator" | "self" | null;
}

export interface HomePost {
  post_id: string;
  creator_handle: string;
  creator_followers: number;
  caption: string | null;
  published_at: string | null;
  views: number;
  likes: number;
  comments: number;
  state: PostState;
  score: number;
  reason: string;
  status_label: string;
  evidence: EvidenceDetail | null;
  is_gone: boolean;
  latest_sim_hours: number | null;
  // Real ISO timestamp of the latest reading — used to show an actual
  // date once something is too old for a relative phrase.
  latest_metrics_at: string | null;
  sparkline: number[];
}

export interface HomeStateTransition {
  post: HomePost;
  from_state: PostState;
  to_state: PostState;
  from_status_label: string;
  to_status_label: string;
  changed_sim_hours: number;
  changed_at: string | null;
}

export interface HomeResponse {
  // Already ranked and capped server-side — rendered as given, not
  // re-derived from state client-side.
  act_now: HomePost[];
  watch_closely: HomePost[];
  // Raw detector state "NEW" (too little history yet), regardless of
  // status_label — the Momentum Board's "New" group.
  new_posts: HomePost[];
  unavailable_posts: HomePost[];
  recent_changes: HomeStateTransition[];
  window_start: string | null;
  window_end: string | null;
  window_type: "last_6_hours" | "since_last_visit";
  total_posts: number;
  unavailable_count: number;
  current_sim_hours: number | null;
}

export interface TrajectoryPoint {
  sim_hours: number;
  views: number;
}

export interface PostDetail {
  post_id: string;
  caption: string | null;
  published_at: string | null;
  platform: string;
  is_gone: boolean;
  gone_sim_hours: number | null;
  creator: CreatorContext;
  trajectory: TrajectoryPoint[];
  state: PostState;
  score: number;
  status_label: string;
  reason: string;
  evidence: EvidenceDetail | null;
  alert_sent: boolean;
  breakout_sim_hours: number | null;
  current_sim_hours: number | null;
}

export interface CreatorRosterPost {
  post_id: string;
  caption: string | null;
  state: PostState;
  status_label: string;
  score: number;
  evidence: EvidenceDetail | null;
  sparkline: number[];
}

export interface CreatorRosterEntry {
  id: string;
  handle: string;
  followers: number;
  active_post_count: number;
  taking_off_count: number;
  worth_watching_count: number;
  needs_attention_count: number;
  unavailable_post_count: number;
  strongest_post: CreatorRosterPost | null;
  latest_sim_hours: number | null;
}

export interface CreatorsResponse {
  creators: CreatorRosterEntry[];
  current_sim_hours: number | null;
}

export interface CreatorPostSummary {
  post_id: string;
  caption: string | null;
  published_at: string | null;
  state: PostState;
  status_label: string;
  score: number;
  evidence: EvidenceDetail | null;
  is_gone: boolean;
  latest_sim_hours: number | null;
  sparkline: number[];
}

export interface CreatorStats {
  posts_tracked: number;
  posts_that_took_off: number;
  typical_views: number;
}

export interface CreatorDetailResponse {
  creator: CreatorContext;
  active_posts: CreatorPostSummary[];
  unavailable_posts: CreatorPostSummary[];
  stats: CreatorStats;
  current_sim_hours: number | null;
}

export interface NotablePost {
  post_id: string;
  creator_handle: string;
  caption: string | null;
  status_label: string;
  sim_hours: number;
}

export interface AlertSummary {
  post_id: string;
  creator_handle: string;
  caption: string | null;
  sim_hours: number;
}

export interface SystemStatus {
  posts_tracked: number;
  last_checked_sim_hours: number | null;
  most_notable_post: NotablePost | null;
  most_recent_alert: AlertSummary | null;
  alerts_sent: number;
}

export interface BreakoutLogEntry {
  post_id: string;
  creator_handle: string;
  caption: string | null;
  breakout_sim_hours: number;
  breakout_at: string | null;
  views_at_breakout: number;
  peak_views: number;
  growth_multiple: number | null;
  current_status_label: string;
  alert_submitted: boolean;
}

export interface BreakoutLogResponse {
  entries: BreakoutLogEntry[];
  current_sim_hours: number | null;
}

// The full "Track program posts" board: every active post, ranked by
// current momentum (highest first) — never by lifetime views. Home only
// ever shows a capped set of highlights; this is the complete list.
export interface PostsBoardResponse {
  posts: HomePost[];
  total_posts: number;
  current_sim_hours: number | null;
}
