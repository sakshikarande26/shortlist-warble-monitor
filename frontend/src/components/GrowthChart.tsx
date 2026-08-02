import type { TrajectoryPoint } from "../lib/types";
import { formatViews } from "../lib/copy";

interface GrowthChartProps {
  trajectory: TrajectoryPoint[];
  isGone: boolean;
  goneSimHours: number | null;
  statusLabel: string;
}

const WIDTH = 640;
const HEIGHT = 260;
const PADDING = { top: 16, right: 16, bottom: 28, left: 56 };
const GRIDLINE = "rgb(0 0 0 / 7%)";
const INK_MUTED = "#6b6b6b";

// The line color echoes the same status color as the badge, so the chart
// itself reads as "this is what taking off/worth watching looks like,"
// not just a generic sparkline.
const LINE_COLORS: Record<string, string> = {
  "Taking off": "#b5473b",
  "Worth watching": "#a97a2e",
  Unavailable: "#8c8299",
};
const DEFAULT_LINE_COLOR = "#000000";

// Hand-rolled SVG rather than a charting library — small enough code that a
// dependency isn't worth it, and it keeps full control over "clean,
// readable axes" instead of a generic library look. Annotations are
// limited to what's actually known (latest point, unavailable marker) —
// this deliberately does NOT try to mark historical "became RISING/
// BREAKOUT" points, since that would mean re-running the state machine
// client-side and duplicating deterministic logic that belongs on the
// backend only.
export function GrowthChart({ trajectory, isGone, goneSimHours, statusLabel }: GrowthChartProps) {
  if (trajectory.length < 2) {
    return (
      <div className="flex h-[260px] items-center justify-center rounded-xl border border-line text-sm text-ink-muted">
        Not enough history yet to chart.
      </div>
    );
  }

  const lineColor = LINE_COLORS[statusLabel] ?? DEFAULT_LINE_COLOR;
  const hours = trajectory.map((p) => p.sim_hours);
  const views = trajectory.map((p) => p.views);
  const minHour = Math.min(...hours);
  const maxHour = Math.max(...hours);
  const minView = 0;
  const maxView = Math.max(...views) * 1.08 || 1;

  const chartWidth = WIDTH - PADDING.left - PADDING.right;
  const chartHeight = HEIGHT - PADDING.top - PADDING.bottom;

  const x = (hour: number) =>
    PADDING.left + ((hour - minHour) / (maxHour - minHour || 1)) * chartWidth;
  const y = (view: number) =>
    PADDING.top + chartHeight - ((view - minView) / (maxView - minView || 1)) * chartHeight;

  const linePath = trajectory
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.sim_hours).toFixed(1)},${y(p.views).toFixed(1)}`)
    .join(" ");
  const areaPath = `${linePath} L${x(maxHour).toFixed(1)},${y(minView).toFixed(1)} L${x(minHour).toFixed(1)},${y(minView).toFixed(1)} Z`;

  const last = trajectory[trajectory.length - 1];
  const yTicks = [0, 0.5, 1].map((t) => minView + t * (maxView - minView));
  const vGridlines = [0, 0.25, 0.5, 0.75, 1].map((t) => minHour + t * (maxHour - minHour));

  return (
    <svg width="100%" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Views over time">
      <defs>
        <linearGradient id="growth-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={lineColor} stopOpacity={0.1} />
          <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
        </linearGradient>
      </defs>

      {vGridlines.map((tick) => (
        <line key={tick} x1={x(tick)} x2={x(tick)} y1={PADDING.top} y2={PADDING.top + chartHeight} stroke={GRIDLINE} strokeWidth={1} />
      ))}

      {yTicks.map((tick) => (
        <text key={tick} x={PADDING.left - 8} y={y(tick)} textAnchor="end" dominantBaseline="middle" fontSize={11} fill={INK_MUTED}>
          {formatViews(tick)}
        </text>
      ))}

      <text x={x(minHour)} y={HEIGHT - 6} textAnchor="start" fontSize={11} fill={INK_MUTED}>
        {Math.round(minHour)}h
      </text>
      <text x={x(maxHour)} y={HEIGHT - 6} textAnchor="end" fontSize={11} fill={INK_MUTED}>
        {Math.round(maxHour)}h
      </text>

      <path d={areaPath} fill="url(#growth-area)" stroke="none" />
      <path d={linePath} fill="none" stroke={lineColor} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

      {isGone && goneSimHours !== null && goneSimHours >= minHour && goneSimHours <= maxHour && (
        <line
          x1={x(goneSimHours)}
          x2={x(goneSimHours)}
          y1={PADDING.top}
          y2={PADDING.top + chartHeight}
          stroke={INK_MUTED}
          strokeWidth={1.5}
          strokeDasharray="4 3"
        />
      )}

      <circle cx={x(last.sim_hours)} cy={y(last.views)} r={4} fill={lineColor} />
    </svg>
  );
}
