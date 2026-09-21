import { api } from "../../api/client";
import type { User } from "../../api/types";
import { Loading, fmtTime, useAdminData } from "./shared";

const STATUS: Record<string, string> = {
  done: "完成", failed: "失败", running: "进行中", pending: "排队",
};

/** 金额按元显示两位小数；后端存四位是为了单价小于一分的模型 */
const yuan = (s: string | null) => (s === null ? "—" : `¥${Number(s).toFixed(2)}`);

export function AiUsageSection(_: { me: User }) {
  const { data, error, reload } = useAdminData(api.admin.aiUsage);
  if (!data) return <Loading error={error} onRetry={reload} />;
  const { total, users, recent } = data;

  return (
    <>
      <dl className="admin-stats">
        <div><dt>重绘次数</dt><dd>{total.renders}</dd></div>
        <div><dt>成功</dt><dd>{total.done}</dd></div>
        <div><dt>失败</dt><dd className={total.failed ? "bad" : undefined}>{total.failed}</dd></div>
        <div><dt>花费</dt><dd>{yuan(total.cost)}</dd></div>
      </dl>
      <p className="admin-meta">失败的次数已退还额度，不产生费用。花费按 providers.yaml 里的单价估算。</p>

      <h3>按用户</h3>
      {users.length === 0 ? <p className="empty">还没有人用过 AI 重绘。</p> : (
        <div className="admin-scroll">
          <table className="admin-table">
            <thead>
              <tr><th>用户</th><th className="num">重绘</th><th className="num">成功</th>
                  <th className="num">失败</th><th className="num">花费</th><th className="num">额度剩余</th></tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.username}>
                  <td>{u.username}</td>
                  <td className="num">{u.renders}</td>
                  <td className="num">{u.done}</td>
                  <td className="num">{u.failed}</td>
                  <td className="num">{yuan(u.cost)}</td>
                  <td className="num">{u.ai_quota - u.ai_used}/{u.ai_quota}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>最近 {recent.length} 次</h3>
      {recent.length > 0 && (
        <div className="admin-scroll">
          <table className="admin-table">
            <thead>
              <tr><th>时间</th><th>用户</th><th>项目</th><th>风格</th><th>模型</th>
                  <th>状态</th><th className="num">花费</th></tr>
            </thead>
            <tbody>
              {recent.map((r) => (
                <tr key={r.id}>
                  <td>{fmtTime(r.created_at)}</td>
                  <td>{r.username}</td>
                  <td className="clip" title={r.project_name}>{r.project_name}</td>
                  <td>{r.preset ?? "—"}</td>
                  <td className="clip" title={`${r.provider} / ${r.model}`}>{r.model}</td>
                  <td>
                    <span className={`status status-${r.status}`}>{STATUS[r.status] ?? r.status}</span>
                    {r.error && <small className="admin-error" title={r.error}>{r.error}</small>}
                  </td>
                  <td className="num">{yuan(r.cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
