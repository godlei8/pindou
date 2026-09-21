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

/** 每格至少这么大才画色号。再小色号就挤成一团，看不清反而添乱。 */
export const SHOW_CODES_MIN = 18;

/** 能看清色号的最小档位（档位里第一个 ≥ SHOW_CODES_MIN 的，目前是 20）。 */
export const CODES_ZOOM = ZOOM_LADDER.find((v) => v >= SHOW_CODES_MIN) ?? MAX_ZOOM;

/** 缩放模式。
 *  - codes：默认。保证色号看得清——窗口够大就等于适应，不够大就放到能看清为止、让画布滚动。
 *    拼的时候要逐格对色号，一进来就该看得到；看全貌再点「适应」。
 *  - fit：整张塞进窗口，看全貌用。
 *  - number：手动缩放到的档位。 */
export type ZoomMode = "codes" | "fit" | number;

export function cellPxFor(mode: ZoomMode, fitPx: number): number {
  if (mode === "fit") return fitPx;
  if (mode === "codes") return Math.max(fitPx, CODES_ZOOM);
  return mode;
}
