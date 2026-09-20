import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../hooks/useAuth";

export function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "login") await login(username, password);
      else await register(username, password, inviteCode);
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <h1>拼豆图纸生成</h1>
      <form onSubmit={submit}>
        <label htmlFor="username">用户名</label>
        <input id="username" value={username} onChange={(e) => setUsername(e.target.value)}
               autoComplete="username" />

        <label htmlFor="password">密码</label>
        <input id="password" type="password" value={password}
               onChange={(e) => setPassword(e.target.value)}
               autoComplete={mode === "login" ? "current-password" : "new-password"} />

        {mode === "register" && (
          <>
            <label htmlFor="invite">邀请码</label>
            <input id="invite" value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} />
          </>
        )}

        {error && <p role="alert" className="error">{error}</p>}

        <button type="submit" disabled={busy}>{mode === "login" ? "登录" : "注册"}</button>
      </form>

      <button type="button" className="link"
              onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
        {mode === "login" ? "没有账号？去注册" : "已有账号？去登录"}
      </button>
    </main>
  );
}
