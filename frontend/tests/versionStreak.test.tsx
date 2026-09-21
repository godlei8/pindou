import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { DEFAULT_PARAMS } from "../src/api/client";
import { usePattern } from "../src/hooks/usePattern";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function pattern(id: string, extra: Record<string, unknown> = {}) {
  return {
    id, project_id: "p1", parent_id: null, origin: "generated", ai_render_id: null,
    params: DEFAULT_PARAMS, grid: [[0]], color_stats: { "0": 1 },
    buildability: null, materials: [], palette_id: "mard",
    created_at: "2026-09-21T00:00:00Z", ...extra,
  };
}

const brief = (id: string) => ({
  id, origin: "generated", parent_id: null, ai_render_id: null,
  created_at: "2026-09-20T00:00:00Z", score: 80, n_colors: 1,
});

/** 重算接口：按调用顺序生成 gen1、gen2…，并像后端一样照 replaces 删掉旧版。
 *  hold=true 时把响应扣住，由测试手动放行，用来制造"请求还在路上"的局面。 */
function makeApi(opts: { hold?: boolean } = {}) {
  let n = 0;
  const bodies: Record<string, unknown>[] = [];
  const release: Array<() => void> = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/api/projects/p1/patterns") && init?.method === "POST") {
      const body = JSON.parse(String(init.body));
      bodies.push(body);
      const res = json(pattern(`gen${++n}`, { replaced_id: body.replaces ?? null }));
      if (!opts.hold) return res;
      return new Promise<Response>((ok) => release.push(() => ok(res)));
    }
    if (url.endsWith("/api/projects/p1")) {
      return json({ id: "p1", name: "t", created_at: "", patterns: [brief("pat1"), brief("old0")] });
    }
    if (url.includes("/api/patterns/old0")) return json(pattern("old0"));
    if (url.includes("/api/patterns/pat1")) return json(pattern("pat1"));
    if (url.includes("/palettes/mard/colors")) return json([]);
    if (url.includes("/suggest-sizes")) return json([]);
    return json({ detail: `未 mock：${url}` }, 500);
  });
  return { fetchMock, bodies, release };
}

async function mountLoaded() {
  const hook = renderHook(() => usePattern("p1"));
  await waitFor(() => expect(hook.result.current.pattern?.id).toBe("pat1"));
  return hook;
}

const tweak = (hook: Awaited<ReturnType<typeof mountLoaded>>, smoothness: number) =>
  act(() => hook.result.current.setParams({ ...hook.result.current.params, smoothness }));

describe("连续调参只留最后一版", () => {
  beforeEach(() => vi.unstubAllGlobals());

  test("载入已有项目后的第一次调参新增一版，不替换——载入的那版是历史", async () => {
    const api = makeApi();
    vi.stubGlobal("fetch", api.fetchMock);
    const hook = await mountLoaded();

    tweak(hook, 3);
    await waitFor(() => expect(api.bodies).toHaveLength(1));
    expect(api.bodies[0].replaces).toBeNull();
  });

  test("接着调，就替换上一次调出来的那版", async () => {
    const api = makeApi();
    vi.stubGlobal("fetch", api.fetchMock);
    const hook = await mountLoaded();

    tweak(hook, 3);
    await waitFor(() => expect(hook.result.current.pattern?.id).toBe("gen1"));
    tweak(hook, 2.5);
    await waitFor(() => expect(hook.result.current.pattern?.id).toBe("gen2"));
    tweak(hook, 1.5);
    await waitFor(() => expect(hook.result.current.pattern?.id).toBe("gen3"));

    expect(api.bodies.map((b) => b.replaces)).toEqual([null, "gen1", "gen2"]);
  });

  test("被替换掉的版本从版本列表里消失，历史版本不动", async () => {
    const api = makeApi();
    vi.stubGlobal("fetch", api.fetchMock);
    const hook = await mountLoaded();

    tweak(hook, 3);
    await waitFor(() => expect(hook.result.current.pattern?.id).toBe("gen1"));
    tweak(hook, 2);
    await waitFor(() => expect(hook.result.current.pattern?.id).toBe("gen2"));

    // 拖了两下：历史两版 + 最后一版，gen1 被替换掉了
    expect(hook.result.current.versions.map((v) => v.id)).toEqual(["gen2", "pat1", "old0"]);
  });

  test("切到历史版本后再调参，不能把刚选中的那版替换掉", async () => {
    const api = makeApi();
    vi.stubGlobal("fetch", api.fetchMock);
    const hook = await mountLoaded();

    tweak(hook, 3);
    await waitFor(() => expect(hook.result.current.pattern?.id).toBe("gen1"));
    await act(() => hook.result.current.selectVersion("old0"));
    tweak(hook, 1);
    await waitFor(() => expect(api.bodies).toHaveLength(2));

    expect(api.bodies[1].replaces).toBeNull();
  });

  test("请求还在路上时又改了两次：只再算一次，用最新的参数", async () => {
    const api = makeApi({ hold: true });
    vi.stubGlobal("fetch", api.fetchMock);
    const hook = await mountLoaded();

    tweak(hook, 3);
    await waitFor(() => expect(api.bodies).toHaveLength(1));
    tweak(hook, 2.5);                         // 这两次都发生在第一个请求回来之前
    await new Promise((r) => setTimeout(r, 350));
    tweak(hook, 1.5);
    await new Promise((r) => setTimeout(r, 350));
    expect(api.bodies).toHaveLength(1);       // 没有并发打出去

    await act(async () => { api.release.shift()!(); });
    await waitFor(() => expect(api.bodies).toHaveLength(2));
    // 中间的 2.5 被跳过；并且第二次替换的是第一次的结果，不会两个请求争同一版
    expect(api.bodies[1].params).toMatchObject({ smoothness: 1.5 });
    expect(api.bodies[1].replaces).toBe("gen1");

    await act(async () => { api.release.shift()!(); });
    await waitFor(() => expect(hook.result.current.pattern?.id).toBe("gen2"));
  });
});
