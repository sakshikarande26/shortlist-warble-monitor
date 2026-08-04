import type { ReactNode } from "react";

// A lighter surface nested on the board: hairline border, near-transparent
// fill, smaller radius. Layered by border + spacing, not by shadow.
export function Surface({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-line bg-white/80 ${className}`}>{children}</div>;
}

export function DashedSurface({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-dashed border-line ${className}`}>{children}</div>;
}
