import { useState } from "react";

import { api } from "../../api/client";
import type { AdminUser, User } from "../../api/types";
import { Loading, errorText, fmtTime, useAdminData } from "./shared";

export function UsersSection({ me }: { me: User }) {
  const { data, setData, error, reload } = useAdminData(api.admin.users);
  const [deltas, setDeltas] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);

  if (!data) return <Loading error={error} onRetry={reload} />;

  const patch = async (u: AdminUser, body: Parameters<typeof api.admin.patchUser>[1]) => {
    setActionError(null);
    try {
      const next = await api.admin.patchUser(u.id, body);
      setData(data.map((x) => (x.id === u.id ? next : x)));
      return true;
    } catch (err) {
      setActionError(`${u.username}：${errorText(err)}`);
      return false;
    }
  };

  const adjust = async (u: AdminUser, sign: 1 | -1) => {
    const n = Number(deltas[u.id] || 0);
    if (!Number.isInteger(n) || n <= 0) return;
    if (await patch(u, { quota_delta: sign * n })) setDeltas({ ...deltas, [u.id]: "" });
  };

  const toggleDisabled = (u: AdminUser) => {
    if (!u.is_disabled &&
        !window.confirm(`停用 ${u.username}？停用后立即退出登录、不能再登录，数据保留，随时可以恢复。`)) return;
    void patch(u, { is_disabled: !u.is_disabled });
  };

  return (
    <>
      {actionError && <p className="error" role="alert">{actionError}</p>}
      <div className="admin-scroll">
        <table className="admin-table">
          <thead>
            <tr><th>用户</th><th>注册</th><th className="num">项目</th>
                <th className="num">AI 额度</th><th>调整额度</th><th>账号</th><th>管理员</th></tr>
          </thead>
          <tbody>
            {data.map((u) => {
              const self = u.id === me.id;
              return (
                <tr key={u.id} className={u.is_disabled ? "dim" : undefined}>
                  <td>{u.username}{self && <small className="admin-meta">（你）</small>}</td>
                  <td>{fmtTime(u.created_at)}</td>
                  <td className="num">{u.projects}</td>
                  <td className="num" title={`已用 ${u.ai_used}，共 ${u.ai_quota}`}>
                    {u.ai_quota - u.ai_used}/{u.ai_quota}
                  </td>
                  <td>
                    <span className="admin-quota">
                      <input type="number" min={1} max={10000} aria-label={`${u.username} 额度调整数量`}
                             value={deltas[u.id] ?? ""} placeholder="次数"
                             onChange={(e) => setDeltas({ ...deltas, [u.id]: e.target.value })} />
                      <button type="button" className="small" onClick={() => void adjust(u, 1)}>加</button>
                      <button type="button" className="small" onClick={() => void adjust(u, -1)}>减</button>
                    </span>
                  </td>
                  <td>
                    {/* 自己不能停用自己：停了就再也进不来后台 */}
                    <button type="button" className="small" disabled={self}
                            onClick={() => toggleDisabled(u)}>
                      {u.is_disabled ? "恢复" : "停用"}
                    </button>
                    {u.is_disabled && <span className="status status-expired">已停用</span>}
                  </td>
                  <td>
                    <label className="field-inline">
                      <input type="checkbox" checked={u.is_admin} disabled={self}
                             aria-label={`${u.username} 是管理员`}
                             onChange={(e) => void patch(u, { is_admin: e.target.checked })} />
                    </label>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
