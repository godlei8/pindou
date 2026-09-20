import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { ProjectsPage } from "../src/pages/ProjectsPage";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const PROJECTS = [
  {
    id: "p1", name: "小新", created_at: "2026-09-20T00:00:00Z",
    patterns: [
      { id: "pat2", origin: "edited", parent_id: "pat1",
        created_at: "2026-09-20T01:00:00Z", score: 92.5, n_colors: 8 },
      { id: "pat1", origin: "generated", parent_id: null,
        created_at: "2026-09-20T00:30:00Z", score: 86, n_colors: 9 },
    ],
  },
  { id: "p2", name: "空项目", created_at: "2026-09-19T00:00:00Z", patterns: [] },
];

function mount() {
  return render(<MemoryRouter><ProjectsPage /></MemoryRouter>);
}

describe("ProjectsPage", () => {
  beforeEach(() => vi.unstubAllGlobals());

  test("列出项目、版本数与最新评分", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(PROJECTS)));
    mount();
    await waitFor(() => screen.getByText("小新"));
    expect(screen.getByText("空项目")).toBeTruthy();
    expect(screen.getByText(/2 个版本/)).toBeTruthy();
    expect(screen.getByText(/92\.5/)).toBeTruthy();
  });

  test("空列表给出引导而不是白屏", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json([])));
    mount();
    await waitFor(() => expect(screen.getByText(/还没有项目/)).toBeTruthy());
  });

  test("上传后刷新列表", async () => {
    const fetchMock = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "POST") return json(PROJECTS[0], 201);
      return json(PROJECTS);
    });
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByLabelText("图片"));

    await userEvent.upload(
      screen.getByLabelText("图片") as HTMLInputElement,
      new File([new Uint8Array([1, 2, 3])], "a.png", { type: "image/png" }),
    );
    await userEvent.type(screen.getByLabelText("项目名"), "新项目");
    await userEvent.click(screen.getByRole("button", { name: /上传/ }));

    await waitFor(() => {
      const posts = fetchMock.mock.calls.filter((c) => c[1]?.method === "POST");
      expect(posts.length).toBe(1);
      expect(posts[0][1]!.body).toBeInstanceOf(FormData);
    });
  });

  test("没选文件时上传按钮不可用", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json([])));
    mount();
    await waitFor(() => screen.getByLabelText("图片"));
    expect((screen.getByRole("button", { name: /上传/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  test("accept 属性挡掉不支持的类型（浏览器层，请求都不会发出）", async () => {
    const fetchMock = vi.fn(async () => json([]));
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByLabelText("图片"));
    const input = screen.getByLabelText("图片") as HTMLInputElement;
    await userEvent.upload(input, new File([new Uint8Array([1])], "a.gif", { type: "image/gif" }));
    expect(input.files?.length ?? 0).toBe(0);
    expect((screen.getByRole("button", { name: /上传/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  test("上传失败时显示后端原文", async () => {
    // 真实的后端拒绝场景：扩展名与 MIME 都合法、字节不是图片（后端 Image.verify 拦下）
    vi.stubGlobal("fetch", vi.fn(async (_u: RequestInfo | URL, init?: RequestInit) =>
      init?.method === "POST"
        ? json({ detail: "无法识别的图片格式：cannot identify image file" }, 400)
        : json([])));
    mount();
    await waitFor(() => screen.getByLabelText("图片"));
    await userEvent.upload(
      screen.getByLabelText("图片") as HTMLInputElement,
      new File([new Uint8Array([1, 2, 3])], "fake.png", { type: "image/png" }),
    );
    await userEvent.click(screen.getByRole("button", { name: /上传/ }));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("无法识别的图片格式"));
  });
});
