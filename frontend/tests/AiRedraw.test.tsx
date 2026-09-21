import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { AuthProvider } from "../src/hooks/useAuth";
import { WorkbenchPage } from "../src/pages/WorkbenchPage";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const USER = { id: "u1", username: "amy", ai_quota: 5, ai_used: 0, is_admin: false };
const COLORS = [
  { index: 0, code: "H2", name: "H2", hex: "#FFFFFF", role: null, confidence: "agree" },
];
const PRESETS = [{ id: "sp1", name: "Q版盲盒", prompt: "...", version: 1 }];

const PARAMS = {
  grid_long_side: 58, max_colors: 24, smoothness: 2, dither: false,
  palette_id: "mard", small_color_threshold: 10, lock_outlines: true,
};

function pattern(id: string, aiRenderId: string | null, score = 90) {
  return {
    id, project_id: "p1", parent_id: null,
    // 后端对两种来源都写 "generated"——origin 说的是"怎么产生的"，不是"基于哪张图"
    origin: "generated",
    ai_render_id: aiRenderId,
    params: PARAMS,
    grid: [[0, 0], [0, 0]],
    color_stats: { "0": 4 },
    buildability: { score, confetti_pct: 0.5, n_components: 1, metrics: {}, issues: [] },
    materials: [{ index: 0, code: "H2", hex: "#FFFFFF", count: 4, packs: 1 }],
    palette_id: "mard", created_at: "2026-09-20T00:00:00Z",
  };
}

const PROJECT = {
  id: "p1", name: "小熊猫", created_at: "2026-09-20T00:00:00Z",
  patterns: [{ id: "pat1", origin: "generated", parent_id: null,
               created_at: "2026-09-20T00:00:00Z", score: 90, n_colors: 1 }],
};

/** jobStates 按顺序供给 GET /jobs/7 的返回，最后一项会一直重复。 */
function makeFetch(jobStates: Array<Record<string, unknown>>, originalScore = 90) {
  let poll = 0;
  return vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/auth/me")) return json(USER);
    if (url.includes("/palettes/mard/colors")) return json(COLORS);
    if (url.includes("/suggest-sizes")) return json([]);
    if (url.includes("/style-presets")) return json(PRESETS);
    if (url.includes("/projects/p1/generate")) {
      return json({ id: 7, type: "generate", status: "pending", result: null,
                    error: null, created_at: "2026-09-20T00:00:00Z" }, 202);
    }
    if (url.includes("/jobs/7")) {
      const state = jobStates[Math.min(poll++, jobStates.length - 1)];
      return json({ id: 7, type: "generate", error: null,
                    created_at: "2026-09-20T00:00:00Z", ...state });
    }
    if (url.includes("/api/patterns/pat-ai")) return json(pattern("pat-ai", "r1"));
    if (url.includes("/api/patterns/pat1")) return json(pattern("pat1", null, originalScore));
    if (url.includes("/projects/p1/patterns")) return json(pattern("pat2", "r1"));
    if (url.endsWith("/api/projects/p1")) return json(PROJECT);
    return json({ detail: `未 mock 的请求：${url}` }, 500);
  });
}

function mount() {
  return render(
    <MemoryRouter initialEntries={["/p/p1"]}>
      <AuthProvider>
        <Routes><Route path="/p/:projectId" element={<WorkbenchPage />} /></Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function redraw() {
  await waitFor(() => screen.getByRole("button", { name: "用 AI 重绘" }));
  await userEvent.click(screen.getByRole("button", { name: "用 AI 重绘" }));
}

describe("AI 重绘", () => {
  beforeEach(() => vi.unstubAllGlobals());

  test("没有 AI 图时不显示对比切换", async () => {
    vi.stubGlobal("fetch", makeFetch([{ status: "pending", result: null }]));
    mount();
    await waitFor(() => screen.getByRole("button", { name: "用 AI 重绘" }));
    expect(screen.queryByRole("tab", { name: "AI 图" })).toBeNull();
  });

  test("出图完成后切到 AI 图，图片指向 AI 渲染结果", async () => {
    vi.stubGlobal("fetch",
      makeFetch([{ status: "done", result: { pattern_id: "pat-ai", ai_render_id: "r1" } }]));
    const { container } = mount();
    await redraw();

    await waitFor(() => expect(screen.getByRole("tab", { name: "AI 图" })).toBeTruthy());
    // 用户刚花了额度，默认就该看到这张
    expect(screen.getByRole("tab", { name: "AI 图" }).getAttribute("aria-selected")).toBe("true");
    const img = container.querySelector("img")!;
    expect(img.getAttribute("src")).toBe("/api/projects/p1/ai-renders/r1/image");
  });

  test("切回原图会换回原图地址", async () => {
    vi.stubGlobal("fetch",
      makeFetch([{ status: "done", result: { pattern_id: "pat-ai", ai_render_id: "r1" } }]));
    const { container } = mount();
    await redraw();
    await waitFor(() => screen.getByRole("tab", { name: "AI 图" }));

    await userEvent.click(screen.getByRole("tab", { name: "原图" }));
    expect(container.querySelector("img")!.getAttribute("src"))
      .toBe("/api/projects/p1/source");
  });

  test("出图失败时显示后端的错误原文，且可以关掉", async () => {
    vi.stubGlobal("fetch",
      makeFetch([{ status: "failed", result: null, error: "provider 返回 InvalidParameter" }]));
    mount();
    await redraw();

    await waitFor(() => expect(screen.getByRole("alert").textContent)
      .toContain("provider 返回 InvalidParameter"));
    await userEvent.click(screen.getByRole("button", { name: "知道了" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("额度为 0 时按钮禁用并给出可行的替代路径", async () => {
    const fetchMock = makeFetch([{ status: "pending", result: null }]);
    const noQuota = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes("/auth/me")) return json({ ...USER, ai_used: 5 });
      return fetchMock(input, init);
    });
    vi.stubGlobal("fetch", noQuota);
    mount();

    await waitFor(() =>
      expect(screen.getByRole("button", { name: "用 AI 重绘" })).toHaveProperty("disabled", true));
    expect(screen.getByText(/不用 AI 也能直接出图/)).toBeTruthy();
  });

  test("AI 出图后改参数，重算仍基于那张 AI 图", async () => {
    // 这是个真会花钱的回归：不带 ai_render_id 就会悄悄退回原图，AI 额度白花
    const fetchMock =
      makeFetch([{ status: "done", result: { pattern_id: "pat-ai", ai_render_id: "r1" } }]);
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await redraw();
    await waitFor(() => screen.getByRole("tab", { name: "AI 图" }));

    const colors = screen.getByLabelText("最多色数");
    await userEvent.clear(colors);
    await userEvent.type(colors, "12");

    await waitFor(() => {
      const call = fetchMock.mock.calls.find((c) => String(c[0]).endsWith("/projects/p1/patterns"));
      expect(call).toBeTruthy();
      const body = JSON.parse(String(call![1]!.body));
      expect(body.source).toBe("ai");
      expect(body.ai_render_id).toBe("r1");
    });
  });
});

describe("版本来源标注", () => {
  beforeEach(() => vi.unstubAllGlobals());

  test("AI 出的图纸标为「基于 AI 图」", async () => {
    // origin 对两种来源都是 "generated"，只有 ai_render_id 能区分。
    // 曾经按 origin 判断，结果 AI 出的图纸被标成「基于原图」。
    vi.stubGlobal("fetch",
      makeFetch([{ status: "done", result: { pattern_id: "pat-ai", ai_render_id: "r1" } }]));
    mount();
    await redraw();
    await waitFor(() => expect(screen.getByText(/基于 AI 图/)).toBeTruthy());
  });

  test("原图出的图纸标为「基于原图」", async () => {
    vi.stubGlobal("fetch", makeFetch([{ status: "pending", result: null }]));
    mount();
    await waitFor(() => expect(screen.getByText(/基于原图/)).toBeTruthy());
  });
});


describe("「这张图可能不需要 AI」提示", () => {
  beforeEach(() => vi.unstubAllGlobals());

  test("原图出的图纸已经够好时给出提示", async () => {
    vi.stubGlobal("fetch", makeFetch([{ status: "pending", result: null }], 89.2));
    mount();
    await waitFor(() => expect(screen.getByText(/这张图可能不需要 AI/)).toBeTruthy());
    // 提示只是提示，不拦着用户去试
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "用 AI 重绘" })).toHaveProperty("disabled", false));
  });

  test("原图出的图纸一般时不提示", async () => {
    vi.stubGlobal("fetch", makeFetch([{ status: "pending", result: null }], 81.6));
    mount();
    await waitFor(() => screen.getByRole("button", { name: "用 AI 重绘" }));
    expect(screen.queryByText(/这张图可能不需要 AI/)).toBeNull();
  });

  test("已经在看 AI 图时不再提示——额度都花了，马后炮没用", async () => {
    vi.stubGlobal("fetch",
      makeFetch([{ status: "done", result: { pattern_id: "pat-ai", ai_render_id: "r1" } }], 89.2));
    mount();
    await waitFor(() => expect(screen.getByText(/这张图可能不需要 AI/)).toBeTruthy());
    await userEvent.click(screen.getByRole("button", { name: "用 AI 重绘" }));
    await waitFor(() => screen.getByRole("tab", { name: "AI 图" }));
    expect(screen.queryByText(/这张图可能不需要 AI/)).toBeNull();
  });

  test("没额度时不提示——已经有一条更该看的消息了", async () => {
    const base = makeFetch([{ status: "pending", result: null }], 89.2);
    vi.stubGlobal("fetch", vi.fn(async (i: RequestInfo | URL, init?: RequestInit) =>
      String(i).includes("/auth/me") ? json({ ...USER, ai_used: 5 }) : base(i, init)));
    mount();
    await waitFor(() => screen.getByText(/不用 AI 也能直接出图/));
    expect(screen.queryByText(/这张图可能不需要 AI/)).toBeNull();
  });
});
