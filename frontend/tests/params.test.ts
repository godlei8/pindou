import { describe, expect, test } from "vitest";

import { DEFAULT_PARAMS, paramsOf } from "../src/api/client";

describe("参数默认值", () => {
  test("新出图默认去掉纯色背景——拼豆拼的是形状，不是一整块矩形", () => {
    expect(DEFAULT_PARAMS.remove_background).toBe(true);
  });

  test("旧图纸参数里没有 remove_background：按它当时的含义，是没去背景的", () => {
    // 不能套用新默认值 true——否则界面上勾着"去掉背景"，图上背景却明明填满了豆
    expect(paramsOf({ params: { grid_long_side: 40 } }).remove_background).toBe(false);
  });

  test("图纸自己记着的值原样取回", () => {
    expect(paramsOf({ params: { remove_background: true } }).remove_background).toBe(true);
    expect(paramsOf({ params: { grid_long_side: 40 } }).grid_long_side).toBe(40);
  });
});
