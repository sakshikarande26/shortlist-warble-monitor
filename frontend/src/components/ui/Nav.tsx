import { NavLink } from "react-router-dom";
import { AgentIcon, BreakoutsIcon, CloseIcon, CreatorsIcon, HomeIcon, ScoreboardIcon } from "./NavIcons";

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
//
// Below `lg`, this is a fixed-position drawer that slides in from the left
// (transform, driven by `isOpen`) over the rest of the app; at `lg` and up
// the lg: overrides put it back in normal flow as the persistent sidebar,
// where `isOpen`/`onClose` are simply never triggered (no toggle exists at
// that width). `position: fixed` here is intentionally NOT clipped by the
// card's own `overflow-hidden` — only an ancestor with `transform`/`filter`/
// `perspective` would establish a containing block that traps it, and
// nothing between here and the viewport does, so it correctly covers the
// full screen rather than just the card.
export function Nav({
  isAgentOpen,
  isOpen,
  onOpenAgent,
  onClose,
  onNavigate,
}: {
  isAgentOpen: boolean;
  isOpen: boolean;
  onOpenAgent: () => void;
  onClose: () => void;
  onNavigate: () => void;
}) {
  return (
    <nav
      className={`fixed inset-y-0 left-0 z-50 flex w-[240px] shrink-0 flex-col border-r border-line bg-board px-6 py-8 shadow-[0_20px_60px_rgb(0_0_0_/_20%)] backdrop-blur-[24px] transition-transform duration-200 ease-out lg:static lg:z-auto lg:w-[220px] lg:translate-x-0 lg:bg-transparent lg:py-10 lg:shadow-none lg:backdrop-blur-none lg:transition-none ${
        isOpen ? "translate-x-0" : "-translate-x-full"
      }`}
    >
      <div className="mb-10 flex items-center justify-between">
        <p className="text-[19px] font-bold tracking-tight text-ink">LongSheet</p>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close menu"
          className="rounded-lg p-1 text-ink-muted hover:bg-black/[0.03] hover:text-ink lg:hidden"
        >
          <CloseIcon />
        </button>
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
          onClick={() => {
            onOpenAgent();
            onClose(); // no-op at lg+; closes the mobile drawer over it below lg
          }}
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
