import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../hooks/useAuth";

/** 管理后台独立的登录页。和用户登录页分开：没有注册，只放管理员进来，登录后直接进后台。 */
export function AdminLoginPage() {
  const { adminLogin } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await adminLogin(username, password);
      navigate("/admin", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
      setBusy(false);
    }
  }

  return (
    <main className="auth auth-admin">
      <div className="auth-card">
        <p className="auth-admin-badge" aria-hidden="true">ADMIN</p>
        <h1 className="auth-title">管理后台</h1>
        <p className="auth-sub">拼豆图纸生成 · 仅限管理员</p>

        <form onSubmit={submit} className="auth-form">
          <label htmlFor="admin-username">管理员账号</label>
          <input id="admin-username" value={username} onChange={(e) => setUsername(e.target.value)}
                 autoComplete="username" spellCheck={false} />

          <label htmlFor="admin-password">密码</label>
          <input id="admin-password" type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />

          {error && <p role="alert" className="auth-error">{error}</p>}

          <button type="submit" className="auth-submit" disabled={busy}>登录后台</button>
        </form>

        <Link to="/login" className="auth-admin-back">← 回到拼豆</Link>
      </div>
    </main>
  );
}
