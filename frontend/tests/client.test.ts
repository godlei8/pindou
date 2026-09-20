import { beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, DEFAULT_PARAMS, api } from "../src/api/client";

function mockFetch(impl: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) =>
    impl(String(input), init));
  vi.stubGlobal("fetch", spy);
  return spy;
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("api client", () => {
  beforeEach(() => vi.unstubAllGlobals());

  test("默认参数与后端 Params 对齐", () => {
    expect(DEFAULT_PARAMS.grid_long_side).toBe(58);
    expect(DEFAULT_PARAMS.max_colors).toBe(24);
    expect(DEFAULT_PARAMS.smoothness).toBe(2.0);
    expect(DEFAULT_PARAMS.dither).toBe(false);
  });

  test("每个请求都带 credentials: include", async () => {
    const spy = mockFetch(() =>
      json({ id: "u1", username: "a", ai_quota: 1, ai_used: 0, is_admin: false }));
    await api.me();
    expect(spy.mock.calls[0][1]?.credentials).toBe("include");
  });

  test("GET 不带 content-type，POST JSON 带", async () => {
    const spy = mockFetch(() => json({}));
    await api.me();
    expect((spy.mock.calls[0][1]?.headers as Record<string, string>)?.["Content-Type"])
      .toBeUndefined();
    await api.login("a", "b");
    expect((spy.mock.calls[1][1]?.headers as Record<string, string>)["Content-Type"])
      .toBe("application/json");
  });

  test("把 detail 归一化成 ApiError", async () => {
    mockFetch(() => json({ detail: "邀请码无效或已用完" }, 400));
    await expect(api.register("a", "pw12345678", "NOPE")).rejects.toThrowError(ApiError);
    try {
      await api.register("a", "pw12345678", "NOPE");
    } catch (e) {
      expect((e as ApiError).status).toBe(400);
      expect((e as ApiError).detail).toBe("邀请码无效或已用完");
    }
  });

  test("422 的 Pydantic 错误也能读出人话", async () => {
    mockFetch(() => json({
      detail: [{ loc: ["body", "edits"], msg: "List should have at least 1 item" }],
    }, 422));
    try {
      await api.applyEdits("p1", []);
    } catch (e) {
      expect((e as ApiError).status).toBe(422);
      expect((e as ApiError).detail).toContain("edits");
    }
  });

  test("非 JSON 的错误响应不会炸", async () => {
    mockFetch(() => new Response("<html>502</html>", { status: 502 }));
    try {
      await api.me();
    } catch (e) {
      expect((e as ApiError).status).toBe(502);
      expect((e as ApiError).detail.length).toBeGreaterThan(0);
    }
  });

  test("204 返回 null 而不是解析失败", async () => {
    mockFetch(() => new Response(null, { status: 204 }));
    await expect(api.logout()).resolves.toBeNull();
  });

  test("createProject 用 multipart 且不手动设 Content-Type", async () => {
    const spy = mockFetch(() => json({ id: "p1", name: "t", created_at: "", patterns: [] }, 201));
    await api.createProject("我的图",
      new File([new Uint8Array([1, 2])], "a.png", { type: "image/png" }));
    const init = spy.mock.calls[0][1]!;
    expect(init.body).toBeInstanceOf(FormData);
    // 手动设 Content-Type 会丢掉 multipart 的 boundary，必须交给浏览器
    expect((init.headers as Record<string, string> | undefined)?.["Content-Type"]).toBeUndefined();
  });

  test("applyEdits 提交显式格子列表", async () => {
    const spy = mockFetch(() => json({ id: "pat2" }));
    await api.applyEdits("pat1", [{ cell: [1, 2], to: 7 }, { cell: [3, 4], to: null }]);
    const body = JSON.parse(String(spy.mock.calls[0][1]!.body));
    expect(body.edits).toEqual([{ cell: [1, 2], to: 7 }, { cell: [3, 4], to: null }]);
  });

  test("exportUrl / sourceUrl 拼出可直接给 <img>/<a> 的地址", () => {
    expect(api.sourceUrl("p1")).toBe("/api/projects/p1/source");
    expect(api.exportUrl("pat1", { format: "pdf", bead_mm: 5 }))
      .toBe("/api/patterns/pat1/export?format=pdf&bead_mm=5");
    expect(api.exportUrl("pat1", { format: "png", cell_px: 20 }))
      .toBe("/api/patterns/pat1/export?format=png&cell_px=20");
  });

  test("suggestSizes 带上 base 查询参数", async () => {
    const spy = mockFetch(() => json([]));
    await api.suggestSizes("p1", 40);
    expect(String(spy.mock.calls[0][0])).toBe("/api/projects/p1/suggest-sizes?base=40");
  });
});
