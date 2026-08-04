import { useId } from "react";

interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
}

// Small inline SVG trend line — hand-rolled rather than a charting
// dependency. A soft gradient fill under the line (echoing GrowthChart's
// area treatment) and a dot on the latest point turn a bare squiggle into
// something that actually reads as "this is the shape of what happened,
// and here's where it stands now" at a glance.
export function Sparkline({ values, width = 88, height = 28, color = "currentColor" }: SparklineProps) {
  const gradientId = useId();

  if (values.length < 2) {
    return <div style={{ width, height }} className="flex items-center text-xs text-ink-muted">-</div>;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = width / (values.length - 1);

  const points = values.map((value, index) => {
    const x = index * step;
    const y = height - ((value - min) / range) * height;
    return { x, y };
  });

  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L${points[points.length - 1].x.toFixed(1)},${height} L0,${height} Z`;
  const last = points[points.length - 1];

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.25} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />
      <polyline
        points={points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ")}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={last.x} cy={last.y} r={2.25} fill={color} />
    </svg>
  );
}
