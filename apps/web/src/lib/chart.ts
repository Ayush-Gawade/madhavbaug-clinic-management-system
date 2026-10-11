/** Pure geometry helpers for dependency-free SVG charts. */

export interface ChartPoint {
  x: number;
  y: number;
}

/** Map a series of values onto SVG coordinates within the given box. */
export function scalePoints(
  values: number[],
  width: number,
  height: number,
  padding = 8,
): ChartPoint[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const innerWidth = Math.max(width - padding * 2, 0);
  const innerHeight = Math.max(height - padding * 2, 0);
  return values.map((value, index) => {
    const x =
      values.length === 1
        ? padding + innerWidth / 2
        : padding + (index / (values.length - 1)) * innerWidth;
    const y = padding + innerHeight - ((value - min) / span) * innerHeight;
    return { x, y };
  });
}

/** Build an SVG path string connecting the points in order. */
export function linePath(points: ChartPoint[]): string {
  if (points.length === 0) return "";
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
    .join(" ");
}

/** Build a closed area path (line plus baseline) for a filled chart. */
export function areaPath(points: ChartPoint[], height: number): string {
  if (points.length === 0) return "";
  const first = points[0];
  const last = points[points.length - 1];
  return `${linePath(points)} L${last.x.toFixed(2)} ${height} L${first.x.toFixed(2)} ${height} Z`;
}
