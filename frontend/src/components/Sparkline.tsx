interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
}

// Small inline SVG trend line — hand-rolled rather than a charting
// dependency, deliberately restrained (one thin line, no axes, no grid).
export function Sparkline({ values, width = 88, height = 28, color = "currentColor" }: SparklineProps) {
  if (values.length < 2) {
    return <div style={{ width, height }} className="flex items-center text-xs text-ink-muted">-</div>;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = width / (values.length - 1);

  const points = values
    .map((value, index) => {
      const x = index * step;
      const y = height - ((value - min) / range) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
