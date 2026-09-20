import { useCallback, useMemo, useState } from "react";

import type { EditCell, Grid } from "../api/types";
import { EditStack, applyEditsToGrid, cloneGrid, diffToEdits, floodFillCells, inBounds }
  from "../lib/grid";

export type Tool = "brush" | "bucket" | "eyedropper" | "eraser" | "protect";

export interface EditorState {
  grid: Grid;
  tool: Tool;
  color: number | null;
  protectedCells: [number, number][];
  dirty: boolean;
  canUndo: boolean;
  canRedo: boolean;
}

export interface Editor {
  readonly state: EditorState;
  setTool(t: Tool): void;
  setColor(i: number | null): void;
  applyAt(r: number, c: number): void;
  undo(): void;
  redo(): void;
  resetTo(grid: Grid, protectedCells?: [number, number][]): void;
  pendingEdits(): EditCell[];
}

/** 脱开 React 的编辑状态机——交互最密的部分，这样才测得干净。 */
export function createEditor(initial: Grid,
                             initialProtected: [number, number][] = []): Editor {
  let baseline = cloneGrid(initial);
  let stack = new EditStack(initial);
  let tool: Tool = "brush";
  let color: number | null = null;
  let protectedCells: [number, number][] = initialProtected.map((c) => [...c] as [number, number]);

  return {
    get state(): EditorState {
      const grid = stack.current;
      return {
        grid,
        tool,
        color,
        protectedCells,
        dirty: diffToEdits(baseline, grid).length > 0,
        canUndo: stack.canUndo,
        canRedo: stack.canRedo,
      };
    },

    setTool(t) { tool = t; },
    setColor(i) { color = i; },

    applyAt(r, c) {
      const grid = stack.current;
      if (!inBounds(grid, r, c)) return;

      if (tool === "eyedropper") {
        color = grid[r][c];                 // 吸管只取色，不入撤销栈
        return;
      }
      if (tool === "protect") {
        const i = protectedCells.findIndex(([pr, pc]) => pr === r && pc === c);
        protectedCells = i >= 0
          ? protectedCells.filter((_, n) => n !== i)
          : [...protectedCells, [r, c]];
        return;
      }

      let edits: EditCell[];
      if (tool === "eraser") {
        edits = [{ cell: [r, c], to: null }];
      } else if (tool === "bucket") {
        if (color === null) return;
        const fillColor = color;
        edits = floodFillCells(grid, r, c).map((cell) => ({ cell, to: fillColor }));
      } else {
        if (color === null) return;
        edits = [{ cell: [r, c], to: color }];
      }
      stack.push(applyEditsToGrid(grid, edits));
    },

    undo() { stack.undo(); },
    redo() { stack.redo(); },

    resetTo(grid, nextProtected) {
      baseline = cloneGrid(grid);
      stack = new EditStack(grid);
      if (nextProtected) protectedCells = nextProtected.map((c) => [...c] as [number, number]);
    },

    /** 相对基线的显式改动列表——提交给后端的就是这个，不是"执行过什么工具"。 */
    pendingEdits() {
      return diffToEdits(baseline, stack.current);
    },
  };
}

/** React 包装：状态机变了就 bump 一个计数器触发重渲染。 */
export function useEditor(initial: Grid, initialProtected: [number, number][] = []) {
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const editor = useMemo(() => createEditor(initial, initialProtected), []);
  const [tick, bump] = useState(0);
  const rerender = useCallback(() => bump((n) => n + 1), []);

  return useMemo(() => ({
    state: editor.state,
    setTool: (t: Tool) => { editor.setTool(t); rerender(); },
    setColor: (i: number | null) => { editor.setColor(i); rerender(); },
    applyAt: (r: number, c: number) => { editor.applyAt(r, c); rerender(); },
    undo: () => { editor.undo(); rerender(); },
    redo: () => { editor.redo(); rerender(); },
    resetTo: (g: Grid, p?: [number, number][]) => { editor.resetTo(g, p); rerender(); },
    pendingEdits: () => editor.pendingEdits(),
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [editor, rerender, tick]);
}
