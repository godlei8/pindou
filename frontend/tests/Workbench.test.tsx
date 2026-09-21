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
  { index: 1, code: "R10", name: "R10", hex: "#FFDD00", role: null, confidence: "agree" },
  { index: 2, code: "T1", name: "T1", hex: "#E2DFD7", role: "clear", confidence: "conflict" },
];

function makePattern(id: string) {
  return {
    id, project_id: "p1", parent_id: null, origin: "generated",
    params: { grid_long_side: 58, max_colors: 24, smoothness: 2, dither: false,
              palette_id: "mard", small_color_threshold: 10, lock_outlines: true },
    grid: [[0, 1], [1, 0]],
    color_stats: { "0": 2, "1": 2 },
    buildability: { score: 88, confetti_pct: 1.2, n_components: 1, metrics: {},
                    issues: [{ type: "diagonal_link", cells: [[0, 0], [1, 1]],
                               action: "bridge_with_clear", target_color: null, delta_e: null,
                               patch_cells: [[0, 1]], severity: 1 }] },
    materials: [{ index: 0, code: "H2", hex: "#FFFFFF", count: 2, packs: 1 }],
    palette_id: "mard", created_at: "2026-09-20T00:00:00Z",
  };
}

const PROJECT = {
  id: "p1", name: "测试", created_at: "2026-09-20T00:00:00Z",
  patterns: [{ id: "pat1", origin: "generated", parent_id: null,
               created_at: "2026-09-20T00:00:00Z", score: 88, n_colors: 2 }],
};

function routeFetch(projectResponse?: () => Response) {
  return vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input);
    if (url.includes("/auth/me")) return json(USER);
    if (url.includes("/palettes/mard/colors")) return json(COLORS);
    if (url.includes("/suggest-sizes")) return json([{ long_side: 44, detail_loss: 0.01 }]);
    if (url.includes("/style-presets")) return json([]);
    if (url.includes("/patterns/pat1/apply-patch")) return json(makePattern("pat2"));
    if (url.includes("/patterns/pat1/edits")) return json(makePattern("pat3"));
    if (url.includes("/patterns/pat1/feedback")) return new Response(null, { status: 204 });
    if (url.includes("/api/patterns/pat1")) return json(makePattern("pat1"));
    if (url.includes("/projects/p1/patterns")) return json(makePattern("pat9"));
    if (url.endsWith("/api/projects/p1")) return projectResponse ? projectResponse() : json(PROJECT);
    return json({ detail: `未 mock 的请求：${url}` }, 500);
  });
}

function mount() {
  // 工作台的每个请求都要会话，现实里它只可能跑在 AuthProvider 里面
  return render(
    <MemoryRouter initialEntries={["/p/p1"]}>
      <AuthProvider>
        <Routes><Route path="/p/:projectId" element={<WorkbenchPage />} /></Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function paintOneCell(container: HTMLElement) {
  await userEvent.click(screen.getByRole("button", { name: "R10" }));
  const canvas = container.querySelector("canvas")!;
  canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 999, height: 999,
                                          right: 999, bottom: 999, x: 0, y: 0,
                                          toJSON: () => ({}) });
  await userEvent.pointer({ target: canvas, coords: { clientX: 2, clientY: 2 },
                            keys: "[MouseLeft>]" });
  await userEvent.pointer({ target: canvas, keys: "[/MouseLeft]" });
}

describe("WorkbenchPage", () => {
  beforeEach(() => vi.unstubAllGlobals());

  test("载入项目最新版本并显示评分与清单", async () => {
    vi.stubGlobal("fetch", routeFetch());
    mount();
    await waitFor(() => expect(screen.getByText("88")).toBeTruthy());
    expect(screen.getByText("H2")).toBeTruthy();
    expect(screen.getByText(/对角虚连/)).toBeTruthy();
  });

  test("改参数防抖后只打一次后端", async () => {
    const fetchMock = routeFetch();
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByLabelText(/格数/));

    const count = () => fetchMock.mock.calls.filter(
      (c) => String(c[0]).includes("/projects/p1/patterns")).length;
    const before = count();
    const input = screen.getByLabelText(/格数/) as HTMLInputElement;
    await userEvent.clear(input);
    await userEvent.type(input, "40");

    await waitFor(() => expect(count()).toBe(before + 1), { timeout: 3000 });
  });

  test("接受修复建议后载入新版本", async () => {
    vi.stubGlobal("fetch", routeFetch());
    mount();
    await waitFor(() => screen.getByRole("button", { name: /应用/ }));
    await userEvent.click(screen.getByRole("button", { name: /应用/ }));
    await waitFor(() => expect(screen.getByText(/pat2/)).toBeTruthy());
  });

  test("画笔改格后出现未保存标识，保存提交显式格子列表", async () => {
    const fetchMock = routeFetch();
    vi.stubGlobal("fetch", fetchMock);
    const { container } = mount();
    await waitFor(() => expect(container.querySelector("canvas")).toBeTruthy());

    await paintOneCell(container);
    await waitFor(() => expect(screen.getByText(/未保存/)).toBeTruthy());
    await userEvent.click(screen.getByRole("button", { name: /保存/ }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find((c) => String(c[0]).includes("/edits"));
      expect(call).toBeTruthy();
      const body = JSON.parse(String(call![1]!.body));
      expect(Array.isArray(body.edits)).toBe(true);
      expect(body.edits[0]).toHaveProperty("cell");
      expect(body.edits[0]).toHaveProperty("to");
      expect(JSON.stringify(body)).not.toContain("bucket");   // 提交结果不是操作意图
    });
  });

  test("有未保存改动时改参数会二次确认", async () => {
    vi.stubGlobal("fetch", routeFetch());
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { container } = mount();
    await waitFor(() => expect(container.querySelector("canvas")).toBeTruthy());

    await paintOneCell(container);
    await waitFor(() => screen.getByText(/未保存/));

    const input = screen.getByLabelText(/格数/) as HTMLInputElement;
    await userEvent.clear(input);
    await userEvent.type(input, "3");
    expect(confirmSpy).toHaveBeenCalled();
    expect(screen.getByText(/未保存/)).toBeTruthy();      // 取消了，改动还在
  });

  test("后端报错时显示原文而不是白屏", async () => {
    vi.stubGlobal("fetch", routeFetch(() => json({ detail: "项目不存在" }, 404)));
    mount();
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("项目不存在"));
  });
});


describe("画布缩放与当前颜色", () => {
  beforeEach(() => vi.unstubAllGlobals());

  const canvasWidth = (c: HTMLElement) =>
    Number(c.querySelector("canvas")!.getAttribute("width"));

  /** 图纸是在渲染后的 effect 里灌进编辑器的，在那之前画布宽度还是 1（0 格 + 1）。
   *  量尺寸前必须等它真的有内容，否则测试会随时序抖。 */
  const waitForGrid = (c: HTMLElement) =>
    waitFor(() => expect(canvasWidth(c)).toBeGreaterThan(1));

  test("默认跟随窗口自动适应", async () => {
    vi.stubGlobal("fetch", routeFetch());
    mount();
    await waitFor(() => screen.getByRole("button", { name: "适应" }));
    expect(screen.getByRole("button", { name: "适应" }).getAttribute("aria-pressed"))
      .toBe("true");
  });

  test("缩小会让画布变小，并脱离自动适应", async () => {
    vi.stubGlobal("fetch", routeFetch());
    const { container } = mount();
    await waitForGrid(container);
    const before = canvasWidth(container);

    await userEvent.click(screen.getByRole("button", { name: "缩小" }));

    expect(canvasWidth(container)).toBeLessThan(before);
    expect(screen.getByRole("button", { name: "适应" }).getAttribute("aria-pressed"))
      .toBe("false");
  });

  test("点「适应」回到自动尺寸", async () => {
    vi.stubGlobal("fetch", routeFetch());
    const { container } = mount();
    await waitForGrid(container);
    const fitted = canvasWidth(container);

    await userEvent.click(screen.getByRole("button", { name: "缩小" }));
    await userEvent.click(screen.getByRole("button", { name: "适应" }));

    expect(canvasWidth(container)).toBe(fitted);
    expect(screen.getByRole("button", { name: "适应" }).getAttribute("aria-pressed"))
      .toBe("true");
  });

  test("到最小档后「缩小」禁用，不会越界", async () => {
    vi.stubGlobal("fetch", routeFetch());
    const { container } = mount();
    await waitForGrid(container);

    for (let i = 0; i < 30; i++) {
      const btn = screen.getByRole("button", { name: "缩小" });
      if ((btn as HTMLButtonElement).disabled) break;
      await userEvent.click(btn);
    }
    expect(screen.getByRole("button", { name: "缩小" })).toHaveProperty("disabled", true);
    expect(canvasWidth(container)).toBeGreaterThan(0);
  });

  test("当前颜色跟着色板选择走", async () => {
    vi.stubGlobal("fetch", routeFetch());
    mount();
    await waitFor(() => screen.getByText("未选"));

    await userEvent.click(screen.getByRole("button", { name: "R10" }));
    expect(screen.queryByText("未选")).toBeNull();
    // 色板上的按钮是纯色块没有文字，画笔用的是哪个色号只能靠这里显示出来，
    // 不该逼用户去找那圈黄边
    expect(screen.getByText("R10")).toBeTruthy();
  });
});
