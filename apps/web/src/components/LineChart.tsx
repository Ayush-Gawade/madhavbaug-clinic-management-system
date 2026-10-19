/** Responsive dependency-free line chart with hover tooltip. */

import { useEffect, useId, useRef, useState } from "react";

import { scalePoints } from "@/lib/chart";

export interface LineChartPoint {
  label: string;
  value: number;
}

export function LineChart({
  points,
  height = 180,
  unit,
  ariaLabel = "Trend chart",
}: {
  points: LineChartPoint[];
  height?: number;
  width?: number;
  unit?: string | null;
  ariaLabel?: string;
}): JSX.Element {
  const gradientId = useId();
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(560);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return undefined;
    const measure = (): void => {
      setWidth(Math.max(240, element.clientWidth));
    };
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const values = points.map((point) => point.value);

  if (values.length === 0) {
    return <p className="py-6 text-center text-sm text-ink-muted">No data points in range.</p>;
  }

  const padding = 10;
  const scaled = scalePoints(values, width, height, padding);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const hovered = hoverIndex !== null ? points[hoverIndex] : null;
  const hoveredPoint = hoverIndex !== null ? scaled[hoverIndex] : null;

  const gridlines = [0.05, 0.5, 0.95];
  const pathSegments =
    scaled
      .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
      .join(" ") +
    ` L${scaled[scaled.length - 1].x.toFixed(1)} ${height} L${scaled[0].x.toFixed(1)} ${height} Z`;

  const lineOnly = scaled
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
    .join(" ");

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>): void => {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const index = Math.round(ratio * (points.length - 1));
    setHoverIndex(Math.min(points.length - 1, Math.max(0, index)));
  };

  return (
    <figure className="space-y-2" ref={containerRef}>
      <div className="relative">
        <svg
          role="img"
          aria-label={`${ariaLabel}${unit ? ` (${unit})` : ""}`}
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
          className="w-full touch-none"
          onPointerMove={handlePointerMove}
          onPointerLeave={() => setHoverIndex(null)}
        >
          <defs>
            <linearGradient id={`area-${gradientId}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-brand-500)" stopOpacity="0.22" />
              <stop offset="100%" stopColor="var(--color-brand-500)" stopOpacity="0" />
            </linearGradient>
          </defs>

          {gridlines.map((fraction) => (
            <line
              key={fraction}
              x1="0"
              x2={width}
              y1={padding + (height - padding * 2) * fraction}
              y2={padding + (height - padding * 2) * fraction}
              stroke="var(--color-line)"
              strokeWidth="1"
              strokeDasharray={fraction === 0.5 ? "4 4" : undefined}
            />
          ))}

          {values.length > 1 ? (
            <path d={pathSegments} fill={`url(#area-${gradientId})`} stroke="none" />
          ) : null}
          <path
            d={lineOnly}
            fill="none"
            stroke="var(--color-brand-600)"
            strokeWidth="2.5"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {values.length === 1 ? (
            <circle cx={scaled[0].x} cy={scaled[0].y} r="4" fill="var(--color-brand-600)" />
          ) : null}

          {hoveredPoint ? (
            <g>
              <line
                x1={hoveredPoint.x}
                x2={hoveredPoint.x}
                y1={padding / 2}
                y2={height - padding / 2}
                stroke="var(--color-brand-400)"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <circle
                cx={hoveredPoint.x}
                cy={hoveredPoint.y}
                r="5"
                fill="var(--color-surface)"
                stroke="var(--color-brand-600)"
                strokeWidth="2.5"
              />
            </g>
          ) : null}
        </svg>

        {hovered && hoveredPoint ? (
          <div
            className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-center shadow-pop animate-fade-in-fast"
            style={{ left: `${hoveredPoint.x}px`, top: `${hoveredPoint.y - 8}px` }}
          >
            <p className="whitespace-nowrap text-xs font-bold tabular-nums text-ink">
              {hovered.value}
              {unit ? ` ${unit}` : ""}
            </p>
            <p className="whitespace-nowrap text-[10px] text-ink-muted">{hovered.label}</p>
          </div>
        ) : null}
      </div>

      <figcaption className="flex justify-between text-xs text-ink-muted">
        <span>
          {points[0].label} — {points[points.length - 1].label}
        </span>
        <span className="tabular-nums">
          min {min} · max {max}
          {unit ? ` ${unit}` : ""}
        </span>
      </figcaption>
    </figure>
  );
}
