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

import type { EvidenceDetail, HomePost, PostDetail } from "./types";

/** One meaningful, honest statement per card, grounded in this post's own
 * evidence numbers — how much it gained, over what window, and how that
 * compares to what's normal for this creator (or, lacking enough of this
 * creator's other posts, to its own earlier pace). Never a fixed sentence
 * repeated across every post in the same status. */
export function performanceStatement(
  post: Pick<HomePost, "is_gone" | "status_label" | "evidence">,
): string {
  if (post.is_gone) {
    return "No longer available. History is preserved below.";
  }
  const evidence = post.evidence;
  if (!evidence) {
    return "Not enough history yet to say how this is performing.";
  }
  if (post.status_label === "Steady") {
    return "No unusual movement. Performing about as expected.";
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
    return "No unusual growth has shown up yet. The latest check was in line with a normal, steady pace.";
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

/** Creator-level context for a post's detail page: who the creator is, and
 * how this post's pace sits against their norm. Grounded only in the
 * fields this endpoint actually returns — nothing about the creator's
 * other posts is available here, so it never claims any. */
export function creatorInsight(detail: Pick<PostDetail, "creator" | "evidence">): string {
  const { handle, followers, category } = detail.creator;
  const audience = `@${handle} has ${formatFollowers(followers)}${category ? ` in ${category}` : ""}.`;

  const evidence = detail.evidence;
  if (!evidence || evidence.creator_pace_ratio === null || evidence.creator_pace_basis === null) {
    return `${audience} Not enough history yet to compare this post against their usual pace.`;
  }

  const multiple = `${evidence.creator_pace_ratio.toFixed(1)}×`;
  return evidence.creator_pace_basis === "creator"
    ? `${audience} This post is running ${multiple} their normal pace for a post this age.`
    : `${audience} Too few other posts from them to compare against yet, so this is measured ${multiple} against the post's own earlier pace.`;
}

/** Warble's own timestamp strings (metrics_at/metrics_cached_at) are
 * sometimes timezone-naive (no trailing Z or ±HH:MM). The backend treats a
 * naive timestamp as UTC (routes.py's _as_utc()) before doing any date
 * math; `new Date(...)` does not — a naive string is parsed as local
 * browser time instead, silently shifting the displayed time (and
 * sometimes the calendar date itself, near midnight) by the viewer's UTC
 * offset. This mirrors the backend's rule so both sides agree. */
function parseApiTimestamp(iso: string | null): Date | null {
  if (!iso) return null;
  const hasTimezone = /Z$|[+-]\d{2}:\d{2}$/.test(iso);
  const date = new Date(hasTimezone ? iso : `${iso}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** Sim time isn't wall-clock time, so freshness has to be phrased relative
 * to the most recent known sim_hours (current_sim_hours from the API),
 * never derived from Date.now(). */
const DAYS_BEFORE_ABSOLUTE_DATE = 3;

export function formatRelativeSimTime(
  latestSimHours: number | null,
  currentSimHours: number | null,
  // Real ISO timestamp of that reading. Once something is more than a few
  // days old, "Updated 6 days ago" stops being useful and an actual date
  // is easier to reason about — that switch needs a real timestamp, which
  // sim_hours alone can't provide.
  latestMetricsAt?: string | null,
): string {
  if (latestSimHours === null) return "No updates yet";
  if (currentSimHours === null) return "Updated recently";
  const delta = currentSimHours - latestSimHours;
  if (delta < 1 / 60) return "Updated moments ago";

  if (delta >= 24 * DAYS_BEFORE_ABSOLUTE_DATE && latestMetricsAt) {
    const date = parseApiTimestamp(latestMetricsAt);
    if (date) {
      return `Updated ${date.toLocaleDateString(undefined, {
        weekday: "short",
        day: "numeric",
        month: "short",
      })}`;
    }
  }

  if (delta < 1) {
    const minutes = Math.min(Math.round(delta * 60), 59);
    return `Updated ${minutes} min${minutes === 1 ? "" : "s"} ago`;
  }

  if (delta < 24) {
    let hours = Math.floor(delta);
    let minutes = Math.round((delta - hours) * 60);
    if (minutes === 60) {
      hours += 1;
      minutes = 0;
    }
    if (minutes === 0) return `Updated ${hours} hour${hours === 1 ? "" : "s"} ago`;
    return `Updated ${hours} hour${hours === 1 ? "" : "s"} ${minutes} min${minutes === 1 ? "" : "s"} ago`;
  }

  if (delta < 24 * 30) {
    const days = Math.round(delta / 24);
    return `Updated ${days} day${days === 1 ? "" : "s"} ago`;
  }

  const months = Math.round(delta / (24 * 30));
  return `Updated ${months} month${months === 1 ? "" : "s"} ago`;
}

/** 6 hours matches the collector's own discovery-sweep cadence (CLAUDE.md)
 * — a post that hasn't refreshed in that long is a real, grounded signal
 * something's off, not an arbitrary UI threshold. */
const STALE_THRESHOLD_HOURS = 6;

export function isStale(latestSimHours: number | null, currentSimHours: number | null): boolean {
  if (latestSimHours === null || currentSimHours === null) return false;
  return currentSimHours - latestSimHours >= STALE_THRESHOLD_HOURS;
}

/** "Tue 7 Jul 2026, 3:42 AM" from a reading's real timestamp. Uses the
 * timestamp stored on the sample itself, never a value derived from
 * sim_hours. */
export function formatMoment(isoTimestamp: string | null): string {
  const date = parseApiTimestamp(isoTimestamp);
  if (!date) return "Time not recorded";
  return date.toLocaleString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatPublishedAt(publishedAt: string | null): string {
  const date = parseApiTimestamp(publishedAt);
  if (!date) return "Publish time unknown";
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

/** 7 matches the sim's fixed monitoring window (CLAUDE.md) — mirrors
 * backend/app/api/agent.py's _window_progress so "Day X of 7" never
 * disagrees between the teammate panel and the home screen. Exported so
 * every sim-hours-to-day bucketing on the frontend (BreakoutTrendChart
 * included) uses this one formula instead of each re-deriving it. */
export const MONITORING_WINDOW_DAYS = 7;

export function dayBucket(simHours: number): number {
  return Math.min(Math.floor(simHours / 24) + 1, MONITORING_WINDOW_DAYS);
}

export function windowProgress(currentSimHours: number | null): string {
  if (currentSimHours === null) return "Not started yet";
  return `Day ${dayBucket(currentSimHours)} of ${MONITORING_WINDOW_DAYS}`;
}

/** The home screen's trend chart shows the shape; this answers "so what" —
 * one plain sentence a marketer can read without doing the counting
 * themselves. `counts` is breakouts per sim-day (index 0 = Day 1),
 * `currentDay` bounds how many of those days are real vs. not-yet-reached,
 * so an empty window doesn't read as "nothing ever happens" when it's
 * really just early. */
export function breakoutTrendSummary(counts: number[], currentDay: number): string {
  const reached = counts.slice(0, currentDay);
  const total = reached.reduce((sum, n) => sum + n, 0);
  if (total === 0) {
    return `No breakouts yet through Day ${currentDay} of ${MONITORING_WINDOW_DAYS} — still early in the window.`;
  }
  const peakDay = reached.reduce((best, n, i) => (n > reached[best] ? i : best), 0) + 1;
  const peakCount = reached[peakDay - 1];
  return `${total} breakout${total === 1 ? "" : "s"} across the program this week, most on Day ${peakDay} (${peakCount}).`;
}

/** Briefing sentence at the top of Home — built only from real counts,
 * never invented (docs/FRONTEND.md: "built from REAL state"). */
export function buildBriefing(actNowCount: number, watchCount: number, unavailableCount: number): string {
  if (actNowCount === 0 && watchCount === 0 && unavailableCount === 0) {
    return "Nothing unusual right now. Everything is performing steadily.";
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
    return "Nothing unusual right now. Everything is performing steadily.";
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

/** The subset of EvidenceDetail the chip line actually reads — narrowed so
 * this can also be fed an adapted (differently-named) evidence shape, like
 * the chat agent's facts_used.selected_post, without a second chip
 * function or a fabricated full EvidenceDetail. */
type EvidenceChipSource = Pick<
  EvidenceDetail,
  "absolute_gain" | "window_hours" | "creator_pace_ratio" | "consecutive_qualifying_checks"
>;

/** Small evidence tags shown under an AI teammate answer — "+408 in 30m",
 * "14.1× baseline", "3 elevated checks" — so a claim is never just
 * asserted. Fed to the AiPanel alongside the LLM's (or its deterministic
 * fallback's) reply. */
export function evidenceChips(evidence: EvidenceChipSource | null): string[] {
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

/** "+289 in 17m" as its own value, for table-style layouts (Track program
 * posts) that want gain in a dedicated column rather than folded into a
 * sentence — same numbers evidenceChips uses, just addressable alone. */
export function gainColumn(evidence: EvidenceChipSource | null): string | null {
  if (!evidence) return null;
  const gain = Math.max(evidence.absolute_gain, 0);
  const gainText = `+${gain.toLocaleString()}`;
  return evidence.window_hours !== null ? `${gainText} in ${formatWindow(evidence.window_hours)}` : gainText;
}

/** "2.6× baseline" as its own value — null (not "0×") when there isn't
 * enough history for a trustworthy comparison, same as everywhere else in
 * the app that reads creator_pace_ratio. */
export function paceColumn(evidence: EvidenceChipSource | null): string | null {
  if (!evidence || evidence.creator_pace_ratio === null) return null;
  return `${evidence.creator_pace_ratio.toFixed(1)}×`;
}

interface AgentFactsSelectedPost {
  recent_gain_views?: number | null;
  recent_gain_window_hours?: number | null;
  baseline_multiple?: number | null;
  consecutive_elevated_checks?: number | null;
}

interface AgentFactsProgram {
  posts_watched?: number;
  creators_watched?: number;
}

/** The chat evidence row: what actually grounded a given chat reply,
 * pulled from that reply's own `facts_used` rather than whatever post
 * happens to be selected on screen right now. Reuses evidenceChips()'s
 * exact chip text for the selected-post case (same visual language as
 * everywhere else); for a program-level reply — no selected post — falls
 * back to a small, honest program-shaped chip set instead of guessing
 * which fact the reply actually drew on. */
export function agentEvidenceChips(factsUsed: Record<string, unknown> | undefined): string[] {
  if (!factsUsed) return [];

  const selected = factsUsed.selected_post as AgentFactsSelectedPost | null | undefined;
  if (selected && selected.recent_gain_views != null) {
    return evidenceChips({
      absolute_gain: selected.recent_gain_views,
      window_hours: selected.recent_gain_window_hours ?? null,
      creator_pace_ratio: selected.baseline_multiple ?? null,
      consecutive_qualifying_checks: selected.consecutive_elevated_checks ?? 0,
    });
  }
  if (selected) return [];

  const chips: string[] = [];
  const program = factsUsed.program as AgentFactsProgram | undefined;
  if (program?.posts_watched != null && program?.creators_watched != null) {
    chips.push(`${program.posts_watched} posts · ${program.creators_watched} creators`);
  }
  const breakouts = factsUsed.breakouts as unknown[] | undefined;
  if (breakouts && breakouts.length > 0) {
    chips.push(`${breakouts.length} breakouts`);
  }
  const alerts = factsUsed.alerts as { submitted?: boolean }[] | undefined;
  const sentAlerts = alerts?.filter((a) => a.submitted).length ?? 0;
  if (sentAlerts > 0) {
    chips.push(`${sentAlerts} alerts sent`);
  }
  return chips;
}

/** One cited source behind an answer: the actual post the reply named,
 * with its own real numbers and a way to go inspect it. */
export interface AgentReference {
  postId: string | null;
  handle: string;
  caption: string | null;
  status: string | null;
  facts: string[];
}

/** The union of every post-shaped entity build_facts() emits (selected
 * post, top movers, alerts, breakouts) — they overlap but each carries a
 * different subset, so every field is optional and only the present ones
 * ever get rendered. */
interface AgentFactsEntity {
  post_id?: string;
  creator_handle?: string;
  creator_followers?: number | null;
  caption?: string | null;
  status?: string;
  status_now?: string;
  is_available?: boolean;
  current_views?: number | null;
  post_age_hours?: number | null;
  views_per_hour?: number | null;
  recent_gain_views?: number | null;
  recent_gain_window_hours?: number | null;
  baseline_multiple?: number | null;
  consecutive_elevated_checks?: number | null;
  is_creators_best_so_far?: boolean | null;
  rank_among_creators_posts?: number | null;
  creators_post_count?: number | null;
  climbed_multiple?: number | null;
  peak_views?: number | null;
  views_at_breakout?: number | null;
  breakout_sim_hour?: number | null;
  submitted?: boolean;
  submitted_sim_hour?: number | null;
}

// Every chip is a distinct number pulled straight from the entity — no two
// chips ever restate the same fact in different words, and which fields are
// present (selected post vs. mover vs. alert vs. breakout row) naturally
// varies which chips show up, so cards don't all read the same shape.
function toReference(entity: AgentFactsEntity): AgentReference {
  const facts: string[] = [];
  if (entity.current_views != null) facts.push(`${formatViews(entity.current_views)} now`);
  if (entity.views_per_hour != null) facts.push(`${formatViews(Math.round(entity.views_per_hour))}/hr`);
  if (entity.recent_gain_views != null) {
    const gain = `+${entity.recent_gain_views.toLocaleString()}`;
    facts.push(
      entity.recent_gain_window_hours != null
        ? `${gain} in ${formatWindow(entity.recent_gain_window_hours)}`
        : `${gain} views`,
    );
  }
  if (entity.baseline_multiple != null) facts.push(`${entity.baseline_multiple.toFixed(1)}× baseline`);
  if (entity.consecutive_elevated_checks != null && entity.consecutive_elevated_checks >= 2) {
    facts.push(`${entity.consecutive_elevated_checks} elevated checks`);
  }
  if (entity.is_creators_best_so_far === true) {
    facts.push("Creator's best post so far");
  } else if (entity.rank_among_creators_posts != null && entity.creators_post_count != null) {
    facts.push(`#${entity.rank_among_creators_posts} of ${entity.creators_post_count} for this creator`);
  }
  if (entity.climbed_multiple != null) facts.push(`${entity.climbed_multiple.toFixed(1)}× since breakout`);
  if (entity.peak_views != null) facts.push(`${formatViews(entity.peak_views)} peak`);
  else if (entity.views_at_breakout != null) facts.push(`${formatViews(entity.views_at_breakout)} at breakout`);
  if (entity.post_age_hours != null) facts.push(`${formatWindow(entity.post_age_hours)} old`);
  if (entity.creator_followers != null) facts.push(`${formatViews(entity.creator_followers)} followers`);
  if (entity.submitted === true) {
    facts.push(
      entity.submitted_sim_hour != null ? `Alert sent at hour ${entity.submitted_sim_hour}` : "Alert sent",
    );
  } else if (entity.submitted === false) {
    facts.push("No alert sent");
  }
  if (entity.is_available === false) facts.push("No longer available");

  return {
    postId: entity.post_id ?? null,
    handle: entity.creator_handle ?? "unknown",
    caption: entity.caption ?? null,
    status: entity.status ?? entity.status_now ?? null,
    facts,
  };
}

/** The sources behind one specific answer — resolved by matching the
 * creators the reply actually named (@handle) against the entities in that
 * same reply's facts blob. This is what makes a citation mean something:
 * it's the post the sentence was about, with that post's own numbers, not
 * the same program-wide totals pasted under every answer. Falls back to
 * the selected post when the reply named no one (a whole-program summary),
 * and to nothing at all rather than citing something the answer never
 * mentioned. */
export function agentReferences(
  replyText: string,
  factsUsed: Record<string, unknown> | undefined,
): AgentReference[] {
  if (!factsUsed) return [];

  const selected = factsUsed.selected_post as AgentFactsEntity | null | undefined;
  const movers = (factsUsed.top_movers as AgentFactsEntity[] | undefined) ?? [];
  const alerts = (factsUsed.alerts as AgentFactsEntity[] | undefined) ?? [];
  const breakouts = (factsUsed.breakouts as AgentFactsEntity[] | undefined) ?? [];

  // Priority order: the post the manager is actually looking at, then the
  // movers (richest live numbers), then alert/breakout history.
  const pool: AgentFactsEntity[] = [...(selected ? [selected] : []), ...movers, ...alerts, ...breakouts];

  const seen = new Set<string>();
  const references: AgentReference[] = [];
  for (const match of replyText.matchAll(/@([a-zA-Z0-9._]+)/g)) {
    const handle = match[1];
    if (seen.has(handle)) continue;
    const entity = pool.find((candidate) => candidate.creator_handle === handle);
    if (!entity) continue;
    seen.add(handle);
    references.push(toReference(entity));
  }

  if (references.length === 0 && selected?.creator_handle) {
    references.push(toReference(selected));
  }
  return references;
}

/** The one-line program footing under an answer's references — the scope
 * the answer was drawn from, stated once rather than repeated as cards. */
export function agentProgramContext(factsUsed: Record<string, unknown> | undefined): string | null {
  if (!factsUsed) return null;

  const parts: string[] = [];
  const program = factsUsed.program as AgentFactsProgram | undefined;
  if (program?.posts_watched != null) parts.push(`${program.posts_watched} posts`);
  if (program?.creators_watched != null) parts.push(`${program.creators_watched} creators`);
  const breakouts = factsUsed.breakouts as unknown[] | undefined;
  if (breakouts?.length) parts.push(`${breakouts.length} breakouts`);
  const alerts = factsUsed.alerts as { submitted?: boolean }[] | undefined;
  const sent = alerts?.filter((a) => a.submitted).length ?? 0;
  if (sent > 0) parts.push(`${sent} alerts sent`);

  return parts.length > 0 ? parts.join(" · ") : null;
}
