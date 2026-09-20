import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import { AuthProvider } from "../src/hooks/useAuth";
import { LoginPage } from "../src/pages/LoginPage";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

const USER = { id: "u1", username: "amy", ai_quota: 5, ai_used: 0, is_admin: false };

function mount() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => vi.unstubAllGlobals());

  test("未登录时 /auth/me 的 401 不显示为错误", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "未登录" }, 401)));
    mount();
    await waitFor(() => expect(screen.getByRole("button", { name: /登录/ })).toBeTruthy());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("登录成功后调用 /auth/login", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) =>
      String(url).includes("/auth/me") ? json({ detail: "未登录" }, 401) : json(USER));
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByLabelText("用户名"));

    await userEvent.type(screen.getByLabelText("用户名"), "amy");
    await userEvent.type(screen.getByLabelText("密码"), "pw12345678");
    await userEvent.click(screen.getByRole("button", { name: /^登录$/ }));

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map((c) => String(c[0]));
      expect(urls).toContain("/api/auth/login");
    });
  });

  test("后端的错误原文直接展示给用户", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) =>
      String(url).includes("/auth/me")
        ? json({ detail: "未登录" }, 401)
        : json({ detail: "用户名或密码错误" }, 401)));
    mount();
    await waitFor(() => screen.getByLabelText("用户名"));

    await userEvent.type(screen.getByLabelText("用户名"), "amy");
    await userEvent.type(screen.getByLabelText("密码"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /^登录$/ }));

    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toContain("用户名或密码错误"));
  });

  test("切到注册模式会多出邀请码输入框", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "未登录" }, 401)));
    mount();
    await waitFor(() => screen.getByLabelText("用户名"));
    expect(screen.queryByLabelText("邀请码")).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /没有账号/ }));
    expect(screen.getByLabelText("邀请码")).toBeTruthy();
  });

  test("注册把邀请码发给后端", async () => {
    const fetchMock = vi.fn(async (url: RequestInfo | URL, _init?: RequestInit) =>
      String(url).includes("/auth/me") ? json({ detail: "未登录" }, 401) : json(USER, 201));
    vi.stubGlobal("fetch", fetchMock);
    mount();
    await waitFor(() => screen.getByLabelText("用户名"));
    await userEvent.click(screen.getByRole("button", { name: /没有账号/ }));

    await userEvent.type(screen.getByLabelText("用户名"), "newbie");
    await userEvent.type(screen.getByLabelText("密码"), "pw12345678");
    await userEvent.type(screen.getByLabelText("邀请码"), "OPEN2026");
    await userEvent.click(screen.getByRole("button", { name: /^注册$/ }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find((c) => String(c[0]).includes("/auth/register"));
      expect(call).toBeTruthy();
      expect(JSON.parse(String(call![1]!.body)).invite_code).toBe("OPEN2026");
    });
  });
});
