import { NavLink } from "react-router-dom";
import { AgentIcon, BreakoutsIcon, CreatorsIcon, HomeIcon, ScoreboardIcon } from "./NavIcons";

const NAV_ITEMS = [
  { label: "Home", to: "/", Icon: HomeIcon },
  { label: "Track program posts", to: "/posts", Icon: ScoreboardIcon },
  { label: "Creator portfolio", to: "/creators", Icon: CreatorsIcon },
  { label: "Breakouts", to: "/breakouts", Icon: BreakoutsIcon },
];

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
