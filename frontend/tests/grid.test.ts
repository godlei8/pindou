import { describe, expect, test } from "vitest";

import type { Grid } from "../src/api/types";
import {
  EditStack, applyEditsToGrid, cloneGrid, colorCounts, diffToEdits, floodFillCells,
  gridSize, inBounds, mergeEdits,
} from "../src/lib/grid";

const G: Grid = [
  [1, 1, 2],
  [1, null, 2],
  [3, 3, 2],
];

describe("基础", () => {
  test("cloneGrid 是深拷贝", () => {
    const c = cloneGrid(G);
    c[0][0] = 9;
    expect(G[0][0]).toBe(1);
  });

  test("gridSize / inBounds", () => {
    expect(gridSize(G)).toEqual({ rows: 3, cols: 3 });
    expect(inBounds(G, 0, 0)).toBe(true);
    expect(inBounds(G, 3, 0)).toBe(false);
    expect(inBounds(G, -1, 0)).toBe(false);
    expect(gridSize([])).toEqual({ rows: 0, cols: 0 });
  });

  test("colorCounts 忽略空格", () => {
    expect(colorCounts(G)).toEqual(new Map([[1, 3], [2, 3], [3, 2]]));
  });
});

describe("floodFillCells", () => {
  test("4-连通同色区域", () => {
    const got = floodFillCells(G, 0, 0).map((c) => c.join(",")).sort();
    expect(got).toEqual(["0,0", "0,1", "1,0"]);
  });

  test("对角不算连通", () => {
    const diag: Grid = [[5, 0], [0, 5]];
    expect(floodFillCells(diag, 0, 0)).toEqual([[0, 0]]);
  });

  test("空格区域也能填（null 视为一种值）", () => {
    const g: Grid = [[null, null], [1, null]];
    expect(floodFillCells(g, 0, 0).length).toBe(3);
  });

  test("越界返回空", () => {
    expect(floodFillCells(G, 99, 99)).toEqual([]);
  });

  test("整张同色不会栈溢出", () => {
    const big: Grid = Array.from({ length: 120 }, () => Array.from({ length: 120 }, () => 0));
    expect(floodFillCells(big, 60, 60).length).toBe(14400);
  });
});

describe("改动集", () => {
  test("applyEditsToGrid 返回新网格且不改原对象", () => {
    const out = applyEditsToGrid(G, [{ cell: [0, 0], to: 7 }, { cell: [1, 1], to: 8 }]);
    expect(out[0][0]).toBe(7);
    expect(out[1][1]).toBe(8);
    expect(G[0][0]).toBe(1);
    expect(G[1][1]).toBeNull();
  });

  test("to: null 表示擦成空格", () => {
    expect(applyEditsToGrid(G, [{ cell: [0, 0], to: null }])[0][0]).toBeNull();
  });

  test("越界的改动被忽略而不是抛错", () => {
    expect(() => applyEditsToGrid(G, [{ cell: [99, 99], to: 1 }])).not.toThrow();
  });

  test("diffToEdits 只列出真正变了的格子", () => {
    const after = applyEditsToGrid(G, [{ cell: [2, 2], to: 4 }]);
    expect(diffToEdits(G, after)).toEqual([{ cell: [2, 2], to: 4 }]);
    expect(diffToEdits(G, cloneGrid(G))).toEqual([]);
  });

  test("diffToEdits 能表达擦除", () => {
    const after = applyEditsToGrid(G, [{ cell: [0, 0], to: null }]);
    expect(diffToEdits(G, after)).toEqual([{ cell: [0, 0], to: null }]);
  });

  test("mergeEdits 同格只保留最后一次，顺序按首次出现", () => {
    const merged = mergeEdits([
      { cell: [0, 0], to: 1 },
      { cell: [1, 1], to: 2 },
      { cell: [0, 0], to: 3 },
    ]);
    expect(merged).toEqual([{ cell: [0, 0], to: 3 }, { cell: [1, 1], to: 2 }]);
  });
});

describe("EditStack", () => {
  test("撤销重做", () => {
    const s = new EditStack(G);
    expect(s.canUndo).toBe(false);
    const a = applyEditsToGrid(G, [{ cell: [0, 0], to: 7 }]);
    s.push(a);
    const b = applyEditsToGrid(a, [{ cell: [0, 1], to: 8 }]);
    s.push(b);

    expect(s.current[0][1]).toBe(8);
    expect(s.undo()?.[0][1]).toBe(1);
    expect(s.undo()?.[0][0]).toBe(1);
    expect(s.canUndo).toBe(false);
    expect(s.undo()).toBeNull();

    expect(s.redo()?.[0][0]).toBe(7);
    expect(s.redo()?.[0][1]).toBe(8);
    expect(s.canRedo).toBe(false);
  });

  test("撤销后再 push 会丢掉重做分支", () => {
    const s = new EditStack(G);
    s.push(applyEditsToGrid(G, [{ cell: [0, 0], to: 7 }]));
    s.undo();
    s.push(applyEditsToGrid(G, [{ cell: [0, 0], to: 9 }]));
    expect(s.canRedo).toBe(false);
    expect(s.current[0][0]).toBe(9);
  });

  test("reset 清空历史", () => {
    const s = new EditStack(G);
    s.push(applyEditsToGrid(G, [{ cell: [0, 0], to: 7 }]));
    s.reset(G);
    expect(s.canUndo).toBe(false);
    expect(s.canRedo).toBe(false);
    expect(s.current[0][0]).toBe(1);
  });
});
