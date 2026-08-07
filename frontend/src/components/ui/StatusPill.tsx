// Clear, distinct signal colors: orange for "needs attention now," green
// for "promising," red for "actually dropping." Steady stays neutral grey
// (nothing unusual to flag) — Declining deliberately does NOT share that
// grey, even though both are "not a mover": a flat post and a post losing
// views are different situations, and a marketer scanning for grey rows
// should never have to open one to find out it was quietly declining.
const PILL_STYLES: Record<string, string> = {
  "Taking off": "bg-taking-off-soft text-taking-off font-medium",
  "Worth watching": "bg-watching-soft text-watching font-medium",
  Steady: "bg-black/[0.04] text-ink-muted",
  Declining: "bg-declining-soft text-declining font-medium",
  Unavailable: "bg-unavailable-soft text-unavailable",
};

const DOT_COLOR: Record<string, string> = {
  "Taking off": "bg-taking-off",
  "Worth watching": "bg-watching",
  Steady: "bg-ink-muted",
  Declining: "bg-declining",
  Unavailable: "bg-unavailable",
};

// Reused by rows that want their sparkline to echo the status color
// (via currentColor) rather than a plain badge.
const STATUS_TEXT_COLOR: Record<string, string> = {
  "Taking off": "text-taking-off",
  "Worth watching": "text-watching",
  Steady: "text-ink-muted",
  Declining: "text-declining",
  Unavailable: "text-unavailable",
};

export function statusTextColorClass(label: string): string {
  return STATUS_TEXT_COLOR[label] ?? "text-ink-muted";
}

// One-line plain-language meaning per status, shown as a native tooltip.
// StatusPill renders everywhere a post's status appears (Home, Creators,
// Posts board, Breakout log, post detail, agent references) so this one
// map is what answers "what does this word mean" across the whole app.
const STATUS_EXPLANATION: Record<string, string> = {
  "Taking off": "Sustained growth well above normal for several checks in a row",
  "Worth watching": "Growing faster than usual for this creator right now",
  Steady: "No unusual movement",
  Declining: "Views have dropped in the latest check, still live",
  Unavailable: "No longer live on Warble",
};

export function StatusPill({ label }: { label: string }) {
  return (
    <span
      title={STATUS_EXPLANATION[label]}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] tracking-wide ${PILL_STYLES[label] ?? "bg-black/[0.04] text-ink-muted"}`}
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${DOT_COLOR[label] ?? "bg-ink-muted"}`} />
      {label}
    </span>
  );
}
