import { Link } from "react-router-dom";

// Semantic-only palette — the same four meanings used everywhere else in
// the app (StatusPill's dot colors, Creators.tsx's NeedsAttentionBreakdown)
// plus the one brand accent. A stat cell's color always means the same
// thing it means elsewhere; this never introduces a new color language.
export type StatCellColor = "ink" | "accent" | "taking-off" | "watching" | "unavailable";

const NUMBER_COLOR: Record<StatCellColor, string> = {
  ink: "text-ink",
  accent: "text-accent",
  "taking-off": "text-taking-off",
  watching: "text-watching",
  unavailable: "text-unavailable",
};

const DOT_COLOR: Record<StatCellColor, string> = {
  ink: "bg-ink-muted",
  accent: "bg-accent",
  "taking-off": "bg-taking-off",
  watching: "bg-watching",
  unavailable: "bg-unavailable",
};

interface StatCellData {
  label: string;
  value: string;
  sub?: string;
  to?: string;
  color?: StatCellColor;
}

// Horizontal row of stat cells divided by hairline borders — not separate
// floating cards. Tiny uppercase label (with a small color dot echoing
// what the number means), large tabular number in that same semantic
// color, tiny muted sub-label. Wraps to multiple rows on narrow screens,
// still divided by hairlines on every axis.
export function StatStrip({ cells }: { cells: StatCellData[] }) {
  return (
    <div className="grid grid-cols-2 divide-x divide-y divide-line rounded-xl border border-line sm:grid-cols-3 lg:grid-cols-6">
      {cells.map((cell) => {
        const color = cell.color ?? "ink";
        const content = (
          <>
            <p className="flex items-center gap-1.5 text-[11px] font-medium tracking-wider text-ink-muted uppercase">
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT_COLOR[color]}`} />
              {cell.label}
            </p>

            <p
              className={`mt-1 text-[26px] leading-none font-medium tracking-tight tabular-nums sm:text-[28px] ${NUMBER_COLOR[color]}`}
            >
              {cell.value}
            </p>

            {cell.sub && (
              <p className="mt-1 text-[13px] text-ink-muted">
                {cell.sub}
              </p>
            )}
          </>
        );

        const className = `block px-4 py-3 sm:px-6 sm:py-4 ${
          cell.to
            ? "transition-colors hover:bg-black/[0.03]"
            : ""
        }`;

        return cell.to ? (
          <Link
            key={cell.label}
            to={cell.to}
            className={className}
          >
            {content}
          </Link>
        ) : (
          <div
            key={cell.label}
            className={className}
          >
            {content}
          </div>
        );
      })}
    </div>
  );
}