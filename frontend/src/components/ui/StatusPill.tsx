// Clear, distinct signal colors: orange for "needs attention now," green
// for "promising." Steady stays neutral grey (nothing unusual to flag).
const PILL_STYLES: Record<string, string> = {
  "Taking off": "bg-taking-off-soft text-taking-off font-medium",
  "Worth watching": "bg-watching-soft text-watching font-medium",
  Steady: "bg-black/[0.04] text-ink-muted",
  Unavailable: "bg-unavailable-soft text-unavailable",
};

const DOT_COLOR: Record<string, string> = {
  "Taking off": "bg-taking-off",
  "Worth watching": "bg-watching",
  Steady: "bg-ink-muted",
  Unavailable: "bg-unavailable",
};

// Reused by rows that want their sparkline to echo the status color
// (via currentColor) rather than a plain badge.
const STATUS_TEXT_COLOR: Record<string, string> = {
  "Taking off": "text-taking-off",
  "Worth watching": "text-watching",
  Steady: "text-ink-muted",
  Unavailable: "text-unavailable",
};

export function statusTextColorClass(label: string): string {
  return STATUS_TEXT_COLOR[label] ?? "text-ink-muted";
}

export function StatusPill({ label }: { label: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] tracking-wide ${PILL_STYLES[label] ?? "bg-black/[0.04] text-ink-muted"}`}
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT_COLOR[label] ?? "bg-ink-muted"}`} />
      {label}
    </span>
  );
}
