import type { Grid } from "../api/types";
import { gridSize } from "./grid";

/** 只声明本模块真正用到的成员——测试就能传一个记录调用的假对象。
 *  属性类型必须与 DOM 的 CanvasRenderingContext2D 一致，否则真 ctx 不可赋值给它。 */
export interface Ctx {
  fillStyle: string | CanvasGradient | CanvasPattern;
  strokeStyle: string | CanvasGradient | CanvasPattern;
  lineWidth: number;
  font: string;
  textAlign: CanvasTextAlign;
  textBaseline: CanvasTextBaseline;
  fillRect(x: number, y: number, w: number, h: number): void;
  strokeRect(x: number, y: number, w: number, h: number): void;
  beginPath(): void;
  moveTo(x: number, y: number): void;
  lineTo(x: number, y: number): void;
  stroke(): void;
  fillText(text: string, x: number, y: number): void;
  clearRect(x: number, y: number, w: number, h: number): void;
  save(): void;
  restore(): void;
}

export interface DrawOptions {
  cellPx: number;
  showCodes: boolean;
  minorEvery: number;
  majorEvery: number;
  highlight?: [number, number][];
  protectedCells?: [number, number][];
  codeOf?: (index: number) => string;
}

export const DEFAULT_DRAW: DrawOptions = {
  cellPx: 16,
  showCodes: false,
  minorEvery: 5,
  majorEvery: 10,
};

const EMPTY_BG = "#F5F5F5";
const UNKNOWN = "#DCDCDC";
const LINE = "#9A9A9A";
const MAJOR = "#1E1E1E";
const HIGHLIGHT = "#FF0000";
const PROTECTED = "#1E64FF";
const MIN_CELL_PX = 2;

export function canvasSize(g: Grid, o: DrawOptions): { width: number; height: number } {
  const { rows, cols } = gridSize(g);
  return { width: cols * o.cellPx + 1, height: rows * o.cellPx + 1 };
}

export function cellAt(x: number, y: number, g: Grid, o: DrawOptions): [number, number] | null {
  const { rows, cols } = gridSize(g);
  if (x < 0 || y < 0) return null;
  const c = Math.floor(x / o.cellPx);
  const r = Math.floor(y / o.cellPx);
  if (r < 0 || r >= rows || c < 0 || c >= cols) return null;
  return [r, c];
}

export function fitCellPx(g: Grid, maxWidth: number, maxHeight: number): number {
  const { rows, cols } = gridSize(g);
  if (rows === 0 || cols === 0) return MIN_CELL_PX;
  const px = Math.floor(Math.min((maxWidth - 1) / cols, (maxHeight - 1) / rows));
  return Math.max(MIN_CELL_PX, px);
}

function textColorFor(hex: string): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 140 ? "#000000" : "#FFFFFF";
}

export function drawPattern(ctx: Ctx, g: Grid, colors: Map<number, string>,
                            o: DrawOptions): void {
  const { rows, cols } = gridSize(g);
  if (rows === 0 || cols === 0) return;
  const cp = o.cellPx;
  const { width, height } = canvasSize(g, o);
  ctx.clearRect(0, 0, width, height);

  // 格子底色
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const x = c * cp;
      const y = r * cp;
      const v = g[r][c];
      ctx.fillStyle = v === null ? EMPTY_BG : (colors.get(v) ?? UNKNOWN);
      ctx.fillRect(x, y, cp, cp);
    }
  }

  // 色号文字：留边距、不顶格线
  if (o.showCodes && cp >= 14) {
    ctx.font = `${Math.max(6, Math.floor(cp * 0.4))}px sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const v = g[r][c];
        if (v === null) continue;
        const hex = colors.get(v);
        if (!hex) continue;
        ctx.fillStyle = textColorFor(hex);
        ctx.fillText(o.codeOf ? o.codeOf(v) : String(v), c * cp + cp / 2, r * cp + cp / 2);
      }
    }
  }

  // 网格线：坐标全部取整，1pt 线被抗锯齿摊开会变成一层灰雾
  for (let c = 0; c <= cols; c++) {
    const major = o.majorEvery > 0 && c % o.majorEvery === 0;
    ctx.strokeStyle = major ? MAJOR : LINE;
    ctx.lineWidth = major ? 2 : 1;
    ctx.beginPath();
    const x = Math.round(c * cp);
    ctx.moveTo(x, 0);
    ctx.lineTo(x, Math.round(rows * cp));
    ctx.stroke();
  }
  for (let r = 0; r <= rows; r++) {
    const major = o.majorEvery > 0 && r % o.majorEvery === 0;
    ctx.strokeStyle = major ? MAJOR : LINE;
    ctx.lineWidth = major ? 2 : 1;
    ctx.beginPath();
    const y = Math.round(r * cp);
    ctx.moveTo(0, y);
    ctx.lineTo(Math.round(cols * cp), y);
    ctx.stroke();
  }

  for (const [r, c] of o.protectedCells ?? []) {
    ctx.strokeStyle = PROTECTED;
    ctx.lineWidth = 2;
    ctx.strokeRect(c * cp + 2, r * cp + 2, Math.max(1, cp - 4), Math.max(1, cp - 4));
  }
  for (const [r, c] of o.highlight ?? []) {
    ctx.strokeStyle = HIGHLIGHT;
    // 格子小的时候 2px 描边占掉半格，几百格一起亮就糊成一片红
    ctx.lineWidth = cp >= 12 ? 2 : 1;
    ctx.strokeRect(c * cp + 1, r * cp + 1, Math.max(1, cp - 2), Math.max(1, cp - 2));
  }
}
