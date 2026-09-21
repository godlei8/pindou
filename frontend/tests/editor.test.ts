import { describe, expect, test } from "vitest";

import type { Grid } from "../src/api/types";
import { createEditor } from "../src/hooks/useEditor";

const G: Grid = [
  [0, 0, 1],
  [0, 2, 1],
  [3, 3, 1],
];

describe("工具", () => {
  test("画笔改一格", () => {
    const ed = createEditor(G);
    ed.setColor(7);
    ed.applyAt(0, 0);
    expect(ed.state.grid[0][0]).toBe(7);
    expect(ed.state.dirty).toBe(true);
  });

  test("画笔未选色时不动网格", () => {
    const ed = createEditor(G);
    ed.applyAt(0, 0);
    expect(ed.state.grid[0][0]).toBe(0);
    expect(ed.state.dirty).toBe(false);
  });

  test("油漆桶整片换色", () => {
    const ed = createEditor(G);
    ed.setTool("bucket");
    ed.setColor(9);
    ed.applyAt(0, 0);
    expect(ed.state.grid[0][0]).toBe(9);
    expect(ed.state.grid[0][1]).toBe(9);
    expect(ed.state.grid[1][0]).toBe(9);
    expect(ed.state.grid[1][1]).toBe(2);       // 不同色，不受影响
  });

  test("橡皮擦成空格", () => {
    const ed = createEditor(G);
    ed.setTool("eraser");
    ed.applyAt(2, 2);
    expect(ed.state.grid[2][2]).toBeNull();
  });

  test("吸管取色但不改网格", () => {
    const ed = createEditor(G);
    ed.setTool("eyedropper");
    ed.applyAt(1, 1);
    expect(ed.state.color).toBe(2);
    expect(ed.state.grid).toEqual(G);
    expect(ed.state.dirty).toBe(false);
  });

  test("吸管吸空格得到 null", () => {
    const ed = createEditor([[null]]);
    ed.setTool("eyedropper");
    ed.applyAt(0, 0);
    expect(ed.state.color).toBeNull();
  });

  test("保护标记可切换且不改网格", () => {
    const ed = createEditor(G);
    ed.setTool("protect");
    ed.applyAt(1, 1);
    expect(ed.state.protectedCells).toEqual([[1, 1]]);
    expect(ed.state.grid).toEqual(G);
    ed.applyAt(1, 1);
    expect(ed.state.protectedCells).toEqual([]);
  });

  test("越界点击被忽略", () => {
    const ed = createEditor(G);
    ed.setColor(7);
    expect(() => ed.applyAt(99, 99)).not.toThrow();
    expect(ed.state.dirty).toBe(false);
  });
});

describe("改动集", () => {
  test("pendingEdits 只含真正变了的格子", () => {
    const ed = createEditor(G);
    ed.setColor(7);
    ed.applyAt(0, 0);
    ed.applyAt(2, 2);
    expect(ed.pendingEdits()).toEqual([
      { cell: [0, 0], to: 7 },
      { cell: [2, 2], to: 7 },
    ]);
  });

  test("改回原值后不算改动", () => {
    const ed = createEditor(G);
    ed.setColor(7);
    ed.applyAt(0, 0);
    ed.setColor(0);
    ed.applyAt(0, 0);
    expect(ed.pendingEdits()).toEqual([]);
    expect(ed.state.dirty).toBe(false);
  });

  test("油漆桶提交的是格子列表而非操作意图", () => {
    const ed = createEditor(G);
    ed.setTool("bucket");
    ed.setColor(9);
    ed.applyAt(0, 0);
    const edits = ed.pendingEdits();
    expect(edits.length).toBe(3);
    expect(edits.every((e) => e.to === 9)).toBe(true);
    expect(JSON.stringify(edits)).not.toContain("bucket");
  });
});

describe("撤销重做", () => {
  test("撤销回到上一步，dirty 随之更新", () => {
    const ed = createEditor(G);
    ed.setColor(7);
    ed.applyAt(0, 0);
    expect(ed.state.canUndo).toBe(true);
    ed.undo();
    expect(ed.state.grid[0][0]).toBe(0);
    expect(ed.state.dirty).toBe(false);
    ed.redo();
    expect(ed.state.grid[0][0]).toBe(7);
    expect(ed.state.dirty).toBe(true);
  });

  test("每一笔各自入栈", () => {
    const ed = createEditor(G);
    ed.setColor(7);
    ed.applyAt(0, 0);
    ed.applyAt(0, 1);
    ed.undo();
    expect(ed.state.grid[0][1]).toBe(0);
    expect(ed.state.grid[0][0]).toBe(7);
  });

  test("吸管不入撤销栈", () => {
    const ed = createEditor(G);
    ed.setTool("eyedropper");
    ed.applyAt(1, 1);
    expect(ed.state.canUndo).toBe(false);
  });
});

describe("resetTo", () => {
  test("后端返回新版本后重置基线", () => {
    const ed = createEditor(G);
    ed.setColor(7);
    ed.applyAt(0, 0);
    const fresh: Grid = [[5, 5, 5], [5, 5, 5], [5, 5, 5]];
    ed.resetTo(fresh);
    expect(ed.state.grid).toEqual(fresh);
    expect(ed.state.dirty).toBe(false);
    expect(ed.state.canUndo).toBe(false);
    expect(ed.pendingEdits()).toEqual([]);
  });

  test("resetTo 能带入保护格", () => {
    const ed = createEditor(G);
    ed.resetTo(G, [[0, 0]]);
    expect(ed.state.protectedCells).toEqual([[0, 0]]);
  });
});

describe("拖动工具", () => {
  test("拖动只看不改：不画、不入撤销栈", () => {
    const ed = createEditor(G);
    ed.setColor(7);
    ed.setTool("pan");
    ed.applyAt(0, 0);
    expect(ed.state.grid[0][0]).toBe(0);
    expect(ed.state.dirty).toBe(false);
    expect(ed.state.canUndo).toBe(false);
  });
});
