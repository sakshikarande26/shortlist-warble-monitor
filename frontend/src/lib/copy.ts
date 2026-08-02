// Every piece of user-facing copy lives in this one file so the "marketer
// language only" rule (docs/FRONTEND.md) is auditable in one place instead
// of scattered across components. Nothing here invents data — every claim
// is derived from a real field on HomePost/PostDetail.

import type { EvidenceDetail, HomePost, PostDetail, PostState } from "./types";

// "Taking off" is the card label (matches the "Act now" section it lives
// under); "Watch closely" is exclusive to RISING now — WATCH keeps its own
// distinct label so a creator's post list (which shows every state, not
// just the two Home triages) never conflates "just jumped, unconfirmed"
// with "sustained growth for multiple checks."
const STATE_LABEL: Record<PostState, string> = {
  BREAKOUT: "Taking off",
  RISING: "Watch closely",
  WATCH: "Just jumped",
  NEW: "Steady",
  COOLING: "Slowing down",
};

export function statusLabel(state: PostState, isGone: boolean): string {
  return isGone ? "No longer available" : STATE_LABEL[state];
}

/** One meaningful, honest statement per card, grounded in this post's own
 * evidence numbers (not a fixed sentence repeated across every post in the
 * same state) — how much views grew, and whether that pace is faster or
 * slower than this post's own earlier trajectory. Falls back to a
 * qualitative line only when there isn't enough history yet to compute
 * evidence (never invents numbers). */
export function performanceStatement(post: Pick<HomePost, "state" | "is_gone" | "evidence">): string {
  if (post.is_gone) {
    return "No longer available — history is preserved below.";
  }
  const evidence = post.evidence;
  if (!evidence) {
    return performanceStatementFallback(post.state);
  }

  // BREAKOUT already gets a specific, absolute-momentum sentence below —
  // for every other state, the comparative-pace sentence (when available)
  // is the more honest story: it's why the post made Home's triage list at
  // all now that ranking is comparative rather than state-based.
  if (post.state !== "BREAKOUT") {
    const comparative = describeComparativePace(evidence);
    if (comparative) return comparative;
  }

  const growthPhrase = describeGrowth(evidence);
  const pacePhrase = describePace(evidence);

  switch (post.state) {
    case "BREAKOUT":
      return `Views ${growthPhrase} in the latest check, ${pacePhrase}.`;
    case "RISING":
      return `Views ${growthPhrase} in the latest check, ${pacePhrase}.`;
    case "WATCH":
      return `Views ${growthPhrase} in this one check — too early to confirm it holds.`;
    case "COOLING":
      return `Growth has cooled — only ${Math.max(evidence.absolute_gain, 0).toLocaleString()} new views in the latest check.`;
    case "NEW":
    default:
      return "No unusual movement — performing about as expected.";
  }
}

function performanceStatementFallback(state: PostState): string {
  switch (state) {
    case "BREAKOUT":
      return "Sustained fast growth across several checks in a row — a real breakout.";
    case "RISING":
      return "Growth has held up across multiple checks, not just a one-off spike.";
    case "WATCH":
      return "Just jumped — still too early to say if it holds.";
    case "COOLING":
      return "Was climbing, but growth has cooled off since.";
    case "NEW":
    default:
      return "No unusual movement — performing about as expected.";
  }
}

/** Short status-line for the top of the detail page — punchier than
 * explainEvidence below it, matching docs/FRONTEND.md's own example style
 * ("Taking off. Sustained unusually fast growth across three checks..."). */
export function statusSummary(detail: Pick<PostDetail, "state" | "is_gone">): string {
  if (detail.is_gone) {
    return "No longer available. History from before it came down is preserved below.";
  }
  switch (detail.state) {
    case "BREAKOUT":
      return "Taking off. Sustained growth across several checks in a row.";
    case "RISING":
      return "Gaining momentum. Growth has held up across more than one check.";
    case "WATCH":
      return "Just started climbing. Still too early to confirm.";
    case "COOLING":
      return "Slowing down after an earlier run of growth.";
    case "NEW":
    default:
      return "Steady. No unusual movement to report.";
  }
}

/** The detail page's evidence-to-plain-language translation. Grounded in
 * the real EvidenceDetail numbers — never narrates raw metrics directly,
 * translates them into what they mean. */
export function explainEvidence(detail: Pick<PostDetail, "state" | "evidence">): string {
  const evidence = detail.evidence;
  if (!evidence) {
    return "Not enough history yet to explain this post's trajectory.";
  }

  const growthPhrase = describeGrowth(evidence);
  const pacePhrase = describePace(evidence);

  switch (detail.state) {
    case "BREAKOUT":
      return `Momentum has continued across several consecutive checks rather than a one-time spike. In the latest check, views were ${growthPhrase}, ${pacePhrase}.`;
    case "RISING":
      return `Growth has held up across more than one check now. In the latest check, views were ${growthPhrase}, ${pacePhrase}.`;
    case "WATCH":
      return `One strong check so far — views were ${growthPhrase} — but it's too early to know if this holds.`;
    case "COOLING":
      return `Growth has slowed since an earlier run of momentum. The latest check added ${Math.max(evidence.absolute_gain, 0).toLocaleString()} views, not enough to count as still taking off.`;
    case "NEW":
    default:
      return "No unusual growth has shown up yet — the latest check was in line with a normal, steady pace.";
  }
}

function describeGrowth(evidence: EvidenceDetail): string {
  if (evidence.relative_growth_pct >= 1) {
    return `up ${Math.round(evidence.relative_growth_pct)}%`;
  }
  return `up ${Math.max(evidence.absolute_gain, 0).toLocaleString()} views`;
}

function describePace(evidence: EvidenceDetail): string {
  if (evidence.trajectory_ratio >= 1.5) {
    return "growing noticeably faster than this post's own early pace";
  }
  if (evidence.trajectory_ratio >= 1.05) {
    return "growing a bit faster than this post's own early pace";
  }
  return "close to this post's own early pace";
}

const SMALL_NUMBER_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];

function numberWord(n: number): string {
  return n >= 0 && n < SMALL_NUMBER_WORDS.length ? SMALL_NUMBER_WORDS[n] : String(n);
}

function paceMagnitudePhrase(ratio: number): string {
  if (ratio >= 2.5) {
    return `about ${numberWord(Math.round(ratio))} times faster`;
  }
  if (ratio >= 1.6) return "notably faster";
  return "faster";
}

/** Home's comparative-ranking sentence: how a post's current pace compares
 * to what's typical for THIS creator specifically (or, lacking enough of
 * this creator's other posts to compare against, to the post's own earlier
 * pace) — the reason a post not yet flagged BREAKOUT can still be worth a
 * marketer's attention on a quiet day. Returns null when there's no
 * comparative signal to describe (post/creator detail views, where it
 * isn't computed) — callers fall back to other evidence-based phrasing. */
function describeComparativePace(evidence: EvidenceDetail): string | null {
  const { creator_pace_ratio: ratio, creator_pace_basis: basis } = evidence;
  if (ratio === null || basis === null) return null;
  const magnitude = paceMagnitudePhrase(ratio);
  return basis === "creator"
    ? `Growing ${magnitude} than this creator's posts usually do at this age.`
    : `Growing ${magnitude} than earlier in its own run.`;
}

/** Considerations, never autonomous actions — the marketer decides. */
export function suggestedActions(state: PostState, isGone: boolean): string[] {
  if (isGone) {
    return [
      "This post is no longer available, so there's nothing to promote directly.",
      "If it was performing well before it came down, consider a follow-up post with this creator.",
    ];
  }
  switch (state) {
    case "BREAKOUT":
      return [
        "Consider boosting with paid spend while momentum is still rising.",
        "Consider resharing on brand channels to extend its reach.",
        "Consider extending this creator's deal while they're hot.",
        "Check usage rights before promoting further.",
      ];
    case "RISING":
      return [
        "Worth watching closely — if growth continues, boosting could pay off.",
        "Consider resharing on brand channels now, at low risk.",
      ];
    case "WATCH":
      return ["Too early to act — keep watching to see if this holds."];
    case "COOLING":
      return [
        "Momentum has passed its peak — reshares or spend are unlikely to have the same impact now.",
        "Worth reviewing what worked here for future posts with this creator.",
      ];
    case "NEW":
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
