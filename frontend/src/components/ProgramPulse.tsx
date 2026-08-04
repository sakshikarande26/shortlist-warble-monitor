interface ProgramPulseProps {
  postsCount: number;
  needsAttentionCount: number;
  alertsReceivedCount: number;
}

interface PulseCardData {
  label: string;
  value: number;
}

// Three real numbers — reassurance that coverage is healthy, not a KPI
// dashboard. Plain black/white/grey cards on purpose: colour on this site
// is reserved for charts, signed metrics (red/green), and the breakout
// spotlight card — a bare count like "195 tracked posts" doesn't carry a
// direction or a status, so it doesn't get a tint.
export function ProgramPulse({ postsCount, needsAttentionCount, alertsReceivedCount }: ProgramPulseProps) {
  const cards: PulseCardData[] = [
    { label: "Tracked posts", value: postsCount },
    { label: "Needs attention", value: needsAttentionCount },
    { label: "Alerts received", value: alertsReceivedCount },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {cards.map((card) => (
        <div key={card.label} className="rounded-2xl border border-line bg-white p-5">
          <p className="text-4xl leading-none font-bold tracking-tight text-ink tabular-nums">
            {card.value}
          </p>
          <p className="mt-3 text-sm text-ink-muted">{card.label}</p>
        </div>
      ))}
    </div>
  );
}
