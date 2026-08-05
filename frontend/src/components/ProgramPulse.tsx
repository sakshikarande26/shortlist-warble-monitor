import { useState } from "react";

interface ProgramPulseProps {
  program: {
    postsCount: number;
    needsAttentionCount: number;
    breakoutsCount: number;
  };
  weekly: {
    flaggedCount: number;
    newCount: number;
    removedCount: number;
  };
}

type View = "program" | "weekly";

interface PulseCardData {
  label: string;
  value: number;
}

// Two real, genuinely different slices — not the same numbers re-labeled.
// The whole simulation is one 7-day window (CLAUDE.md), so "breakouts
// this week" and "breakouts total" would always be identical; each number
// lives in exactly one tab, never duplicated under a different label.
// "Program" is where things stand right now (a snapshot); "Weekly" is
// what actually happened across the window (an activity count).
function cardsFor(view: View, program: ProgramPulseProps["program"], weekly: ProgramPulseProps["weekly"]): PulseCardData[] {
  if (view === "program") {
    return [
      { label: "Tracked posts", value: program.postsCount },
      {
        label: program.needsAttentionCount === 1 ? "Post needs attention" : "Posts need attention",
        value: program.needsAttentionCount,
      },
      { label: "Breakouts", value: program.breakoutsCount },
    ];
  }
  return [
    { label: "Flagged this week", value: weekly.flaggedCount },
    { label: "New posts this week", value: weekly.newCount },
    { label: "Removed this week", value: weekly.removedCount },
  ];
}

// Reassurance that coverage is healthy, not a KPI dashboard — three cards,
// a quiet inner glow (the agent interface's violet/coral pair, toned way
// down), everything else plain black/white/grey.
export function ProgramPulse({ program, weekly }: ProgramPulseProps) {
  const [view, setView] = useState<View>("program");
  const cards = cardsFor(view, program, weekly);

  return (
    <div>
      <div className="mb-3 inline-flex rounded-full border border-line bg-white p-0.5">
        {(
          [
            { id: "program", label: "Program" },
            { id: "weekly", label: "Weekly" },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setView(tab.id)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              view === tab.id ? "bg-ink text-white" : "text-ink-muted hover:text-ink"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {cards.map((card) => (
          <div key={card.label} className="pulse-card-glow rounded-2xl border border-line p-5">
            <p className="text-4xl leading-none font-bold tracking-tight text-ink tabular-nums">
              {card.value}
            </p>
            <p className="mt-3 text-sm text-ink-muted">{card.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
