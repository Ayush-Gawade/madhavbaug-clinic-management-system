import { describe, expect, it } from "vitest";

import { areaPath, linePath, scalePoints } from "@/lib/chart";

describe("scalePoints", () => {
  it("returns an empty array for no values", () => {
    expect(scalePoints([], 100, 50)).toEqual([]);
  });

  it("maps the min value to the bottom and max to the top", () => {
    const points = scalePoints([0, 10], 100, 100, 10);
    expect(points).toHaveLength(2);
    expect(points[0]).toEqual({ x: 10, y: 90 });
    expect(points[1]).toEqual({ x: 90, y: 10 });
  });

  it("centers a single value horizontally", () => {
    const points = scalePoints([5], 100, 100, 10);
    expect(points).toHaveLength(1);
    expect(points[0].x).toBe(50);
  });

  it("uses a flat span when all values are equal", () => {
    const points = scalePoints([7, 7], 100, 100, 0);
    expect(points[0].y).toBe(100);
    expect(points[1].y).toBe(100);
  });
});

describe("linePath", () => {
  it("returns an empty string with no points", () => {
    expect(linePath([])).toBe("");
  });

  it("starts at the first point with a moveto command", () => {
    const path = linePath([
      { x: 0, y: 10 },
      { x: 10, y: 0 },
    ]);
    expect(path).toBe("M0.00 10.00 L10.00 0.00");
  });
});

describe("areaPath", () => {
  it("closes the path to the baseline", () => {
    const path = areaPath(
      [
        { x: 0, y: 10 },
        { x: 10, y: 0 },
      ],
      20,
    );
    expect(path.endsWith("Z")).toBe(true);
    expect(path).toContain("L10.00 20");
  });
});
