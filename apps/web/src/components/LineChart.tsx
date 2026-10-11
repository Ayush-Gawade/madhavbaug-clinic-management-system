import { areaPath, linePath, scalePoints } from "@/lib/chart";

export interface LineChartPoint {
  label: string;
  value: number;
}

export function LineChart({
  points,
  height = 160,
  width = 640,
  unit,
  ariaLabel = "Trend chart",
}: {
  points: LineChartPoint[];
  height?: number;
  width?: number;
  unit?: string | null;
  ariaLabel?: string;
}): JSX.Element {
  const values = points.map((point) => point.value);

  if (values.length === 0) {
    return <p className="py-6 text-center text-sm text-slate-400">No data points in range.</p>;
  }

  const scaled = scalePoints(values, width, height);
  const min = Math.min(...values);
  const max = Math.max(...values);

  return (
    <figure className="space-y-2">
      <svg
        role="img"
        aria-label={`${ariaLabel}${unit ? ` (${unit})` : ""}`}
        viewBox={`0 0 ${width} ${height}`}
        className="h-40 w-full"
        preserveAspectRatio="none"
      >
        <line x1="0" y1={height} x2={width} y2={height} stroke="#e2e8f0" strokeWidth="1" />
        {values.length > 1 ? (
          <path d={areaPath(scaled, height)} fill="#dbeafe" opacity="0.6" stroke="none" />
        ) : null}
        <path
          d={linePath(scaled)}
          fill="none"
          stroke="#1d4ed8"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {scaled.map((point, index) => (
          <circle key={index} cx={point.x} cy={point.y} r="3" fill="#1d4ed8" />
        ))}
      </svg>
      <figcaption className="flex justify-between text-xs text-slate-500">
        <span>
          {points[0].label} — {points[points.length - 1].label}
        </span>
        <span>
          min {min} · max {max}
          {unit ? ` ${unit}` : ""}
        </span>
      </figcaption>
    </figure>
  );
}
