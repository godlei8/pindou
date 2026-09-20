import type { Cell, EditCell, Grid } from "../api/types";

export function cloneGrid(g: Grid): Grid {
  return g.map((row) => row.slice());
}

export function gridSize(g: Grid): { rows: number; cols: number } {
  return { rows: g.length, cols: g[0]?.length ?? 0 };
}

export function inBounds(g: Grid, r: number, c: number): boolean {
  const { rows, cols } = gridSize(g);
  return r >= 0 && r < rows && c >= 0 && c < cols;
}

/** 4-连通同值区域。用显式栈，120×120 全同色也不会爆调用栈。 */
export function floodFillCells(g: Grid, r: number, c: number): [number, number][] {
  if (!inBounds(g, r, c)) return [];
  const { rows, cols } = gridSize(g);
  const target: Cell = g[r][c];
  const seen = new Uint8Array(rows * cols);
  const out: [number, number][] = [];
  const stack: [number, number][] = [[r, c]];
  seen[r * cols + c] = 1;

  while (stack.length) {
    const [cr, cc] = stack.pop()!;
    out.push([cr, cc]);
    for (const [dr, dc] of [[1, 0], [-1, 0], [0, 1], [0, -1]] as const) {
      const nr = cr + dr;
      const nc = cc + dc;
      if (nr < 0 || nr >= rows || nc < 0 || nc >= cols) continue;
      const k = nr * cols + nc;
      if (seen[k]) continue;
      if (g[nr][nc] !== target) continue;
      seen[k] = 1;
      stack.push([nr, nc]);
    }
  }
  return out;
}

export function applyEditsToGrid(g: Grid, edits: EditCell[]): Grid {
  const out = cloneGrid(g);
  for (const { cell, to } of edits) {
    const [r, c] = cell;
    if (!inBounds(out, r, c)) continue;      // 越界忽略，不让一次误操作炸掉整批
    out[r][c] = to;
  }
  return out;
}

export function diffToEdits(before: Grid, after: Grid): EditCell[] {
  const edits: EditCell[] = [];
  const { rows, cols } = gridSize(after);
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const b = before[r]?.[c];
      const a = after[r][c];
      if (b !== a) edits.push({ cell: [r, c], to: a });
    }
  }
  return edits;
}

export function mergeEdits(edits: EditCell[]): EditCell[] {
  const order: string[] = [];
  const last = new Map<string, EditCell>();
  for (const e of edits) {
    const key = `${e.cell[0]},${e.cell[1]}`;
    if (!last.has(key)) order.push(key);
    last.set(key, e);
  }
  return order.map((k) => last.get(k)!);
}

export function colorCounts(g: Grid): Map<number, number> {
  const m = new Map<number, number>();
  for (const row of g) {
    for (const v of row) {
      if (v === null) continue;
      m.set(v, (m.get(v) ?? 0) + 1);
    }
  }
  return m;
}

/** 撤销栈。存整张网格快照——120×120 才 14400 个数字，几十步历史毫无压力。 */
export class EditStack {
  private history: Grid[];
  private index: number;

  constructor(initial: Grid) {
    this.history = [cloneGrid(initial)];
    this.index = 0;
  }

  get current(): Grid {
    return this.history[this.index];
  }

  get canUndo(): boolean {
    return this.index > 0;
  }

  get canRedo(): boolean {
    return this.index < this.history.length - 1;
  }

  push(grid: Grid): void {
    this.history = this.history.slice(0, this.index + 1);   // 丢掉重做分支
    this.history.push(cloneGrid(grid));
    this.index = this.history.length - 1;
  }

  undo(): Grid | null {
    if (!this.canUndo) return null;
    this.index -= 1;
    return this.current;
  }

  redo(): Grid | null {
    if (!this.canRedo) return null;
    this.index += 1;
    return this.current;
  }

  reset(grid: Grid): void {
    this.history = [cloneGrid(grid)];
    this.index = 0;
  }
}
