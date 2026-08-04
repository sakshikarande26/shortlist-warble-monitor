import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getCreators } from "../lib/api";
import type { CreatorRosterEntry, CreatorsResponse } from "../lib/types";
import { formatFollowers, formatRelativeSimTime, getInitials, performanceStatement } from "../lib/copy";
import type { LoadState } from "../lib/loadState";
import { SkeletonCard, SkeletonLine } from "../components/states/Skeleton";
import { EmptyState } from "../components/states/EmptyState";
import { ErrorState } from "../components/states/ErrorState";
import { Sparkline } from "../components/Sparkline";
import { statusTextColorClass } from "../components/ui/StatusPill";

// No separate "Needs attention" filter: it's exactly the union of the two
// specific ones below, so it returns an identical list whenever only one
// kind of signal is present.
type Filter = "all" | "taking_off" | "worth_watching";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "taking_off", label: "Taking off" },
  { id: "worth_watching", label: "Worth watching" },
];

function matchesFilter(creator: CreatorRosterEntry, filter: Filter): boolean {
  switch (filter) {
    case "taking_off":
      return creator.taking_off_count > 0;
    case "worth_watching":
      return creator.worth_watching_count > 0;
    case "all":
    default:
      return true;
  }
}

export function Creators() {
  const [state, setState] = useState<LoadState<CreatorsResponse>>({ status: "loading" });
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const load = useCallback(() => {
    setState({ status: "loading" });
    getCreators()
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : "Couldn't load creators.";
        setState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const needingAttentionCount =
    state.status === "ready" ? state.data.creators.filter((c) => c.needs_attention_count > 0).length : 0;

  // Not a directory of everyone equally — a portfolio prioritized for
  // action. The roster arrives from the backend already sorted by needs
  // attention first (routes.py), so filtering here never needs to re-sort.
  const filtered = useMemo(() => {
    if (state.status !== "ready") return [];
    const query = search.trim().toLowerCase();
    return state.data.creators
      .filter((c) => matchesFilter(c, filter))
      .filter((c) => query === "" || c.handle.toLowerCase().includes(query));
  }, [state, filter, search]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[26px] leading-snug font-bold tracking-tight text-ink sm:text-[30px]">
          Creator portfolio
        </p>
        {state.status === "ready" && (
          <p className="mt-1 text-sm text-ink-muted">
            {state.data.creators.length} creator{state.data.creators.length === 1 ? "" : "s"} monitored
            on Warble · {needingAttentionCount} currently need{needingAttentionCount === 1 ? "s" : ""}{" "}
            attention.
          </p>
        )}
      </div>

      {state.status === "ready" && state.data.creators.length > 0 && (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-2">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
                  filter === f.id
                    ? "border-accent bg-accent-soft text-accent"
                    : "border-line text-ink-muted hover:border-ink/20 hover:text-ink"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by handle..."
            className="w-full max-w-xs rounded-full border border-line bg-white/60 px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:border-accent focus:outline-none"
          />
        </div>
      )}

      {state.status === "loading" && <CreatorsSkeleton />}
      {state.status === "error" && <ErrorState message={state.message} onRetry={load} />}
      {state.status === "ready" && (
        <CreatorsList creators={filtered} currentSimHours={state.data.current_sim_hours} empty={state.data.creators.length === 0} />
      )}
    </div>
  );
}

function CreatorsList({
  creators,
  currentSimHours,
  empty,
}: {
  creators: CreatorRosterEntry[];
  currentSimHours: number | null;
  empty: boolean;
}) {
  if (empty) {
    return (
      <EmptyState
        title="No creators tracked yet"
        message="Once creators are enrolled in the program, they'll show up here."
      />
    );
  }
  if (creators.length === 0) {
    return (
      <EmptyState
        title="No creators match"
        message="Try a different filter or search term."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {creators.map((creator) => (
        <CreatorCard key={creator.id} creator={creator} currentSimHours={currentSimHours} />
      ))}
    </div>
  );
}

// Horizontal cards in a grid, not a single stacked list — each creator
// gets its own bordered box so the roster reads as a portfolio to scan
// side by side, not a long vertical feed.
function CreatorCard({ creator, currentSimHours }: { creator: CreatorRosterEntry; currentSimHours: number | null }) {
  return (
    <Link
      to={`/creators/${creator.id}`}
      className="group flex h-full flex-col gap-3 rounded-2xl border border-line bg-white p-4 transition-colors hover:border-ink/20 sm:p-5"
    >
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-black/[0.04] text-sm font-medium text-ink">
          {getInitials(creator.handle)}
        </div>
        <div className="min-w-0 flex-1">
          <span className="truncate text-sm font-medium text-ink">@{creator.handle}</span>
          <p className="text-xs text-ink-muted">
            {formatFollowers(creator.followers)} · {creator.active_post_count} tracked post
            {creator.active_post_count === 1 ? "" : "s"}
          </p>
        </div>
        {creator.strongest_post && creator.strongest_post.sparkline.length > 1 && (
          <div className={`hidden shrink-0 sm:block ${statusTextColorClass(creator.strongest_post.status_label)}`}>
            <Sparkline values={creator.strongest_post.sparkline} width={64} height={26} />
          </div>
        )}
      </div>

      <NeedsAttentionBreakdown creator={creator} />

      {creator.active_post_count === 0 ? (
        <p className="text-sm text-ink-muted">No active posts right now</p>
      ) : creator.strongest_post ? (
        <div>
          <p className="text-[11px] font-medium tracking-wide text-ink-muted uppercase">
            Strongest current signal
          </p>
          {creator.strongest_post.caption && (
            <p className="mt-1 truncate text-sm text-ink">"{creator.strongest_post.caption}"</p>
          )}
          <p className="mt-0.5 text-sm text-ink-muted">
            {performanceStatement({
              is_gone: false,
              status_label: creator.strongest_post.status_label,
              evidence: creator.strongest_post.evidence,
            })}
          </p>
        </div>
      ) : (
        <p className="text-sm text-ink-muted">Not enough history for comparison</p>
      )}

      <div className="mt-auto flex items-center justify-between gap-2 pt-1">
        <p className="text-xs text-ink-muted">
          {creator.latest_sim_hours !== null
            ? formatRelativeSimTime(creator.latest_sim_hours, currentSimHours)
            : "No updates yet"}
        </p>
        <span className="text-xs font-medium text-ink-muted opacity-0 transition-opacity group-hover:opacity-100">
          View creator &rarr;
        </span>
      </div>
    </Link>
  );
}

function NeedsAttentionBreakdown({ creator }: { creator: CreatorRosterEntry }) {
  if (creator.needs_attention_count === 0) {
    return <p className="mt-1 text-sm text-ink-muted">No posts need attention</p>;
  }
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-1.5 text-sm">
      {creator.taking_off_count > 0 && (
        <span className="font-medium text-taking-off">
          {creator.taking_off_count} Taking off
        </span>
      )}
      {creator.taking_off_count > 0 && creator.worth_watching_count > 0 && (
        <span className="text-ink-muted">·</span>
      )}
      {creator.worth_watching_count > 0 && (
        <span className="font-medium text-watching">
          {creator.worth_watching_count} Worth watching
        </span>
      )}
    </p>
  );
}

function CreatorsSkeleton() {
  return (
    <div className="space-y-3">
      <SkeletonLine width="w-1/3" />
      <SkeletonCard />
      <SkeletonCard />
    </div>
  );
}
