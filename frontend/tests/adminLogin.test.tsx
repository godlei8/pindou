import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { App } from "../src/App";
import { inviteUrl } from "../src/lib/invite";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const ADMIN = { id: "u1", username: "admin", ai_quota: 0, ai_used: 0, is_admin: true };

type Call = { url: string; method: string; body: unknown };

/** 一开始没登录；adminLogin 成功后 /auth/me 返回管理员。 */
function stub(adminLoginResult: Response | (() => Response) = () => json(ADMIN)) {
  const calls: Call[] = [];
  let me: unknown = null;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (url.includes("/auth/me")) return me ? json(me) : json({ detail: "未登录" }, 401);
    if (url.includes("/auth/admin-login")) {
      const r = typeof adminLoginResult === "function" ? adminLoginResult() : adminLoginResult;
      if (r.ok) me = ADMIN;
      return r;
    }
    if (url.endsWith("/admin/feedback")) return json([]);
    if (url.endsWith("/admin/invites")) {
      return json([{ code: "ABCD1234EFGH", max_uses: 1, used_count: 0, expires_at: null,
                     created_at: "2026-09-21T00:00:00Z", state: "active" }]);
    }
    return json({ detail: `未 mock：${url}` }, 500);
  }));
  return calls;
}

const mountAt = (path: string) =>
  render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);

describe("后台独立登录", () => {
  beforeEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  test("没登录打开后台，进的是后台自己的登录页，不是用户登录页", async () => {
    stub();
    mountAt("/admin/users");
    expect(await screen.findByRole("heading", { name: "管理后台" })).toBeTruthy();
    expect(screen.getByLabelText("管理员账号")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /去注册/ })).toBeNull();   // 后台没有注册
  });

  test("管理员登录后直接进后台", async () => {
    const calls = stub();
    mountAt("/admin/login");
    await userEvent.type(await screen.findByLabelText("管理员账号"), "admin");
    await userEvent.type(screen.getByLabelText("密码"), "secret12");
    await userEvent.click(screen.getByRole("button", { name: "登录后台" }));
    expect(await screen.findByRole("navigation", { name: "管理后台" })).toBeTruthy();
    expect(calls.find((c) => c.url.includes("/auth/admin-login"))!.body)
      .toEqual({ username: "admin", password: "secret12" });
    expect(calls.some((c) => c.url.endsWith("/auth/login"))).toBe(false);
  });

  test("普通账号在后台登录页被拒，提示原因", async () => {
    stub(() => json({ detail: "这个账号不是管理员" }, 403));
    mountAt("/admin/login");
    await userEvent.type(await screen.findByLabelText("管理员账号"), "amy");
    await userEvent.type(screen.getByLabelText("密码"), "pw12345678");
    await userEvent.click(screen.getByRole("button", { name: "登录后台" }));
    expect((await screen.findByRole("alert")).textContent).toContain("不是管理员");
    expect(screen.queryByRole("navigation", { name: "管理后台" })).toBeNull();
  });

  test("用户登录页不出现后台入口", async () => {
    stub();
    mountAt("/login");
    await screen.findByRole("button", { name: "登录" });
    expect(screen.queryByText(/管理/)).toBeNull();
  });
});

describe("邀请链接", () => {
  beforeEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });

  test("链接格式：/register?code=", () => {
    expect(inviteUrl("AB CD", "https://pindou.godlei8.top"))
      .toBe("https://pindou.godlei8.top/register?code=AB%20CD");
  });

  test("打开邀请链接直接是注册，邀请码已填好", async () => {
    stub();
    mountAt("/register?code=ABCD1234EFGH");
    expect(await screen.findByRole("button", { name: "注册" })).toBeTruthy();
    expect((screen.getByLabelText("邀请码") as HTMLInputElement).value).toBe("ABCD1234EFGH");
    expect(screen.getByText(/已从邀请链接填好/)).toBeTruthy();
  });

  test("普通登录页不带邀请码，还是登录", async () => {
    stub();
    mountAt("/login");
    expect(await screen.findByRole("button", { name: "登录" })).toBeTruthy();
    expect(screen.queryByLabelText("邀请码")).toBeNull();
  });

  test("后台一键复制注册链接", async () => {
    stub();
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    mountAt("/admin/login");
    await userEvent.type(await screen.findByLabelText("管理员账号"), "admin");
    await userEvent.type(screen.getByLabelText("密码"), "secret12");
    await userEvent.click(screen.getByRole("button", { name: "登录后台" }));
    await userEvent.click(await screen.findByRole("link", { name: "邀请码" }));
    await userEvent.click(await screen.findByRole("button", { name: "复制 ABCD1234EFGH 的注册链接" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(inviteUrl("ABCD1234EFGH")));
    expect(await screen.findByRole("button", { name: "复制 ABCD1234EFGH 的注册链接" }))
      .toHaveProperty("textContent", "已复制");
  });
});
