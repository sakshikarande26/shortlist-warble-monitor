// Small hand-rolled stroke icons for Nav.tsx — no icon library dependency,
// matching this codebase's convention (GrowthChart/Sparkline hand-roll
// their own SVG rather than pulling in a charting package). Every icon is
// 18x18, currentColor stroke, no fill, so it inherits whatever text color
// the nav link applies (muted by default, accent when active).

type IconProps = { className?: string };

const BASE = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none" } as const;
const STROKE = { stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

export function HomeIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className} aria-hidden="true">
      <path d="M3 11.5 12 4l9 7.5" {...STROKE} />
      <path d="M5.5 10v9a1 1 0 0 0 1 1H10v-6h4v6h3.5a1 1 0 0 0 1-1v-9" {...STROKE} />
    </svg>
  );
}

export function CreatorsIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className} aria-hidden="true">
      <circle cx="9" cy="8" r="3" {...STROKE} />
      <path d="M3.5 19c.7-3 2.9-4.5 5.5-4.5s4.8 1.5 5.5 4.5" {...STROKE} />
      <circle cx="17" cy="8.5" r="2.4" {...STROKE} />
      <path d="M15 14.8c2.1.2 3.7 1.6 4.3 4" {...STROKE} />
    </svg>
  );
}

export function BreakoutsIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className} aria-hidden="true">
      <path d="M13 3 4.5 13.5H11L9.5 21 18.5 9.5H12z" {...STROKE} strokeLinejoin="round" />
    </svg>
  );
}

export function UnavailableIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="8.25" {...STROKE} />
      <path d="M6.5 6.5l11 11" {...STROKE} />
    </svg>
  );
}

export function AgentIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className} aria-hidden="true">
      <path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4H6.5A2.5 2.5 0 0 1 4 13.5z" {...STROKE} strokeLinejoin="round" />
      <circle cx="9" cy="10" r="1" fill="currentColor" stroke="none" />
      <circle cx="12" cy="10" r="1" fill="currentColor" stroke="none" />
      <circle cx="15" cy="10" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function ScoreboardIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className} aria-hidden="true">
      <path d="M6 20V13M12 20V6M18 20V10" {...STROKE} />
    </svg>
  );
}

export function RefreshIcon({ className }: IconProps) {
  return (
    <svg {...BASE} className={className} aria-hidden="true">
      <path d="M4.5 12a7.5 7.5 0 0 1 12.6-5.5M19.5 12a7.5 7.5 0 0 1-12.6 5.5" {...STROKE} />
      <path d="M17.5 3.5v3.5H14M6.5 20.5V17H10" {...STROKE} />
    </svg>
  );
}
