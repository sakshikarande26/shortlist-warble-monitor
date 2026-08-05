import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getBreakoutLog } from "../lib/api";
import type { BreakoutLogEntry, BreakoutLogResponse } from "../lib/types";
import { formatMoment, formatViews } from "../lib/copy";
import type { LoadState } from "../lib/loadState";
import { SkeletonCard, SkeletonLine } from "../components/states/Skeleton";
import { EmptyState } from "../components/states/EmptyState";
import { ErrorState } from "../components/states/ErrorState";

export function BreakoutLog() {
  const [state, setState] = useState<LoadState<BreakoutLogResponse>>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    getBreakoutLog()
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : "Couldn't load breakouts.";
        setState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[26px] leading-snug font-bold tracking-tight text-ink sm:text-[30px]">
          Breakouts
        </p>
        <p className="mt-1 text-sm text-ink-muted">
          Every post that has broken out so far, newest first.
        </p>
      </div>

      {state.status === "loading" && <BreakoutSkeleton />}
      {state.status === "error" && <ErrorState message={state.message} onRetry={load} />}
      {state.status === "ready" &&
        (state.data.entries.length === 0 ? (
          <EmptyState
            title="No breakouts yet"
            message="Once a post sustains unusually fast growth, it will be recorded here."
          />
        ) : (
          <div className="space-y-3">
            {state.data.entries.map((entry) => (
              <BreakoutRow key={entry.post_id} entry={entry} />
            ))}
          </div>
        ))}
    </div>
  );
}

function BreakoutRow({ entry }: { entry: BreakoutLogEntry }) {
  return (
    <Link
      to={`/posts/${entry.post_id}`}
      className="block rounded-xl border border-line bg-white/80 px-5 py-4 transition-colors hover:bg-white/90"
    >
      <div className="flex items-center gap-2">
        <span className="truncate text-sm font-medium text-ink">@{entry.creator_handle}</span>
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-black/[0.05] px-2.5 py-0.5 text-[11px] tracking-wide text-ink-muted">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-ink-muted/50" />
          {entry.current_status_label}
        </span>
      </div>

      {entry.caption && (
        <p className="mt-1 truncate text-sm text-ink-muted">"{entry.caption}"</p>
      )}

      {/* Each stat gets its own nested surface so the numbers read as a
          set of readings rather than one dense line of text. */}
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Broke out" value={formatMoment(entry.breakout_at)} />
        <Stat label="Views at breakout" value={formatViews(entry.views_at_breakout)} />
        <Stat label="Peak views" value={formatViews(entry.peak_views)} />
        <Stat
          label="Climbed"
          value={entry.growth_multiple !== null ? `${entry.growth_multiple.toFixed(1)}×` : "Not enough history"}
        />
      </div>
    </Link>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-line bg-white/85 px-3 py-2">
      <p className="text-[10px] tracking-wider text-ink-muted uppercase">{label}</p>
      <p className="mt-0.5 text-sm font-medium text-ink tabular-nums">{value}</p>
    </div>
  );
}

function BreakoutSkeleton() {
  return (
    <div className="space-y-3">
      <SkeletonLine width="w-1/3" />
      <SkeletonCard />
      <SkeletonCard />
    </div>
  );
}
