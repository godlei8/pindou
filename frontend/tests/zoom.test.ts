import { describe, expect, test } from "vitest";

import {
  CODES_ZOOM, MAX_ZOOM, MIN_ZOOM, SHOW_CODES_MIN, ZOOM_LADDER, cellPxFor, zoomIn, zoomOut,
} from "../src/lib/zoom";

describe("缩放档位", () => {
  test("档位全是整数——像素图纸不能落在半格上", () => {
    expect(ZOOM_LADDER.every((v) => Number.isInteger(v) && v > 0)).toBe(true);
  });

  test("档位严格递增", () => {
    for (let i = 1; i < ZOOM_LADDER.length; i++) {
      expect(ZOOM_LADDER[i]).toBeGreaterThan(ZOOM_LADDER[i - 1]);
    }
  });

  test("放大跳到下一档", () => {
    expect(zoomIn(2)).toBe(3);
    expect(zoomIn(12)).toBe(14);
  });

  test("缩小跳到上一档", () => {
    expect(zoomOut(3)).toBe(2);
    expect(zoomOut(14)).toBe(12);
  });

  test("自动适应算出的值不在档位上时，也能就近进退", () => {
    // fitCellPx 返回的是 floor(容器/格数)，7、13、19 这种值很常见
    expect(zoomIn(7)).toBe(8);
    expect(zoomOut(7)).toBe(6);
    expect(zoomIn(13)).toBe(14);
    expect(zoomOut(13)).toBe(12);
  });

  test("到头就停住，不会越界", () => {
    expect(zoomIn(MAX_ZOOM)).toBe(MAX_ZOOM);
    expect(zoomIn(9999)).toBe(MAX_ZOOM);
    expect(zoomOut(MIN_ZOOM)).toBe(MIN_ZOOM);
    expect(zoomOut(1)).toBe(MIN_ZOOM);
  });

  test("一进一退回到原档", () => {
    for (const v of ZOOM_LADDER.slice(1, -1)) {
      expect(zoomOut(zoomIn(v))).toBe(v);
      expect(zoomIn(zoomOut(v))).toBe(v);
    }
  });
});

describe("缩放模式", () => {
  test("色号档位能看清色号，且落在档位上", () => {
    expect(CODES_ZOOM).toBeGreaterThanOrEqual(SHOW_CODES_MIN);
    expect(ZOOM_LADDER).toContain(CODES_ZOOM);
  });

  test("默认的色号模式：窗口小时放大到看得清色号", () => {
    expect(cellPxFor("codes", 9)).toBe(CODES_ZOOM);
  });

  test("默认的色号模式：窗口够大时就等于适应，不多余放大", () => {
    expect(cellPxFor("codes", 30)).toBe(30);
  });

  test("适应模式就是适应", () => {
    expect(cellPxFor("fit", 9)).toBe(9);
  });

  test("手动档位原样使用", () => {
    expect(cellPxFor(14, 9)).toBe(14);
  });
});
