import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { ProjectsPage } from "../src/pages/ProjectsPage";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const PROJECTS = [
  {
    id: "p1", name: "小新", created_at: "2026-09-20T00:00:00Z",
    patterns: [
      { id: "pat2", origin: "edited", parent_id: "pat1", ai_render_id: null,
        created_at: "2026-09-20T01:00:00Z", score: 92.5, n_colors: 8, rows: 44, cols: 58 },
      { id: "pat1", origin: "generated", parent_id: null, ai_render_id: null,
        created_at: "2026-09-20T00:30:00Z", score: 86, n_colors: 9 },
    ],
  },
  { id: "p2", name: "空项目", created_at: "2026-09-19T00:00:00Z", patterns: [] },
];

const CREATED = { id: "new1", name: "x", created_at: "2026-09-21T00:00:00Z", patterns: [] };

/** 列表 + 建项目 + 改名。建项目时把请求体记下来，看默认名对不对。 */
function makeFetch(list: unknown[] = PROJECTS, createStatus = 201) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (url.endsWith("/api/projects") && method === "POST") {
      return createStatus === 201 ? json(CREATED, 201)
                                  : json({ detail: "图片格式无法识别" }, createStatus);
    }
    if (url.endsWith("/api/projects") && method === "GET") return json(list);
    if (method === "PATCH") {
      const body = JSON.parse(String(init!.body));
      return json({ ...PROJECTS[0], name: body.name });
    }
    if (url.startsWith("/samples/")) return new Response(new Blob(["png"], { type: "image/png" }));
    return json({ detail: `未 mock：${method} ${url}` }, 500);
  });
}

/** 挂在路由里，才能验证"投完图直接跳到工作台"。 */
function mount() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<ProjectsPage />} />
        <Route path="/p/:projectId" element={<p>工作台已打开</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

const png = (name = "avatar.jpg", type = "image/png", size = 10) =>
  new File([new Uint8Array(size)], name, { type });

const createdName = (fetchMock: ReturnType<typeof makeFetch>) => {
  const call = fetchMock.mock.calls.find(
    (c) => String(c[0]).endsWith("/api/projects") && c[1]?.method === "POST");
  return (call![1]!.body as FormData).get("name");
};

describe("首页：进站就能投图", () => {
  beforeEach(() => vi.unstubAllGlobals());

  test("首页有自己的介绍，不是一上来就一个上传框", async () => {
    vi.stubGlobal("fetch", makeFetch([]));
    mount();
    await waitFor(() => screen.getByRole("heading", { level: 1 }));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("拼得出来的图纸");
    // 介绍里的示例是真实输出，数字来自生成脚本，图上的标注和正文对得上
    expect(screen.getByRole("img", { name: /示例：一朵蘑菇/ })).toBeTruthy();
  });

  test("没有项目时，网格里是「新图纸」加三张示例卡片", async () => {
    vi.stubGlobal("fetch", makeFetch([]));
    mount();
    await waitFor(() => screen.getByText("从这里开始"));
    const tiles = within(screen.getByRole("list", { name: "图纸" })).getAllByRole("listitem");
    expect(tiles).toHaveLength(4);
    expect(screen.getByRole("button", { name: /开始一张新图纸/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /示例图「草莓」/ })).toBeTruthy();
  });

  test("有项目时「新图纸」仍是第一格，示例让位给最近的图纸", async () => {
    vi.stubGlobal("fetch", makeFetch());
    mount();
    await waitFor(() => screen.getByText("最近的图纸"));
    const first = within(screen.getByRole("list", { name: "图纸" })).getAllByRole("listitem")[0];
    expect(first.textContent).toContain("新图纸");
    expect(screen.queryByRole("button", { name: /示例图/ })).toBeNull();
    expect(screen.getByText("小新")).toBeTruthy();
    expect(screen.getByText(/2 个版本/)).toBeTruthy();
    expect(screen.getByText(/可拼性 92\.5/)).toBeTruthy();
    expect(screen.getByText(/58×44 格/)).toBeTruthy();   // 卡片上写全两边
  });

  test("缩略图用最新图纸；还没出图的项目退回原图", async () => {
    vi.stubGlobal("fetch", makeFetch());
    const { container } = mount();
    await waitFor(() => screen.getByText("小新"));
    const srcs = [...container.querySelectorAll(".thumb img")].map((i) => i.getAttribute("src"));
    expect(srcs).toContain("/api/patterns/pat2/thumb");
    expect(srcs).toContain("/api/projects/p2/source");
  });

  test("选一张图：不问名字，建完项目直接进工作台", async () => {
    const fetchMock = makeFetch();
    vi.stubGlobal("fetch", fetchMock);
    const { container } = mount();
    await waitFor(() => screen.getByRole("button", { name: /开始一张新图纸/ }));

    await userEvent.upload(container.querySelector('input[type="file"]')!, png("avatar.jpg"));

    await waitFor(() => screen.getByText("工作台已打开"));
    expect(createdName(fetchMock)).toBe("avatar");      // 去掉扩展名
  });

  test("粘贴截图也能开始，默认名能看出是截图", async () => {
    const fetchMock = makeFetch();
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByRole("button", { name: /开始一张新图纸/ }));

    fireEvent.paste(window, { clipboardData: { files: [png("image.png")] } });

    await waitFor(() => screen.getByText("工作台已打开"));
    expect(String(createdName(fetchMock))).toMatch(/^截图 \d\d-\d\d \d\d:\d\d$/);
  });

  test("在输入框里粘贴不会被抢去上传", async () => {
    const fetchMock = makeFetch();
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByRole("button", { name: /重命名「小新」/ }));
    await userEvent.click(screen.getByRole("button", { name: /重命名「小新」/ }));

    fireEvent.paste(screen.getByLabelText("项目名"), { clipboardData: { files: [png()] } });

    expect(fetchMock.mock.calls.some((c) => c[1]?.method === "POST")).toBe(false);
  });

  test("把文件拖到页面上出现落点提示，松手就开始", async () => {
    const fetchMock = makeFetch();
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByRole("button", { name: /开始一张新图纸/ }));

    const dt = { types: ["Files"], files: [png("drag.png")] };
    fireEvent.dragEnter(window, { dataTransfer: dt });
    expect(screen.getByText("松手就开始出图")).toBeTruthy();

    fireEvent.drop(window, { dataTransfer: dt });
    expect(screen.queryByText("松手就开始出图")).toBeNull();
    await waitFor(() => screen.getByText("工作台已打开"));
    expect(createdName(fetchMock)).toBe("drag");
  });

  test("拖的是文字不是文件时，不弹落点提示", async () => {
    vi.stubGlobal("fetch", makeFetch());
    mount();
    await waitFor(() => screen.getByRole("button", { name: /开始一张新图纸/ }));
    fireEvent.dragEnter(window, { dataTransfer: { types: ["text/plain"], files: [] } });
    expect(screen.queryByText("松手就开始出图")).toBeNull();
  });

  test("不支持的格式当场挡下，请求都不发", async () => {
    const fetchMock = makeFetch();
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByRole("button", { name: /开始一张新图纸/ }));

    fireEvent.paste(window, { clipboardData: { files: [png("a.gif", "image/gif")] } });

    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/PNG、JPG 或 WebP/));
    expect(fetchMock.mock.calls.some((c) => c[1]?.method === "POST")).toBe(false);
  });

  test("超过 20 MB 当场挡下，并说出实际大小", async () => {
    const fetchMock = makeFetch();
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByRole("button", { name: /开始一张新图纸/ }));

    fireEvent.paste(window, { clipboardData: { files: [png("big.png", "image/png", 21 * 1024 * 1024)] } });

    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/21\.0 MB.*20 MB/));
    expect(fetchMock.mock.calls.some((c) => c[1]?.method === "POST")).toBe(false);
  });

  test("后端拒绝时显示原文，投图区恢复可用", async () => {
    vi.stubGlobal("fetch", makeFetch(PROJECTS, 400));
    const { container } = mount();
    await waitFor(() => screen.getByRole("button", { name: /开始一张新图纸/ }));

    await userEvent.upload(container.querySelector('input[type="file"]')!, png());

    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("图片格式无法识别"));
    expect(screen.getByText("新图纸")).toBeTruthy();            // 不卡在"正在上传…"
  });

  test("点示例图直接开始，名字标明是示例", async () => {
    const fetchMock = makeFetch([]);
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByRole("button", { name: /示例图「小猫」/ }));

    await userEvent.click(screen.getByRole("button", { name: /示例图「小猫」/ }));

    await waitFor(() => screen.getByText("工作台已打开"));
    expect(createdName(fetchMock)).toBe("示例 · 小猫");
  });
});

describe("首页：改名", () => {
  beforeEach(() => vi.unstubAllGlobals());

  test("改名后卡片立刻更新", async () => {
    const fetchMock = makeFetch();
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByRole("button", { name: /重命名「小新」/ }));

    await userEvent.click(screen.getByRole("button", { name: /重命名「小新」/ }));
    const input = screen.getByLabelText("项目名");
    await userEvent.clear(input);
    await userEvent.type(input, "小熊猫{Enter}");

    await waitFor(() => screen.getByText("小熊猫"));
    const patch = fetchMock.mock.calls.find((c) => c[1]?.method === "PATCH")!;
    expect(String(patch[0])).toBe("/api/projects/p1");
    expect(JSON.parse(String(patch[1]!.body))).toEqual({ name: "小熊猫" });
  });

  test("Esc 取消改名，不发请求", async () => {
    const fetchMock = makeFetch();
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByRole("button", { name: /重命名「小新」/ }));

    await userEvent.click(screen.getByRole("button", { name: /重命名「小新」/ }));
    await userEvent.type(screen.getByLabelText("项目名"), "乱改{Escape}");

    expect(screen.getByText("小新")).toBeTruthy();
    expect(fetchMock.mock.calls.some((c) => c[1]?.method === "PATCH")).toBe(false);
  });

  test("进入改名时全选——直接打字就是替换，不会追加到旧名后面", async () => {
    vi.stubGlobal("fetch", makeFetch());
    mount();
    await waitFor(() => screen.getByRole("button", { name: /重命名「小新」/ }));
    await userEvent.click(screen.getByRole("button", { name: /重命名「小新」/ }));

    const input = screen.getByLabelText("项目名") as HTMLInputElement;
    await waitFor(() => expect([input.selectionStart, input.selectionEnd]).toEqual([0, 2]));
  });

  test("拼音输入法选字时的回车是确认候选字，不能提交", async () => {
    const fetchMock = makeFetch();
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByRole("button", { name: /重命名「小新」/ }));
    await userEvent.click(screen.getByRole("button", { name: /重命名「小新」/ }));
    const input = screen.getByLabelText("项目名");
    fireEvent.change(input, { target: { value: "hongmogu" } });

    fireEvent.keyDown(input, { key: "Enter", isComposing: true });

    expect(fetchMock.mock.calls.some((c) => c[1]?.method === "PATCH")).toBe(false);
    expect(screen.getByLabelText("项目名")).toBeTruthy();       // 还在编辑
  });

  test("拼音输入法选字时的 Esc 是取消拼音，不能取消改名", async () => {
    vi.stubGlobal("fetch", makeFetch());
    mount();
    await waitFor(() => screen.getByRole("button", { name: /重命名「小新」/ }));
    await userEvent.click(screen.getByRole("button", { name: /重命名「小新」/ }));

    fireEvent.keyDown(screen.getByLabelText("项目名"), { key: "Escape", isComposing: true });

    expect(screen.getByLabelText("项目名")).toBeTruthy();
  });

  test("回车保存后即使再补一次失焦，也只发一次请求", async () => {
    const fetchMock = makeFetch();
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByRole("button", { name: /重命名「小新」/ }));
    await userEvent.click(screen.getByRole("button", { name: /重命名「小新」/ }));
    const input = screen.getByLabelText("项目名");
    fireEvent.change(input, { target: { value: "小熊猫" } });

    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.blur(input);

    await waitFor(() => screen.getByText("小熊猫"));
    expect(fetchMock.mock.calls.filter((c) => c[1]?.method === "PATCH")).toHaveLength(1);
  });
});

