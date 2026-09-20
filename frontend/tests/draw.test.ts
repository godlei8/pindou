import { describe, expect, test } from "vitest";

import type { Grid } from "../src/api/types";
import { DEFAULT_DRAW, canvasSize, cellAt, drawPattern, fitCellPx } from "../src/lib/draw";

const G: Grid = [
  [0, 1, null],
  [1, 1, 0],
];
const COLORS = new Map([[0, "#FF0000"], [1, "#00FF00"]]);
const O = { ...DEFAULT_DRAW, cellPx: 10 };

/** 记录调用的假 2d 上下文——jsdom 没有真的。 */
function fakeCtx() {
  const calls: { fn: string; args: unknown[] }[] = [];
  const rec = (fn: string) => (...args: unknown[]) => { calls.push({ fn, args }); };
  return {
    calls,
    fillStyle: "", strokeStyle: "", lineWidth: 0, font: "", textAlign: "", textBaseline: "",
    fillRect: rec("fillRect"),
    strokeRect: rec("strokeRect"),
    beginPath: rec("beginPath"),
    moveTo: rec("moveTo"),
    lineTo: rec("lineTo"),
    stroke: rec("stroke"),
    fillText: rec("fillText"),
    clearRect: rec("clearRect"),
    save: rec("save"),
    restore: rec("restore"),
  };
}

describe("几何", () => {
  test("canvasSize 是格数×格宽 +1（给最后一条线留像素）", () => {
    expect(canvasSize(G, O)).toEqual({ width: 31, height: 21 });
  });

  test("cellAt 把画布坐标映射到格子", () => {
    expect(cellAt(0, 0, G, O)).toEqual([0, 0]);
    expect(cellAt(9, 9, G, O)).toEqual([0, 0]);
    expect(cellAt(10, 0, G, O)).toEqual([0, 1]);
    expect(cellAt(25, 15, G, O)).toEqual([1, 2]);
  });

  test("cellAt 越界返回 null", () => {
    expect(cellAt(-1, 0, G, O)).toBeNull();
    expect(cellAt(0, -1, G, O)).toBeNull();
    expect(cellAt(999, 0, G, O)).toBeNull();
    expect(cellAt(0, 999, G, O)).toBeNull();
  });

  test("fitCellPx 让图纸塞进给定区域", () => {
    expect(fitCellPx(G, 301, 300)).toBe(100);      // 3 列 × 100 = 300，+1 给线
    expect(fitCellPx(G, 31, 300)).toBe(10);
    expect(fitCellPx(G, 1, 1)).toBe(2);            // 下限 2，别退化成看不见
    expect(fitCellPx([], 300, 300)).toBe(2);
  });
});

describe("drawPattern", () => {
  test("每个格子都画了底", () => {
    const ctx = fakeCtx();
    drawPattern(ctx, G, COLORS, O);
    const fills = ctx.calls.filter((c) => c.fn === "fillRect");
    expect(fills.length).toBe(6);
    expect(fills[0].args).toEqual([0, 0, 10, 10]);
  });

  test("空格不使用色卡颜色", () => {
    const base = fakeCtx();
    const seen: string[] = [];
    const proxy = new Proxy(base, {
      set(t, k, v) {
        if (k === "fillStyle") seen.push(String(v));
        return Reflect.set(t, k, v);
      },
    });
    drawPattern(proxy, [[null]], COLORS, O);
    expect(seen).not.toContain("#FF0000");
    expect(seen).not.toContain("#00FF00");
  });

  test("网格线落在整数像素上", () => {
    const ctx = fakeCtx();
    drawPattern(ctx, G, COLORS, O);
    const coords = ctx.calls
      .filter((c) => c.fn === "moveTo" || c.fn === "lineTo")
      .flatMap((c) => c.args as number[]);
    expect(coords.length).toBeGreaterThan(0);
    for (const v of coords) expect(Number.isInteger(v)).toBe(true);
  });

  test("每 majorEvery 条线更粗", () => {
    const base = fakeCtx();
    const widths: number[] = [];
    const proxy = new Proxy(base, {
      set(t, k, v) {
        if (k === "lineWidth") widths.push(Number(v));
        return Reflect.set(t, k, v);
      },
    });
    const wide: Grid = Array.from({ length: 2 }, () => Array.from({ length: 21 }, () => 0));
    drawPattern(proxy, wide, COLORS, { ...O, majorEvery: 10 });
    expect(widths).toContain(2);
    expect(widths).toContain(1);
  });

  test("highlight 画红框", () => {
    const ctx = fakeCtx();
    drawPattern(ctx, G, COLORS, { ...O, highlight: [[1, 1]] });
    expect(ctx.calls.some((c) => c.fn === "strokeRect")).toBe(true);
  });

  test("showCodes=false 时不画文字", () => {
    const ctx = fakeCtx();
    drawPattern(ctx, G, COLORS, { ...O, showCodes: false });
    expect(ctx.calls.some((c) => c.fn === "fillText")).toBe(false);
  });

  test("色卡里没有的索引不会让绘制崩掉", () => {
    const ctx = fakeCtx();
    expect(() => drawPattern(ctx, [[42]], COLORS, O)).not.toThrow();
  });

  test("空网格不崩", () => {
    const ctx = fakeCtx();
    expect(() => drawPattern(ctx, [], COLORS, O)).not.toThrow();
  });
});
