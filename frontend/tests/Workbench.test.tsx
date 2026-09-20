import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { WorkbenchPage } from "../src/pages/WorkbenchPage";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

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
  return render(
    <MemoryRouter initialEntries={["/p/p1"]}>
      <Routes><Route path="/p/:projectId" element={<WorkbenchPage />} /></Routes>
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
