// Strictly greyscale: states are told apart by tint depth and weight, not
// hue. Darker + medium weight for the two states that matter most (Taking
// off, Watch closely); a lighter, uniform muted treatment for everything
// else; an outlined, faded treatment for archived/unavailable posts.
const PILL_STYLES: Record<string, string> = {
  "Taking off": "bg-black/[0.08] text-ink font-medium",
  "Watch closely": "bg-black/[0.06] text-ink font-medium",
  "Just jumped": "bg-black/[0.04] text-ink-muted",
  Steady: "bg-black/[0.04] text-ink-muted",
  "Slowing down": "bg-black/[0.04] text-ink-muted",
  "No longer available": "border border-line text-ink-muted/70",
};

export function StatusPill({ label }: { label: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full px-2.5 py-0.5 text-[11px] tracking-wide ${PILL_STYLES[label] ?? "bg-black/[0.04] text-ink-muted"}`}
    >
      {label}
    </span>
  );
}
