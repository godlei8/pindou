import { useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAuth } from "../hooks/useAuth";

/** 草莓——新手拼的第一张图基本都是它。11 格宽 × 12 格高。
 *
 *  这张图自己也得过我们的可拼性检查：全图 4-连通、没有孤立豆。
 *  （叶尖看着是三个点，但每一个下面都压着 r1 那一整排，连着的。）
 */
const SPRITE = [
  "...G.G.G...",
  "..GGGGGGG..",
  "..RRRRRRR..",
  ".RRRYRRRYR.",
  "RRRRRRRRRRR",
  "RRYRRRRRYRR",
  ".RRRRYRRRR.",
  "..RRRRRRR..",
  "..RYRRRYR..",
  "...RRRRR...",
  "....RRR....",
  ".....R.....",
];

/** 真实 MARD 色号——页面配色就是产品的材料。 */
const BEAD: Record<string, { hex: string; code: string }> = {
  R: { hex: "#FC3D45", code: "F2" },   // 草莓红
  G: { hex: "#00BD35", code: "B5" },   // 叶绿
  Y: { hex: "#FFDB4D", code: "R10" },  // 籽。真草莓的籽就是黄的，在红底上也看得见
};

function Sprite({ fused }: { fused: boolean }) {
  return (
    <div className={`sprite${fused ? " is-fused" : ""}`} aria-hidden="true">
      {SPRITE.map((row, r) => (
        <div className="sprite-row" key={r}>
          {[...row].map((ch, c) => {
            const bead = BEAD[ch];
            return (
              <span
                key={c}
                className={bead ? "bead" : "bead is-empty"}
                style={bead
                  ? { "--bead": bead.hex } as React.CSSProperties
                  : undefined}
              />
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function LoginPage() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [params] = useSearchParams();
  // 邀请链接 /register?code=XXXX：直接进注册，邀请码填好
  const linkCode = (params.get("code") ?? "").trim();
  const [mode, setMode] = useState<"login" | "register">(
    pathname === "/register" || linkCode ? "register" : "login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [inviteCode, setInviteCode] = useState(linkCode);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [fused, setFused] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (mode === "login") await login(username, password);
      else await register(username, password, inviteCode);
      // 成功了就「熨」一下：环闭合、边缘熔连——这一步正是拼豆成败的落点
      setFused(true);
      await new Promise((r) => setTimeout(r, 620));
      navigate("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <div className="auth-card">
        <Sprite fused={fused} />

        <h1 className="auth-title">馨豆</h1>
        <p className="auth-sub">拼豆图纸生成 · 把图片变成能拼的图纸</p>

        <form onSubmit={submit} className="auth-form">
          <label htmlFor="username">用户名</label>
          <input id="username" value={username} onChange={(e) => setUsername(e.target.value)}
                 autoComplete="username" spellCheck={false} />

          <label htmlFor="password">密码</label>
          <input id="password" type="password" value={password}
                 onChange={(e) => setPassword(e.target.value)}
                 autoComplete={mode === "login" ? "current-password" : "new-password"} />

          {mode === "register" && (
            <>
              <label htmlFor="invite">邀请码</label>
              <input id="invite" value={inviteCode} spellCheck={false}
                     onChange={(e) => setInviteCode(e.target.value)} />
              <p className="auth-hint">{linkCode && inviteCode === linkCode
                ? "已从邀请链接填好，设个用户名和密码就行"
                : "找已经在用的人要一个"}</p>
            </>
          )}

          {error && <p role="alert" className="auth-error">{error}</p>}

          <button type="submit" className="auth-submit" disabled={busy}>
            {mode === "login" ? "登录" : "注册"}
          </button>
        </form>

        <button type="button" className="auth-toggle"
                onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
          {mode === "login" ? "没有账号？去注册" : "已有账号？去登录"}
        </button>

        <p className="auth-credit">
          配色取自 MARD 真实色号 <b>F2</b> <b>B5</b> <b>R10</b>
        </p>
      </div>
    </main>
  );
}
