import { useEffect, useState } from "react";
import { getStatus } from "../../lib/api";
import { RefreshIcon } from "./NavIcons";

const TICK_MS = 30_000; // coarse — this is a UI-freshness hint, not a stopwatch

// Full-width glass bar above the nav+main and agent cards — same visual
// language (rounded-3xl border bg-board shadow backdrop-blur) as the cards
// below it, just spanning both.
export function TopBar() {
  // Real wall-clock time of the last successful fetch (not sim time) —
  // "how long ago did this browser last talk to the server," a UI
  // freshness claim distinct from CLAUDE.md's sim-clock-only rule for
  // post/creator data timestamps.
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const [, forceTick] = useState(0);

  function refresh() {
    getStatus()
      .then(() => setLastFetchedAt(new Date()))
      .catch(() => {
        // Best-effort only: the bar just won't show a freshness label.
      });
  }

  useEffect(() => {
    refresh();
    const interval = setInterval(() => forceTick((n) => n + 1), TICK_MS);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="relative flex shrink-0 items-center justify-between rounded-3xl border border-line bg-board px-6 py-3 shadow-[0_20px_60px_rgb(0_0_0_/_10%)] backdrop-blur-[24px] sm:px-8">
      <p className="pointer-events-none absolute left-1/2 -translate-x-1/2 text-center text-sm font-bold text-ink sm:text-base">
        Shortlist Brand Performance Monitor
      </p>
      <div className="ml-auto flex items-center gap-3">
        {lastFetchedAt && (
          <span className="text-xs text-ink-muted">
            Last updated {formatMinutesAgo(lastFetchedAt)}
          </span>
        )}
        <button
          type="button"
          onClick={() => {
            refresh();
            window.location.reload();
          }}
          className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-ink-muted transition-colors hover:bg-black/[0.05] hover:text-ink"
        >
          <RefreshIcon className="shrink-0" />
          Refresh
        </button>
      </div>
    </div>
  );
}

function formatMinutesAgo(since: Date): string {
  const minutes = Math.round((Date.now() - since.getTime()) / 60_000);
  if (minutes < 1) return "moments ago";
  return `${minutes}m ago`;
}
