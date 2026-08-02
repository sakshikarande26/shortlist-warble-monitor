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
  // Comparative-to-creator pace — Home ranking only, null on post/creator
  // detail. "creator" = compared against this creator's other posts at a
  // similar age; "self" = fell back to trajectory_ratio (too few other
  // posts to build a baseline from).
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
  sparkline: number[];
}

export interface HomeResponse {
  // Already ranked and capped server-side — rendered as given, not
  // re-derived from state client-side.
  act_now: HomePost[];
  watch_closely: HomePost[];
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
  current_sim_hours: number | null;
}

export interface CreatorRosterPost {
  post_id: string;
  caption: string | null;
  state: PostState;
  status_label: string;
  score: number;
}

export interface CreatorRosterEntry {
  id: string;
  handle: string;
  followers: number;
  active_post_count: number;
  needs_attention_count: number;
  strongest_post: CreatorRosterPost | null;
}

export interface CreatorsResponse {
  creators: CreatorRosterEntry[];
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
