import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getBreakoutLog } from "../lib/api";
import type { BreakoutLogResponse } from "../lib/types";
import { formatMonitoringProgress, formatRelativeSimTime } from "../lib/copy";
import { SkeletonCard, SkeletonLine } from "../components/states/Skeleton";
import { EmptyState } from "../components/states/EmptyState";
import { ErrorState } from "../components/states/ErrorState";
import { Surface } from "../components/ui/Surface";
import { StatusPill } from "../components/ui/StatusPill";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: BreakoutLogResponse };

export function BreakoutLog() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  const load = useCallback(() => {
    setState({ status: "loading" });
    getBreakoutLog()
      .then((data) => setState({ status: "ready", data }))
      .catch((error: unknown) => {
        const message = error instanceof ApiError ? error.message : "Couldn't load the breakout log.";
        setState({ status: "error", message });
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[26px] leading-snug font-medium tracking-tight text-ink sm:text-[30px]">
          Breakout log
        </p>
        <p className="mt-1 text-sm text-ink-muted">
          Every confirmed breakout alert this monitoring week, newest first.
        </p>
      </div>

      {state.status === "loading" && <BreakoutLogSkeleton />}
      {state.status === "error" && <ErrorState message={state.message} onRetry={load} />}
      {state.status === "ready" && <BreakoutLogContent data={state.data} />}
    </div>
  );
}

function BreakoutLogContent({ data }: { data: BreakoutLogResponse }) {
  const { entries, window_end_sim_hours } = data;
  const progress =
    window_end_sim_hours !== null ? formatMonitoringProgress(window_end_sim_hours) : "Day 1 of 7";

  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 text-[15px] font-medium text-ink">This week ({progress})</h2>
        {entries.length === 0 ? (
          <EmptyState
            title="No breakouts confirmed yet this week"
            message="Once a post is confirmed taking off and an alert is sent, it will show up here."
          />
        ) : (
          <Surface className="divide-y divide-line">
            {entries.map((entry) => (
              <Link
                key={entry.post_id}
                to={`/posts/${entry.post_id}`}
                className="flex items-center gap-4 px-4 py-4 transition-colors hover:bg-black/[0.02] sm:px-6"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-ink">
                      @{entry.creator_handle}
                    </span>
                    <StatusPill label={entry.status_label} />
                    {!entry.submitted && (
                      <span className="text-[11px] text-ink-muted">(not confirmed sent)</span>
                    )}
                  </div>
                  {entry.caption && (
                    <p className="mt-0.5 truncate text-sm text-ink-muted">{entry.caption}</p>
                  )}
                  <p className="mt-1 text-xs text-ink-muted">
                    {formatRelativeSimTime(entry.decided_sim_hours, window_end_sim_hours)}
                  </p>
                </div>
              </Link>
            ))}
          </Surface>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-[15px] font-medium text-ink">History</h2>
        <EmptyState
          title="No earlier weeks yet"
          message="This is the first monitoring week on record. Past weekly logs will appear here once a new monitoring week begins."
        />
      </section>
    </div>
  );
}

function BreakoutLogSkeleton() {
  return (
    <div className="space-y-3">
      <SkeletonLine width="w-1/3" />
      <SkeletonCard />
      <SkeletonCard />
    </div>
  );
}
