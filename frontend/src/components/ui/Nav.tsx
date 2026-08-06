import { Link, NavLink } from "react-router-dom";
import { AgentIcon, BreakoutsIcon, CreatorsIcon, HomeIcon, ScoreboardIcon } from "./NavIcons";
import { getStatus } from "../../lib/api";
import { useCachedResource } from "../../lib/dataCache";
import { monitoringStateLabel } from "../../lib/copy";
import type { MonitoringState, SystemStatus } from "../../lib/types";

const NAV_ITEMS = [
  { label: "Home", to: "/", Icon: HomeIcon },
  { label: "Track program posts", to: "/posts", Icon: ScoreboardIcon },
  { label: "Creator portfolio", to: "/creators", Icon: CreatorsIcon },
  { label: "Breakouts", to: "/breakouts", Icon: BreakoutsIcon },
];

const MONITOR_DOT_CLASS: Record<MonitoringState, string> = {
  live: "bg-monitor-live",
  delayed: "bg-monitor-delayed",
  interrupted: "bg-monitor-interrupted",
};

// Real liveness, not a static placeholder: shares the "status" cache key (and
// its ~60s poll cadence) with every other consumer of getStatus() via
// useCachedResource, so this never fires its own extra request. Color, not
// just dot fill, carries the signal here — deliberately: "interrupted" needs
// to read as unmistakably wrong at a glance, not just a differently-filled
// dot next to otherwise-identical grey text. Whole row links to /status.
function MonitoringIndicator() {
  const { state } = useCachedResource<SystemStatus>("status", getStatus, "Couldn't load status");
  const monitoringState = state.status === "ready" ? state.data.monitoring_state : null;

  const label = monitoringState ? monitoringStateLabel(monitoringState) : "Checking monitoring status…";
  const dotClass = monitoringState ? MONITOR_DOT_CLASS[monitoringState] : "bg-ink-muted/40";

  return (
    <Link
      to="/status"
      title={label}
      className="mt-2 flex items-center gap-2 text-xs text-ink-muted transition-colors hover:text-ink"
    >
      <span className="relative flex h-2 w-2 shrink-0">
        {monitoringState === "live" && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-monitor-live opacity-60" />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dotClass}`} />
      </span>
      <span className="truncate">{label}</span>
    </Link>
  );
}

// Slim, calm sidebar — a hairline divider carries the separation from the
// center column, not a heavy panel treatment. The marketing agent chat's
// own edge tab (AppShell) still works; this adds a second, sidebar-native
// way in, via onOpenAgent, so the panel isn't only discoverable from the
// screen edge. "Unavailable" isn't in this list — the Momentum Board's
// Removed group is the entry point now; the /unavailable route still
// works for deep links.
// The agent is a panel, not a route, so `isAgentOpen` has to drive its
// highlight by hand — and suppress the routed link's, since that page is no
// longer what's on screen. Without this the sidebar claims you're on Home
// while you're looking at the agent.
export function Nav({
  isAgentOpen,
  onOpenAgent,
  onNavigate,
}: {
  isAgentOpen: boolean;
  onOpenAgent: () => void;
  onNavigate: () => void;
}) {
  return (
    <nav className="flex w-[220px] shrink-0 flex-col border-r border-line px-6 py-10">
      <div className="mb-10">
        <p className="text-[19px] font-bold tracking-tight text-ink">LongSheet</p>
        <MonitoringIndicator />
      </div>

      <div className="flex flex-col gap-1">
        {NAV_ITEMS.map(({ label, to, Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive && !isAgentOpen
                  ? "bg-accent-soft font-medium text-accent"
                  : "text-ink-muted hover:bg-black/[0.03] hover:text-ink"
              }`
            }
          >
            <Icon className="shrink-0" />
            {label}
          </NavLink>
        ))}

        <button
          type="button"
          onClick={onOpenAgent}
          aria-current={isAgentOpen ? "page" : undefined}
          className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors ${
            isAgentOpen
              ? "bg-accent-soft font-medium text-accent"
              : "text-ink-muted hover:bg-black/[0.03] hover:text-ink"
          }`}
        >
          <AgentIcon className="shrink-0" />
          Marketing agent
        </button>
      </div>
    </nav>
  );
}
