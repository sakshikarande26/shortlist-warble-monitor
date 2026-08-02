// Every piece of user-facing copy lives in this one file so the "marketer
// language only" rule (docs/FRONTEND.md) is auditable in one place instead
// of scattered across components. Nothing here invents data — every claim
// is derived from a real field on HomePost/PostDetail.
//
// status_label itself is NOT computed here — it comes straight from the
// API (backend/app/api/routes.py's _unified_status), and every component
// renders it verbatim. That's deliberate: it's the one canonical status
// (headline, section membership, row badge, detail page, right panel all
// use the same value), and a second frontend-side mapping is exactly how a
// section header and a card's own badge end up disagreeing.

import type { EvidenceDetail, HomePost, HomeResponse, PostDetail, SystemStatus } from "./types";

/** One meaningful, honest statement per card, grounded in this post's own
 * evidence numbers — how much it gained, over what window, and how that
 * compares to what's normal for this creator (or, lacking enough of this
 * creator's other posts, to its own earlier pace). Never a fixed sentence
 * repeated across every post in the same status. */
export function performanceStatement(
  post: Pick<HomePost, "is_gone" | "status_label" | "evidence">,
): string {
  if (post.is_gone) {
    return "No longer available — history is preserved below.";
  }
  const evidence = post.evidence;
  if (!evidence) {
    return "Not enough history yet to say how this is performing.";
  }
  if (post.status_label === "Steady") {
    return "No unusual movement — performing about as expected.";
  }

  return `${describeGain(evidence)}. ${describeComparativePace(evidence)}`;
}

/** Short status-line for the top of the detail page — punchier than
 * explainEvidence below it, matching docs/FRONTEND.md's own example style
 * ("Taking off. Sustained unusually fast growth across three checks..."). */
export function statusSummary(detail: Pick<PostDetail, "status_label" | "is_gone">): string {
  if (detail.is_gone) {
    return "No longer available. History from before it came down is preserved below.";
  }
  switch (detail.status_label) {
    case "Taking off":
      return "Taking off. Sustained growth across several checks in a row.";
    case "Worth watching":
      return "Worth watching. Growing faster than what's typical for this creator right now.";
    case "Steady":
    default:
      return "Steady. No unusual movement to report.";
  }
}

/** The detail page's (and right panel's) evidence-to-plain-language
 * translation. Grounded in the real EvidenceDetail numbers — never
 * narrates raw metrics directly, translates them into what they mean. */
export function explainEvidence(detail: Pick<PostDetail, "status_label" | "is_gone" | "evidence">): string {
  if (detail.is_gone) {
    return "This post is no longer available. The history below is from before it came down.";
  }
  const evidence = detail.evidence;
  if (!evidence) {
    return "Not enough history yet to explain this post's trajectory.";
  }
  if (detail.status_label === "Steady") {
    return "No unusual growth has shown up yet — the latest check was in line with a normal, steady pace.";
  }

  const streak = describeStreak(evidence.consecutive_qualifying_checks);
  return `${describeGain(evidence)}. ${describeComparativePace(evidence)}${streak}`;
}

/** "+3,420 views in 2h" — the gain from the latest check and, when it's
 * known, the real time window it happened over. Never derives the window
 * by dividing gain by velocity (that would itself divide by zero on a
 * flat interval) — it's read directly off the underlying sample
 * timestamps on the backend. */
function describeGain(evidence: EvidenceDetail): string {
  const gain = Math.max(evidence.absolute_gain, 0);
  const gainText = `+${gain.toLocaleString()} views`;
  if (evidence.window_hours === null) return gainText;
  return `${gainText} in ${formatWindow(evidence.window_hours)}`;
}

function formatWindow(hours: number): string {
  if (hours < 1) return `${Math.max(Math.round(hours * 60), 1)}m`;
  if (Number.isInteger(hours)) return `${hours}h`;
  return `${hours.toFixed(1)}h`;
}

/** "2.4× faster than this creator's normal pace at this age" — the
 * comparative signal that ranks Home in the first place, folded into one
 * plain sentence. Never a bare multiplier on its own: when it can't be
 * trusted (too little history for either a creator or self comparison),
 * says so honestly rather than fabricating a number. */
function describeComparativePace(evidence: EvidenceDetail): string {
  const { creator_pace_ratio: ratio, creator_pace_basis: basis } = evidence;
  if (ratio === null || basis === null) {
    return "Not enough history yet to compare its pace.";
  }
  const multiple = `${ratio.toFixed(1)}×`;
  return basis === "creator"
    ? `${multiple} faster than this creator's normal pace at this age.`
    : `${multiple} faster than earlier in its own run.`;
}

function describeStreak(consecutiveChecks: number): string {
  if (consecutiveChecks < 2) return "";
  return ` Elevated for ${consecutiveChecks} checks in a row.`;
}

/** Considerations, never autonomous actions — the marketer decides. Keyed
 * off the same canonical status_label as everything else, not a separate
 * absolute-state mapping. */
export function suggestedActions(statusLabel: string, isGone: boolean): string[] {
  if (isGone) {
    return [
      "This post is no longer available, so there's nothing to promote directly.",
      "If it was performing well before it came down, consider a follow-up post with this creator.",
    ];
  }
  switch (statusLabel) {
    case "Taking off":
      return [
        "Consider boosting with paid spend while momentum is still rising.",
        "Consider resharing on brand channels to extend its reach.",
        "Consider extending this creator's deal while they're hot.",
        "Check usage rights before promoting further.",
      ];
    case "Worth watching":
      return [
        "Worth watching closely — if growth continues, boosting could pay off.",
        "Consider resharing on brand channels now, at low risk.",
      ];
    case "Steady":
    default:
      return ["Nothing unusual yet — keep watching along with the rest of this creator's posts."];
  }
}

/** Sim time isn't wall-clock time, so freshness has to be phrased relative
 * to the most recent known sim_hours (current_sim_hours from the API),
 * never derived from Date.now(). */
export function formatRelativeSimTime(
  latestSimHours: number | null,
  currentSimHours: number | null,
): string {
  if (latestSimHours === null) return "No updates yet";
  if (currentSimHours === null) return "Updated recently";
  const delta = currentSimHours - latestSimHours;
  if (delta < 0.05) return "Updated moments ago";
  if (delta < 1) return "Updated less than an hour ago";
  if (delta < 24) {
    const hours = Math.round(delta);
    return `Updated ${hours} hour${hours === 1 ? "" : "s"} ago`;
  }
  const days = Math.round(delta / 24);
  return `Updated ${days} day${days === 1 ? "" : "s"} ago`;
}

/** 6 hours matches the collector's own discovery-sweep cadence (CLAUDE.md)
 * — a post that hasn't refreshed in that long is a real, grounded signal
 * something's off, not an arbitrary UI threshold. */
const STALE_THRESHOLD_HOURS = 6;

export function isStale(latestSimHours: number | null, currentSimHours: number | null): boolean {
  if (latestSimHours === null || currentSimHours === null) return false;
  return currentSimHours - latestSimHours >= STALE_THRESHOLD_HOURS;
}

/** The monitoring window runs for 7 sim-days (CLAUDE.md). "Day 3 of 7" is
 * grounded in the real sim_hours number but means something to a marketer
 * in a way a raw "hour 62" reading never does. */
const MONITORING_WINDOW_DAYS = 7;

export function formatMonitoringProgress(simHours: number): string {
  const day = Math.min(Math.floor(simHours / 24) + 1, MONITORING_WINDOW_DAYS);
  return `Day ${day} of ${MONITORING_WINDOW_DAYS}`;
}

export function formatPublishedAt(publishedAt: string | null): string {
  if (!publishedAt) return "Publish time unknown";
  const date = new Date(publishedAt);
  if (Number.isNaN(date.getTime())) return "Publish time unknown";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export function getInitials(handle: string): string {
  const cleaned = handle.replace(/^[^a-zA-Z0-9]+/, "");
  return cleaned.slice(0, 2).toUpperCase() || "?";
}

export function formatFollowers(followers: number): string {
  if (followers >= 1_000_000) return `${(followers / 1_000_000).toFixed(1)}M followers`;
  if (followers >= 1_000) return `${(followers / 1_000).toFixed(1)}K followers`;
  return `${followers} followers`;
}

export function formatViews(views: number): string {
  if (views >= 1_000_000) return `${(views / 1_000_000).toFixed(1)}M`;
  if (views >= 1_000) return `${Math.round(views / 1_000)}K`;
  return `${Math.round(views)}`;
}

/** Briefing sentence at the top of Home — built only from real counts,
 * never invented (docs/FRONTEND.md: "built from REAL state"). */
export function buildBriefing(actNowCount: number, watchCount: number, unavailableCount: number): string {
  if (actNowCount === 0 && watchCount === 0 && unavailableCount === 0) {
    return "Nothing unusual right now — everything is performing steadily.";
  }

  const parts: string[] = [];
  if (actNowCount > 0) {
    parts.push(`${actNowCount} post${actNowCount === 1 ? " is" : "s are"} taking off`);
  }
  if (watchCount > 0) {
    parts.push(`${watchCount} worth watching`);
  }
  if (unavailableCount > 0) {
    parts.push(
      `${unavailableCount} became unavailable while you were away`,
    );
  }

  if (parts.length === 0) {
    return "Nothing unusual right now — everything is performing steadily.";
  }
  if (parts.length === 1) {
    return `${capitalize(parts[0])}.`;
  }
  const last = parts[parts.length - 1];
  const rest = parts.slice(0, -1);
  return `${capitalize(rest.join(", "))}, and ${last}.`;
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

// ---------------------------------------------------------------------
// AI teammate: pre-built questions with deterministic, evidence-grounded
// answers. No LLM wired up yet — every answer here is built from the same
// real fields the rest of the app already uses, phrased as a helpful
// colleague would say it. When the LLM is added later, these become the
// fallback path (docs/FRONTEND.md: the product must stay honest even if
// the LLM is unavailable), not thrown away.
// ---------------------------------------------------------------------

/** Small evidence tags shown under an answer — "+408 in 30m", "14.1×
 * baseline", "3 elevated checks" — so a claim is never just asserted. */
export function evidenceChips(evidence: EvidenceDetail | null): string[] {
  if (!evidence) return [];
  const chips: string[] = [];
  const gain = Math.max(evidence.absolute_gain, 0);
  chips.push(
    evidence.window_hours !== null
      ? `+${gain.toLocaleString()} in ${formatWindow(evidence.window_hours)}`
      : `+${gain.toLocaleString()} views`,
  );
  if (evidence.creator_pace_ratio !== null) {
    chips.push(`${evidence.creator_pace_ratio.toFixed(1)}× baseline`);
  }
  if (evidence.consecutive_qualifying_checks >= 2) {
    chips.push(`${evidence.consecutive_qualifying_checks} elevated checks`);
  }
  return chips;
}

export function answerWhyStatus(post: Pick<PostDetail, "status_label" | "is_gone" | "evidence">): string {
  return explainEvidence(post);
}

export function answerWhatChanged(post: Pick<PostDetail, "is_gone" | "evidence">): string {
  if (post.is_gone) return "No new activity — this post is no longer live.";
  if (!post.evidence) return "Not enough history yet to describe a recent change.";
  return describeGain(post.evidence);
}

export function answerBaselineComparison(post: Pick<PostDetail, "is_gone" | "evidence">): string {
  if (post.is_gone) return "Comparison isn't meaningful for a post that's no longer live.";
  if (!post.evidence) return "Not enough history yet to compare its pace.";
  return describeComparativePace(post.evidence);
}

export function answerAlertStatus(alertSent: boolean, isGone: boolean): string {
  if (alertSent) return "Yes — an official breakout alert has been sent for this post.";
  if (isGone) return "No alert was sent before this post became unavailable.";
  return "No alert has been sent for this post yet.";
}

export function answerNextSteps(statusLabel: string, isGone: boolean): string {
  return suggestedActions(statusLabel, isGone).join(" ");
}

export function answerWhatChangedSinceLastCheck(status: SystemStatus): string {
  if (!status.most_notable_post) return "Nothing new to flag since the last check.";
  const p = status.most_notable_post;
  const caption = p.caption ? ` — "${p.caption}"` : "";
  return `@${p.creator_handle}${caption} is the most recently updated post worth flagging, now ${p.status_label.toLowerCase()}.`;
}

export function answerWhichPostsNeedAttention(home: HomeResponse): string {
  const total = home.act_now.length + home.watch_closely.length;
  if (total === 0) return "Nothing needs your attention right now.";
  const parts: string[] = [];
  if (home.act_now.length > 0) {
    parts.push(`${home.act_now.length} taking off`);
  }
  if (home.watch_closely.length > 0) {
    parts.push(`${home.watch_closely.length} worth watching`);
  }
  return `${capitalize(parts.join(" and "))} right now.`;
}

export function answerStrongestMomentum(home: HomeResponse): string {
  const candidates = [...home.act_now, ...home.watch_closely];
  if (candidates.length === 0) {
    return "Nothing is currently outperforming what's normal for its creator.";
  }
  const strongest = candidates.reduce((best, post) => {
    const ratio = post.evidence?.creator_pace_ratio ?? -Infinity;
    const bestRatio = best.evidence?.creator_pace_ratio ?? -Infinity;
    return ratio > bestRatio ? post : best;
  });
  const caption = strongest.caption ? ` — "${strongest.caption}"` : "";
  return `@${strongest.creator_handle}${caption} has the strongest current momentum.`;
}

export function answerRecentAlert(status: SystemStatus): string {
  if (!status.most_recent_alert) return "No alerts have been sent yet.";
  const a = status.most_recent_alert;
  const caption = a.caption ? ` — "${a.caption}"` : "";
  return `An alert was sent for @${a.creator_handle}${caption}.`;
}
