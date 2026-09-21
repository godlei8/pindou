import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { App } from "../src/App";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const USER = { id: "u1", username: "amy", ai_quota: 5, ai_used: 0, is_admin: false };
const COLORS = [
  { index: 0, code: "H2", name: "H2", hex: "#FFFFFF", role: null, confidence: "agree" },
  { index: 1, code: "R10", name: "R10", hex: "#FFDD00", role: null, confidence: "agree" },
];
const PATTERN = {
  id: "pat1", project_id: "p1", parent_id: null, origin: "generated", ai_render_id: null,
  params: { grid_long_side: 58, max_colors: 24, smoothness: 2, dither: false,
            palette_id: "mard", small_color_threshold: 10, lock_outlines: true },
  grid: [[0, 1], [1, 0]], color_stats: { "0": 2, "1": 2 },
  buildability: { score: 88, confetti_pct: 1, n_components: 1, metrics: {}, issues: [] },
  materials: [], palette_id: "mard", created_at: "2026-09-20T00:00:00Z",
};
const PROJECT = {
  id: "p1", name: "小熊猫", created_at: "2026-09-20T00:00:00Z",
  patterns: [{ id: "pat1", origin: "generated", parent_id: null, ai_render_id: null,
               created_at: "2026-09-20T00:00:00Z", score: 88, n_colors: 2 }],
};

function stubApi() {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes("/auth/me")) return json(USER);
    if (url.includes("/palettes/mard/colors")) return json(COLORS);
    if (url.includes("/suggest-sizes")) return json([]);
    if (url.includes("/style-presets")) return json([]);
    if (url.includes("/api/patterns/pat1")) return json(PATTERN);
    if (url.endsWith("/api/projects/p1")) return json(PROJECT);
    if (url.endsWith("/api/projects")) return json([PROJECT]);
    return json({ detail: `未 mock：${url}` }, 500);
  }));
}

function mountAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
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

describe("工作台的返回首页", () => {
  beforeEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  test("工作台顶栏显示「返回首页」和项目名", async () => {
    stubApi();
    mountAt("/p/p1");
    await waitFor(() => screen.getByRole("button", { name: "← 返回首页" }));
    // 工作台里原来看不出"我在改哪张"
    expect(screen.getByText("小熊猫", { selector: ".crumb" })).toBeTruthy();
  });

  test("首页不显示返回按钮", async () => {
    stubApi();
    mountAt("/");
    await waitFor(() => screen.getByText("最近的图纸"));
    expect(screen.queryByRole("button", { name: "← 返回首页" })).toBeNull();
  });

  test("点返回回到首页", async () => {
    stubApi();
    mountAt("/p/p1");
    await waitFor(() => screen.getByRole("button", { name: "← 返回首页" }));

    await userEvent.click(screen.getByRole("button", { name: "← 返回首页" }));

    await waitFor(() => screen.getByText("最近的图纸"));
  });

  test("有未保存的改动时先确认，取消就留在工作台", async () => {
    stubApi();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { container } = mountAt("/p/p1");
    await waitFor(() => screen.getByRole("button", { name: "R10" }));
    await paintOneCell(container);
    await waitFor(() => screen.getByText("有未保存的改动"));

    await userEvent.click(screen.getByRole("button", { name: "← 返回首页" }));

    expect(confirm).toHaveBeenCalled();
    expect(screen.getByText("有未保存的改动")).toBeTruthy();       // 改动还在
    expect(screen.queryByText("最近的图纸")).toBeNull();
  });

  test("有未保存的改动时确认离开，才回首页", async () => {
    stubApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const { container } = mountAt("/p/p1");
    await waitFor(() => screen.getByRole("button", { name: "R10" }));
    await paintOneCell(container);

    await userEvent.click(screen.getByRole("button", { name: "← 返回首页" }));

    await waitFor(() => screen.getByText("最近的图纸"));
  });

  test("没有改动时直接返回，不弹确认", async () => {
    stubApi();
    const confirm = vi.spyOn(window, "confirm");
    mountAt("/p/p1");
    await waitFor(() => screen.getByRole("button", { name: "← 返回首页" }));

    await userEvent.click(screen.getByRole("button", { name: "← 返回首页" }));

    await waitFor(() => screen.getByText("最近的图纸"));
    expect(confirm).not.toHaveBeenCalled();
  });
});
