import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { App } from "../src/App";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const ADMIN = { id: "u1", username: "boss", ai_quota: 5, ai_used: 0, is_admin: true };
const PLAIN = { ...ADMIN, is_admin: false };

const USERS = [
  { id: "u1", username: "boss", ai_quota: 5, ai_used: 0, is_admin: true, is_disabled: false,
    created_at: "2026-09-20T00:00:00Z", projects: 2 },
  { id: "u2", username: "amy", ai_quota: 3, ai_used: 1, is_admin: false, is_disabled: false,
    created_at: "2026-09-20T00:00:00Z", projects: 1 },
];

type Call = { url: string; method: string; body: unknown };

function stub(me = ADMIN, overrides: Record<string, (c: Call) => Response> = {}) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const call = { url, method, body: init?.body ? JSON.parse(String(init.body)) : null };
    calls.push(call);
    for (const [k, fn] of Object.entries(overrides)) if (url.includes(k)) return fn(call);
    if (url.includes("/auth/me")) return json(me);
    if (url.endsWith("/api/projects")) return json([]);
    if (url.endsWith("/admin/users")) return json(USERS);
    if (url.endsWith("/admin/feedback")) return json([]);
    return json({ detail: `未 mock：${url}` }, 500);
  }));
  return calls;
}

const mountAt = (path: string) =>
  render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

describe("管理后台", () => {
  beforeEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  test("普通用户看不到入口，直接访问也被送回首页", async () => {
    stub(PLAIN);
    mountAt("/admin/users");
    await screen.findByText(/boss · AI 额度/);
    expect(screen.queryByRole("link", { name: "管理后台" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "管理后台" })).toBeNull();
  });

  test("管理员顶栏有入口，/admin 默认进实拼反馈", async () => {
    stub();
    mountAt("/");
    await userEvent.click(await screen.findByRole("link", { name: "管理后台" }));
    expect(await screen.findByRole("heading", { name: "实拼反馈" })).toBeTruthy();
    expect(screen.getByText(/还没有人提交实拼反馈/)).toBeTruthy();
  });

  test("加额度：发增量，表格换成服务器返回的值", async () => {
    const calls = stub(ADMIN, {
      "/admin/users/u2": (c) => json({ ...USERS[1], ai_quota: 3 + (c.body as { quota_delta: number }).quota_delta }),
    });
    mountAt("/admin/users");
    const input = await screen.findByLabelText("amy 额度调整数量");
    await userEvent.type(input, "10");
    const row = input.closest("tr")!;
    await userEvent.click(within(row).getByRole("button", { name: "加" }));
    await waitFor(() => expect(within(row).getByText("12/13")).toBeTruthy());
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ quota_delta: 10 });
  });

  test("不能停用自己、撤销自己的管理员", async () => {
    stub();
    mountAt("/admin/users");
    const me = (await screen.findByText("boss")).closest("tr")!;
    expect((within(me).getByRole("button", { name: "停用" }) as HTMLButtonElement).disabled).toBe(true);
    expect((within(me).getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
  });

  test("停用别人要确认，取消就不发请求", async () => {
    const calls = stub();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    mountAt("/admin/users");
    const amy = (await screen.findByText("amy")).closest("tr")!;
    await userEvent.click(within(amy).getByRole("button", { name: "停用" }));
    expect(calls.some((c) => c.method === "PATCH")).toBe(false);
  });

  test("后端报错（比如额度低于已用）显示出来", async () => {
    stub(ADMIN, {
      "/admin/users/u2": () => json({ detail: "总额度不能低于已用次数（已用 1）" }, 400),
    });
    mountAt("/admin/users");
    const input = await screen.findByLabelText("amy 额度调整数量");
    await userEvent.type(input, "5");
    await userEvent.click(within(input.closest("tr")!).getByRole("button", { name: "减" }));
    expect((await screen.findByRole("alert")).textContent).toContain("不能低于已用");
  });

  test("生成邀请码：新码醒目地列出来", async () => {
    const calls = stub(ADMIN, {
      "/admin/invites": (c) => c.method === "POST"
        ? json([{ code: "NEWCODE12345", max_uses: 2, used_count: 0, expires_at: null,
                  created_at: "2026-09-21T00:00:00Z", state: "active" }], 201)
        : json([]),
    });
    mountAt("/admin/invites");
    const uses = await screen.findByLabelText(/每个能用/);
    await userEvent.clear(uses);
    await userEvent.type(uses, "2");
    await userEvent.click(screen.getByRole("button", { name: "生成邀请码" }));
    expect((await screen.findByRole("status")).textContent).toContain("NEWCODE12345");
    expect(calls.find((c) => c.method === "POST")!.body)
      .toEqual({ count: 1, max_uses: 2, expires_days: null });
  });

  test("风格预设：没改不能保存，改了提示词保存后显示新版本", async () => {
    const P = { id: "s1", name: "平涂", prompt: "flat", params: {}, version: 1,
                sort_order: 10, is_active: true };
    const calls = stub(ADMIN, {
      "/admin/presets/s1": (c) => json({ ...P, ...(c.body as object), version: 2 }),
      "/admin/presets": () => json([P]),
    });
    mountAt("/admin/presets");
    const save = await screen.findByRole("button", { name: "保存" });
    expect((save as HTMLButtonElement).disabled).toBe(true);
    const prompt = screen.getAllByLabelText("提示词").at(-1)!;
    await userEvent.type(prompt, " art");
    await userEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(await screen.findByText("v2")).toBeTruthy();
    expect(calls.find((c) => c.method === "PATCH")!.body).toMatchObject({ prompt: "flat art" });
  });
});
