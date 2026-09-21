import { useState } from "react";
import type { FormEvent } from "react";

import { api } from "../../api/client";
import type { AdminInvite, InviteState, User } from "../../api/types";
import { Loading, errorText, fmtTime, useAdminData } from "./shared";

const STATE: Record<InviteState, string> = { active: "可用", used_up: "已用完", expired: "已作废" };

export function InvitesSection(_: { me: User }) {
  const { data, setData, error, reload } = useAdminData(api.admin.invites);
  const [count, setCount] = useState(1);
  const [maxUses, setMaxUses] = useState(1);
  const [days, setDays] = useState("");        // 空 = 永久有效
  const [fresh, setFresh] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  if (!data) return <Loading error={error} onRetry={reload} />;

  const create = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setActionError(null);
    try {
      const made = await api.admin.createInvites({
        count, max_uses: maxUses, expires_days: days ? Number(days) : null,
      });
      setFresh(made.map((c) => c.code));
      setData([...made, ...data]);
    } catch (err) {
      setActionError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (c: AdminInvite) => {
    if (!window.confirm(`作废邀请码 ${c.code}？作废后不能再用它注册，已注册的账号不受影响。`)) return;
    try {
      const next = await api.admin.revokeInvite(c.code);
      setData(data.map((x) => (x.code === c.code ? next : x)));
    } catch (err) {
      setActionError(errorText(err));
    }
  };

  const copyFresh = () => void navigator.clipboard?.writeText(fresh.join("\n"));

  return (
    <>
      <form className="admin-form" onSubmit={create}>
        <label>生成<input type="number" min={1} max={20} value={count}
                         onChange={(e) => setCount(Number(e.target.value))} />个</label>
        <label>每个能用<input type="number" min={1} max={1000} value={maxUses}
                          onChange={(e) => setMaxUses(Number(e.target.value))} />次</label>
        <label><input type="number" min={1} max={365} value={days} placeholder="永久"
                      onChange={(e) => setDays(e.target.value)} />天后过期</label>
        <button type="submit" className="primary" disabled={busy}>生成邀请码</button>
      </form>
      {actionError && <p className="error" role="alert">{actionError}</p>}

      {fresh.length > 0 && (
        <div className="admin-fresh" role="status">
          <p>新生成 {fresh.length} 个，发给要邀请的人：</p>
          <code>{fresh.join("  ")}</code>
          <button type="button" onClick={copyFresh}>复制</button>
        </div>
      )}

      <div className="admin-scroll">
        <table className="admin-table">
          <thead>
            <tr><th>邀请码</th><th className="num">已用</th><th>过期时间</th><th>创建</th>
                <th>状态</th><th /></tr>
          </thead>
          <tbody>
            {data.map((c) => (
              <tr key={c.code} className={c.state === "active" ? undefined : "dim"}>
                <td><code>{c.code}</code></td>
                <td className="num">{c.used_count}/{c.max_uses}</td>
                <td>{c.expires_at ? fmtTime(c.expires_at) : "永久"}</td>
                <td>{fmtTime(c.created_at)}</td>
                <td><span className={`status status-${c.state}`}>{STATE[c.state]}</span></td>
                <td>
                  {c.state !== "expired" && (
                    <button type="button" className="small" onClick={() => void revoke(c)}>作废</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
