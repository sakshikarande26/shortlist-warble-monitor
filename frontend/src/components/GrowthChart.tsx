import { useState, type MouseEvent } from "react";
import type { TrajectoryPoint } from "../lib/types";
import { formatViews } from "../lib/copy";

interface GrowthChartProps {
  trajectory: TrajectoryPoint[];
  isGone: boolean;
  goneSimHours: number | null;
  statusLabel: string;
  breakoutSimHours: number | null;
}

const WIDTH = 640;
const HEIGHT = 280;
const PADDING = { top: 16, right: 16, bottom: 46, left: 60 };
const GRIDLINE = "rgb(0 0 0 / 7%)";
const INK_MUTED = "#6b6b78";
const INK = "#12101a";
const BREAKOUT_COLOR = "#e0812f";

// The line color echoes the same status color as the badge, so the chart
// itself reads as "this is what taking off/worth watching looks like,"
// not just a generic sparkline.
const LINE_COLORS: Record<string, string> = {
  "Taking off": "#e0812f",
  "Worth watching": "#2f9e5c",
  Unavailable: "#8c7fa8",
};
const DEFAULT_LINE_COLOR = "#12101a";

// Hand-rolled SVG rather than a charting library — small enough code that
// a dependency isn't worth it, and it keeps full control over "clean,
// readable axes." The breakout marker is real (backend-computed, the sim
// hour this post's state machine first reached BREAKOUT) — it doesn't
// re-run detection logic client-side. The hover tooltip's growth-since-
// last-check figure is computed purely from the two real trajectory
// points either side of the cursor, nothing fabricated.
export function GrowthChart({ trajectory, isGone, goneSimHours, statusLabel, breakoutSimHours }: GrowthChartProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

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

  const x = (hour: number) => PADDING.left + ((hour - minHour) / (maxHour - minHour || 1)) * chartWidth;
  const y = (view: number) =>
    PADDING.top + chartHeight - ((view - minView) / (maxView - minView || 1)) * chartHeight;

  const linePath = trajectory
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.sim_hours).toFixed(1)},${y(p.views).toFixed(1)}`)
    .join(" ");
  const areaPath = `${linePath} L${x(maxHour).toFixed(1)},${y(minView).toFixed(1)} L${x(minHour).toFixed(1)},${y(minView).toFixed(1)} Z`;

  const last = trajectory[trajectory.length - 1];
  const yTicks = [0, 0.5, 1].map((t) => minView + t * (maxView - minView));
  const vGridlines = [0, 0.25, 0.5, 0.75, 1].map((t) => minHour + t * (maxHour - minHour));

  function handleMove(event: MouseEvent<SVGRectElement>) {
    const svg = event.currentTarget.ownerSVGElement;
    if (!svg) return;
    const bounds = svg.getBoundingClientRect();
    const ratio = (event.clientX - bounds.left) / bounds.width;
    const hoveredHour = minHour + ratio * (maxHour - minHour);
    let nearest = 0;
    let nearestDelta = Infinity;
    trajectory.forEach((p, i) => {
      const delta = Math.abs(p.sim_hours - hoveredHour);
      if (delta < nearestDelta) {
        nearestDelta = delta;
        nearest = i;
      }
    });
    setHoverIndex(nearest);
  }

  const hovered = hoverIndex !== null ? trajectory[hoverIndex] : null;
  const previous = hoverIndex !== null && hoverIndex > 0 ? trajectory[hoverIndex - 1] : null;
  const hoveredGrowthPct =
    hovered && previous && previous.views > 0
      ? ((hovered.views - previous.views) / previous.views) * 100
      : null;

  const showBreakoutMarker =
    breakoutSimHours !== null && breakoutSimHours >= minHour && breakoutSimHours <= maxHour;

  const tooltipWidth = 156;
  const tooltipHeight = hoveredGrowthPct !== null ? 58 : 40;
  let tooltipX = hovered ? x(hovered.sim_hours) + 10 : 0;
  if (tooltipX + tooltipWidth > WIDTH - PADDING.right) {
    tooltipX = (hovered ? x(hovered.sim_hours) : 0) - tooltipWidth - 10;
  }
  const tooltipY = PADDING.top + 6;

  return (
    <svg width="100%" viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Views over time">
      <defs>
        <linearGradient id="growth-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={lineColor} stopOpacity={0.22} />
          <stop offset="100%" stopColor={lineColor} stopOpacity={0} />
        </linearGradient>
      </defs>

      {vGridlines.map((tick) => (
        <line
          key={tick}
          x1={x(tick)}
          x2={x(tick)}
          y1={PADDING.top}
          y2={PADDING.top + chartHeight}
          stroke={GRIDLINE}
          strokeWidth={1}
        />
      ))}

      {yTicks.map((tick) => (
        <text
          key={tick}
          x={PADDING.left - 8}
          y={y(tick)}
          textAnchor="end"
          dominantBaseline="middle"
          fontSize={11}
          fill={INK_MUTED}
        >
          {formatViews(tick)}
        </text>
      ))}

      <text x={x(minHour)} y={HEIGHT - 30} textAnchor="start" fontSize={11} fill={INK_MUTED}>
        {Math.round(minHour)}h
      </text>
      <text x={x(maxHour)} y={HEIGHT - 30} textAnchor="end" fontSize={11} fill={INK_MUTED}>
        {Math.round(maxHour)}h
      </text>
      <text
        x={(x(minHour) + x(maxHour)) / 2}
        y={HEIGHT - 12}
        textAnchor="middle"
        fontSize={11}
        fill={INK_MUTED}
      >
        Hours since first tracked
      </text>

      <path d={areaPath} fill="url(#growth-area)" stroke="none" />
      <path
        d={linePath}
        fill="none"
        stroke={lineColor}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />

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

      {showBreakoutMarker && breakoutSimHours !== null && (
        <g>
          <line
            x1={x(breakoutSimHours)}
            x2={x(breakoutSimHours)}
            y1={PADDING.top}
            y2={PADDING.top + chartHeight}
            stroke={BREAKOUT_COLOR}
            strokeWidth={1.5}
            strokeDasharray="3 3"
          />
          <text
            x={x(breakoutSimHours)}
            y={PADDING.top - 4}
            textAnchor="middle"
            fontSize={10}
            fontWeight={600}
            fill={BREAKOUT_COLOR}
          >
            Breakout
          </text>
        </g>
      )}

      <circle cx={x(last.sim_hours)} cy={y(last.views)} r={4} fill={lineColor} />

      {hovered && (
        <g>
          <line
            x1={x(hovered.sim_hours)}
            x2={x(hovered.sim_hours)}
            y1={PADDING.top}
            y2={PADDING.top + chartHeight}
            stroke={INK_MUTED}
            strokeWidth={1}
            strokeDasharray="2 2"
          />
          <circle cx={x(hovered.sim_hours)} cy={y(hovered.views)} r={4} fill={INK} stroke="#fff" strokeWidth={1.5} />

          <g transform={`translate(${tooltipX}, ${tooltipY})`}>
            <rect width={tooltipWidth} height={tooltipHeight} rx={8} fill="#fff" stroke={GRIDLINE} />
            <text x={10} y={17} fontSize={11} fontWeight={600} fill={INK}>
              {formatViews(hovered.views)} views
            </text>
            <text x={10} y={31} fontSize={10} fill={INK_MUTED}>
              {Math.round(hovered.sim_hours)}h since first tracked
            </text>
            {hoveredGrowthPct !== null && (
              <text
                x={10}
                y={45}
                fontSize={10}
                fill={hoveredGrowthPct >= 0 ? LINE_COLORS["Taking off"] : INK_MUTED}
              >
                {hoveredGrowthPct >= 0 ? "+" : ""}
                {hoveredGrowthPct.toFixed(1)}% since last check
              </text>
            )}
          </g>
        </g>
      )}

      <rect
        x={PADDING.left}
        y={PADDING.top}
        width={chartWidth}
        height={chartHeight}
        fill="transparent"
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIndex(null)}
      />
    </svg>
  );
}
