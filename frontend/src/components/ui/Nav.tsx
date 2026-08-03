import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { label: "Home", to: "/" },
  { label: "Creator portfolio", to: "/creators" },
  { label: "Breakout log", to: "/breakouts" },
];

// Slim, calm sidebar — a hairline divider carries the separation from the
// center column, not a heavy panel treatment. The marketing agent chat is
// opened from its own edge tab on the right (AppShell), not from here.
export function Nav() {
  return (
    <nav className="flex w-[220px] shrink-0 flex-col border-r border-line px-6 py-10">
      <div className="mb-10">
        <p className="text-[17px] font-medium tracking-tight text-ink">LongSheet</p>
        <p className="mt-0.5 text-[13px] text-ink-muted">Performance Monitor</p>
      </div>

      <div className="flex flex-col gap-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive ? "bg-black/[0.05] font-medium text-ink" : "text-ink-muted hover:bg-black/[0.03] hover:text-ink"
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </div>

      {/* This board is scoped to one connected platform, Warble, the way
          other tools in the account might connect Instagram or TikTok
          instead. A small badge, not a switcher, since only Warble exists
          today. */}
      <div className="mt-auto border-t border-line pt-4">
        <p className="text-[11px] font-medium tracking-wider text-ink-muted uppercase">Platform</p>
        <div className="mt-2 flex items-center gap-2">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-ink" />
          <span className="text-sm text-ink">Monitoring on Warble</span>
        </div>
      </div>
    </nav>
  );
}
