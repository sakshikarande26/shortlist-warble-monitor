import { getStatus } from "../lib/api";
import type { MonitoringState, SamplingCoverageTick, SystemStatus } from "../lib/types";
import { useCachedResource } from "../lib/dataCache";
import { formatMoment, formatWallClockAgo, monitoringStateDetail, monitoringStateLabel } from "../lib/copy";
import { Surface } from "../components/ui/Surface";
import { SkeletonCard, SkeletonLine } from "../components/states/Skeleton";
import { ErrorState } from "../components/states/ErrorState";

// Deliberately minimal: plain-language state, when it was last checked, and
// what's being watched. No uptime %, no per-service rows, no incident log —
// this answers "should I trust what I'm looking at right now," nothing more.

const STATE_DOT_CLASS: Record<MonitoringState, string> = {
  live: "bg-monitor-live",
  delayed: "bg-monitor-delayed",
  interrupted: "bg-monitor-interrupted",
  complete: "bg-monitor-complete",
};

const STATE_TEXT_CLASS: Record<MonitoringState, string> = {
  live: "text-monitor-live",
  delayed: "text-monitor-delayed",
  interrupted: "text-monitor-interrupted",
  complete: "text-monitor-complete",
};

const STATE_CARD_CLASS: Record<MonitoringState, string> = {
  live: "bg-monitor-live-soft",
  delayed: "bg-monitor-delayed-soft",
  interrupted: "bg-monitor-interrupted-soft",
  complete: "bg-monitor-complete-soft",
};

export function Status() {
  const { state, refresh } = useCachedResource<SystemStatus>(
    // Same cache key the nav indicator polls — landing here never fires a
    // second request on top of the one the sidebar already keeps warm.
    "status",
    getStatus,
    "Couldn't load status.",
  );

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[26px] leading-snug font-bold tracking-tight text-ink sm:text-[30px]">
          Monitoring status
        </p>
        <p className="mt-1 text-sm text-ink-muted">Whether the collector is actively sampling right now.</p>
      </div>

      {state.status === "loading" && <StatusSkeleton />}
      {state.status === "error" && <ErrorState message={state.message} onRetry={refresh} />}
      {state.status === "ready" && <StatusContent data={state.data} />}
    </div>
  );
}

function StatusContent({ data }: { data: SystemStatus }) {
  const {
    monitoring_state,
    minutes_since_last_sample,
    last_sample_captured_at,
    posts_tracked,
    creators_tracked,
    sampling_coverage,
  } = data;

  return (
    <div className="space-y-6">
      <div
        className={`flex items-center gap-3 rounded-2xl border border-line px-5 py-4 sm:px-6 sm:py-5 ${STATE_CARD_CLASS[monitoring_state]}`}
      >
        <span className="relative flex h-3 w-3 shrink-0">
          {monitoring_state === "live" && (
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-monitor-live opacity-60" />
          )}
          <span className={`relative inline-flex h-3 w-3 rounded-full ${STATE_DOT_CLASS[monitoring_state]}`} />
        </span>
        <div>
          <p className={`text-[17px] font-semibold ${STATE_TEXT_CLASS[monitoring_state]}`}>
            {monitoringStateLabel(monitoring_state)}
          </p>
          <p className="mt-0.5 text-sm text-ink-muted">{monitoringStateDetail(monitoring_state)}</p>
        </div>
      </div>

      <Surface className="grid grid-cols-1 gap-4 px-5 py-4 sm:grid-cols-2 sm:px-6">
        <div>
          <p className="text-[11px] font-medium tracking-wider text-ink-muted uppercase">Last checked</p>
          <p
            className="mt-1 text-sm text-ink"
            title={last_sample_captured_at ? formatMoment(last_sample_captured_at) : undefined}
          >
            {formatWallClockAgo(minutes_since_last_sample)}
          </p>
        </div>
        <div>
          <p className="text-[11px] font-medium tracking-wider text-ink-muted uppercase">Coverage</p>
          <p className="mt-1 text-sm text-ink">
            Watching {posts_tracked} post{posts_tracked === 1 ? "" : "s"} across {creators_tracked} creator
            {creators_tracked === 1 ? "" : "s"}
          </p>
        </div>
      </Surface>

      {sampling_coverage.length > 0 && <CoverageStrip ticks={sampling_coverage} />}
    </div>
  );
}

function CoverageStrip({ ticks }: { ticks: SamplingCoverageTick[] }) {
  return (
    <Surface className="px-5 py-4 sm:px-6">
      <p className="text-[11px] font-medium tracking-wider text-ink-muted uppercase">Last 10 hours</p>
      <div className="mt-3 flex items-end gap-[3px] overflow-x-auto">
        {ticks.map((tick) => (
          <span
            key={tick.interval_start}
            title={`${formatMoment(tick.interval_start)} — ${tick.has_sample ? "sample captured" : "no sample"}`}
            className={`h-6 w-1.5 shrink-0 rounded-sm ${tick.has_sample ? "bg-ink" : "bg-black/[0.06]"}`}
          />
        ))}
      </div>
      <p className="mt-2 text-xs text-ink-muted">
        Each tick is a 15-minute window. Solid means at least one sample was captured; faint means a gap.
      </p>
    </Surface>
  );
}

function StatusSkeleton() {
  return (
    <div className="space-y-4">
      <SkeletonCard />
      <SkeletonLine width="w-1/2" />
    </div>
  );
}
