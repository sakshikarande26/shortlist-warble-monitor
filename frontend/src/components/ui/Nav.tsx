import { NavLink } from "react-router-dom";
import { AgentIcon, BreakoutsIcon, CreatorsIcon, HomeIcon, ScoreboardIcon } from "./NavIcons";

const NAV_ITEMS = [
  { label: "Home", to: "/", Icon: HomeIcon },
  { label: "Track program posts", to: "/posts", Icon: ScoreboardIcon },
  { label: "Creator portfolio", to: "/creators", Icon: CreatorsIcon },
  { label: "Breakouts", to: "/breakouts", Icon: BreakoutsIcon },
];

// Every platform this account could in principle connect — Warble is the
// only one actually live today. Shown honestly: one real, active
// connection and three plainly-labeled "not connected" placeholders, never
// implying functionality that doesn't exist.
const PLATFORMS: { label: string; mono: string; connected: boolean }[] = [
  { label: "Warble", mono: "W", connected: true },
  { label: "YouTube", mono: "YT", connected: false },
  { label: "TikTok", mono: "TT", connected: false },
  { label: "Instagram", mono: "IG", connected: false },
];

// Slim, calm sidebar — a hairline divider carries the separation from the
// center column, not a heavy panel treatment. The marketing agent chat's
// own edge tab (AppShell) still works; this adds a second, sidebar-native
// way in, via onOpenAgent, so the panel isn't only discoverable from the
// screen edge. "Unavailable" isn't in this list — the Momentum Board's
// Removed group is the entry point now; the /unavailable route still
// works for deep links.
export function Nav({ onOpenAgent }: { onOpenAgent: () => void }) {
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
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive
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
          className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm text-ink-muted transition-colors hover:bg-black/[0.03] hover:text-ink"
        >
          <AgentIcon className="shrink-0" />
          Marketing agent
        </button>
      </div>

      <div className="mt-auto border-t border-line pt-4">
        <p className="text-[11px] font-medium tracking-wider text-ink-muted uppercase">
          Under monitoring
        </p>
        <div className="mt-2 flex flex-col gap-1.5">
          {PLATFORMS.map((platform) => (
            <div key={platform.label} className="flex items-center gap-2">
              <span
                className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[9px] font-semibold ${
                  platform.connected
                    ? "bg-accent text-white"
                    : "border border-line text-ink-muted"
                }`}
              >
                {platform.mono}
              </span>
              <span className={`text-sm ${platform.connected ? "text-ink" : "text-ink-muted"}`}>
                {platform.label}
              </span>
              <span className="ml-auto text-[10px] text-ink-muted">
                {platform.connected ? "Connected" : "Not connected"}
              </span>
            </div>
          ))}
        </div>
      </div>
    </nav>
  );
}
