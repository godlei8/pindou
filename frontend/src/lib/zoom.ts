/** 缩放档位：每格多少像素。
 *
 *  用固定档位而不是"乘 1.25 再取整"，因为像素图纸必须落在整数格宽上——
 *  连续缩放会得到 13.75 这种值，格线和色号文字都会被抗锯齿糊掉。
 *  低档密（看整体时一格一两像素的差别很明显），高档疏。 */
export const ZOOM_LADDER = [2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 20, 24, 28, 32, 40, 48];

export const MIN_ZOOM = ZOOM_LADDER[0];
export const MAX_ZOOM = ZOOM_LADDER[ZOOM_LADDER.length - 1];

/** 下一档更大的。已经最大就停在最大。 */
export function zoomIn(cellPx: number): number {
  return ZOOM_LADDER.find((v) => v > cellPx) ?? MAX_ZOOM;
}

/** 下一档更小的。已经最小就停在最小。 */
export function zoomOut(cellPx: number): number {
  let out = MIN_ZOOM;
  for (const v of ZOOM_LADDER) {
    if (v < cellPx) out = v;
    else break;
  }
  return out;
}
