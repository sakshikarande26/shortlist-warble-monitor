import { useState, type MouseEvent } from "react";
import { MONITORING_WINDOW_DAYS } from "../lib/copy";

interface BreakoutTrendChartProps {
  // Pre-bucketed by the caller (Home.tsx), via lib/copy's dayBucket, so the
  // chart and the plain-English summary sentence next to it are always
  // counting from the exact same numbers rather than two separate passes.
  counts: number[]; // length MONITORING_WINDOW_DAYS, index 0 = Day 1
  currentDay: number; // days beyond this haven't happened in the sim yet
}

const WIDTH = 640;
const HEIGHT = 280;
const PADDING = { top: 16, right: 16, bottom: 40, left: 40 };
const GRIDLINE = "rgb(0 0 0 / 7%)";
const INK_MUTED = "#71717a";
const INK = "#18181b";
// Same coral GrowthChart marks a breakout with — the single busiest day
// gets flagged the same color as an individual post's breakout marker, so
// "coral = worth a second look" reads consistently across the app.
const PEAK_COLOR = "#fc896d";
// Violet scale (index.css's cool family) for every other bar, light-to-
// deep by count — real counts, colored for scannability, not decoration.
const BAR_SCALE = ["#e9daf4", "#dcc8f6", "#c9c6ff", "#9b96f8", "#7670f2"];

// Bar chart of breakouts per sim-day (Day 1..7), sourced from the real
// breakout log — no charting dependency, same hand-rolled SVG conventions
// (axes, gridlines, hover tooltip) as GrowthChart.tsx. Days the simulation
// hasn't reached yet render as hollow outlines: an honest "no data yet,"
// never a fabricated zero.
export function BreakoutTrendChart({ counts, currentDay }: BreakoutTrendChartProps) {
  const [hoverDay, setHoverDay] = useState<number | null>(null);

  const maxCount = Math.max(...counts, 1);
  const peakValue = Math.max(...counts);

  const chartWidth = WIDTH - PADDING.left - PADDING.right;
  const chartHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const bandWidth = chartWidth / MONITORING_WINDOW_DAYS;
  const barWidth = bandWidth * 0.56;

  const yTicks = [0, 0.5, 1].map((t) => Math.round(t * maxCount));
  const y = (count: number) => PADDING.top + chartHeight - (count / maxCount) * chartHeight;

  function barColor(count: number, reached: boolean): string {
    if (!reached) return "transparent";
    if (count === peakValue && count > 0) return PEAK_COLOR;
    if (count === 0) return BAR_SCALE[0];
    const step = Math.min(Math.round((count / maxCount) * (BAR_SCALE.length - 1)), BAR_SCALE.length - 1);
    return BAR_SCALE[step];
  }

  const hovered = hoverDay !== null ? { day: hoverDay, count: counts[hoverDay - 1] } : null;
  const tooltipWidth = 128;
  const tooltipHeight = 40;
  const hoveredX = hovered ? PADDING.left + (hovered.day - 0.5) * bandWidth : 0;
  let tooltipX = hoveredX - tooltipWidth / 2;
  tooltipX = Math.max(PADDING.left, Math.min(tooltipX, WIDTH - PADDING.right - tooltipWidth));

  function handleMove(event: MouseEvent<SVGRectElement>) {
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return;
    const bounds = svg.getBoundingClientRect();
    const ratio = (event.clientX - bounds.left) / bounds.width;
    const day = Math.min(Math.max(Math.ceil((ratio * WIDTH - PADDING.left) / bandWidth), 1), MONITORING_WINDOW_DAYS);
    setHoverDay(day);
  }

  if (currentDay <= 0) {
    return (
      <div className="flex h-[260px] items-center justify-center rounded-xl border border-line text-sm text-ink-muted">
        Not enough history yet to chart.
      </div>
    );
  }

  return (
    <svg width="100%" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Breakouts per day">
      {yTicks.map((tick) => (
        <line
          key={tick}
          x1={PADDING.left}
          x2={WIDTH - PADDING.right}
          y1={y(tick)}
          y2={y(tick)}
          stroke={GRIDLINE}
          strokeWidth={1}
        />
      ))}
      {yTicks.map((tick) => (
        <text key={tick} x={PADDING.left - 8} y={y(tick)} textAnchor="end" dominantBaseline="middle" fontSize={11} fill={INK_MUTED}>
          {tick}
        </text>
      ))}

      {counts.map((count, i) => {
        const day = i + 1;
        const reached = day <= currentDay;
        const barHeight = reached ? chartHeight - (y(count) - PADDING.top) : 0;
        const bandX = PADDING.left + i * bandWidth;
        const barX = bandX + (bandWidth - barWidth) / 2;
        return (
          <g key={day}>
            {reached ? (
              <rect
                x={barX}
                y={y(count)}
                width={barWidth}
                height={Math.max(barHeight, count > 0 ? 2 : 0)}
                rx={4}
                fill={barColor(count, reached)}
                opacity={hoverDay !== null && hoverDay !== day ? 0.55 : 1}
              />
            ) : (
              <rect
                x={barX}
                y={PADDING.top + chartHeight - 4}
                width={barWidth}
                height={4}
                rx={2}
                fill="none"
                stroke={INK_MUTED}
                strokeDasharray="2 2"
                opacity={0.4}
              />
            )}
            <text x={bandX + bandWidth / 2} y={HEIGHT - 14} textAnchor="middle" fontSize={10} fill={INK_MUTED}>
              {day}
            </text>
          </g>
        );
      })}
      <text x={PADDING.left + chartWidth / 2} y={HEIGHT - 2} textAnchor="middle" fontSize={11} fill={INK_MUTED}>
        Day of the 7-day window
      </text>

      {hovered && (
        <g transform={`translate(${tooltipX}, ${PADDING.top + 6})`}>
          <rect width={tooltipWidth} height={tooltipHeight} rx={8} fill="#fff" stroke={GRIDLINE} />
          <text x={10} y={17} fontSize={11} fontWeight={600} fill={INK}>
            Day {hovered.day}
          </text>
          <text x={10} y={31} fontSize={10} fill={INK_MUTED}>
            {hovered.count} breakout{hovered.count === 1 ? "" : "s"}
          </text>
        </g>
      )}

      <rect
        x={PADDING.left}
        y={PADDING.top}
        width={chartWidth}
        height={chartHeight}
        fill="transparent"
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverDay(null)}
      />
    </svg>
  );
}
