import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getStatus } from "../../lib/api";
import { invalidateCache, useCachedResource } from "../../lib/dataCache";
import { monitoringStateLabel } from "../../lib/copy";
import type { MonitoringState, SystemStatus } from "../../lib/types";
import { MenuIcon, RefreshIcon } from "./NavIcons";

const TICK_MS = 30_000; // coarse — this is a UI-freshness hint, not a stopwatch

// Pastel/soft per state, not the saturated dot color — a light, quiet badge
// that still shifts hue when something's actually wrong, rather than a loud
// traffic light sitting in the header at all times.
const HEALTH_PILL_CLASS: Record<MonitoringState, string> = {
  live: "bg-monitor-live-soft text-monitor-live",
  delayed: "bg-monitor-delayed-soft text-monitor-delayed",
  interrupted: "bg-monitor-interrupted-soft text-monitor-interrupted",
  complete: "bg-monitor-complete-soft text-monitor-complete",
};

const HEALTH_DOT_CLASS: Record<MonitoringState, string> = {
  live: "bg-monitor-live",
  delayed: "bg-monitor-delayed",
  interrupted: "bg-monitor-interrupted",
  complete: "bg-monitor-complete",
};

// Real liveness, not a static placeholder: shares the "status" cache key
// (and its ~60s poll cadence) with the /status page via useCachedResource,
// so this never fires its own extra request. Label always reads "System
// health" — the actual state ("Monitoring live" / "delayed" / "interrupted")
// is the hover tooltip, same pattern as StatusPill's fixed labels. The pill
// links to /status for the full picture.
function SystemHealthIndicator() {
  const { state } = useCachedResource<SystemStatus>("status", getStatus, "Couldn't load status");
  const monitoringState = state.status === "ready" ? state.data.monitoring_state : null;

  const pillClass = monitoringState ? HEALTH_PILL_CLASS[monitoringState] : "bg-black/[0.04] text-ink-muted";
  const dotClass = monitoringState ? HEALTH_DOT_CLASS[monitoringState] : "bg-ink-muted/40";
  const title = monitoringState ? monitoringStateLabel(monitoringState) : "Checking monitoring status…";

  return (
    <Link
      to="/status"
      title={title}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium tracking-wide transition-opacity hover:opacity-80 ${pillClass}`}
    >
      <span className="relative flex h-1.5 w-1.5 shrink-0">
        {monitoringState === "live" && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-monitor-live opacity-60" />
        )}
        <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${dotClass}`} />
      </span>
      System health
    </Link>
  );
}

// Full-width glass bar above the nav+main and agent cards — same visual
// language (rounded-3xl border bg-board shadow backdrop-blur) as the cards
// below it, just spanning both.
export function TopBar({ onToggleNav }: { onToggleNav: () => void }) {
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
    // A flex row of three sections (rather than the title absolutely
    // centered over static siblings) so the title truncates instead of
    // overlapping the hamburger/health pill or the refresh button once the
    // bar gets narrower than all four can comfortably fit — the failure
    // mode on a phone with the old absolute-positioned version.
    <div className="relative flex shrink-0 items-center gap-3 rounded-3xl border border-line bg-board px-4 py-3 shadow-[0_20px_60px_rgb(0_0_0_/_10%)] backdrop-blur-[24px] sm:px-8">
      <div className="flex shrink-0 items-center gap-3">
        <button
          type="button"
          onClick={onToggleNav}
          aria-label="Open menu"
          className="rounded-lg p-1.5 text-ink-muted hover:bg-black/[0.05] hover:text-ink lg:hidden"
        >
          <MenuIcon />
        </button>
        <SystemHealthIndicator />
      </div>
      <p className="min-w-0 flex-1 truncate text-center text-sm font-bold text-ink sm:text-base">
        Shortlist Brand Performance Monitor
      </p>
      <div className="flex shrink-0 items-center gap-3">
        {lastFetchedAt && (
          <span className="hidden text-xs text-ink-muted sm:inline">
            Last updated {formatMinutesAgo(lastFetchedAt)}
          </span>
        )}
        <button
          type="button"
          onClick={() => {
            // Drop every cached page, then reload — otherwise the reboot
            // would repopulate from the same stale entries and "Refresh"
            // would be a no-op.
            invalidateCache();
            refresh();
            window.location.reload();
          }}
          aria-label="Refresh"
          className="flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-xs font-medium text-ink-muted transition-colors hover:bg-black/[0.05] hover:text-ink sm:px-3"
        >
          <RefreshIcon className="shrink-0" />
          <span className="hidden sm:inline">Refresh</span>
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
