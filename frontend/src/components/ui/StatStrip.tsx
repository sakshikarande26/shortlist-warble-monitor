import { Link } from "react-router-dom";

interface StatCellData {
  label: string;
  value: string;
  sub?: string;
  to?: string;
}

// Horizontal row of stat cells divided by hairline borders — not separate
// floating cards. Tiny uppercase label, large tabular number, tiny muted
// sub-label.
export function StatStrip({ cells }: { cells: StatCellData[] }) {
  return (
    <div className="grid grid-cols-3 divide-x divide-line rounded-xl border border-line sm:grid-cols-3">
      {cells.map((cell) => {
        const content = (
          <>
            <p className="text-[11px] font-medium tracking-wider text-ink-muted uppercase">
              {cell.label}
            </p>

            <p className="mt-1 text-[26px] leading-none font-medium tracking-tight text-ink tabular-nums sm:text-[28px]">
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