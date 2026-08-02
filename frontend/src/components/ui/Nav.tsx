import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { label: "Home", to: "/" },
  { label: "Creators", to: "/creators" },
];

// Slim, calm sidebar — a hairline divider carries the separation from the
// center column, not a heavy panel treatment.
export function Nav() {
  return (
    <nav className="flex w-[220px] shrink-0 flex-col border-r border-line px-6 py-10">
      <div className="mb-10">
        <p className="text-[17px] font-medium tracking-tight text-ink">LongSheet</p>
        <p className="mt-0.5 text-[13px] text-ink-muted">Creator Content Performance</p>
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
    </nav>
  );
}
