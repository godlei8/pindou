import { api } from "../../api/client";
import type { User } from "../../api/types";
import { Loading, fmtTime, useAdminData } from "./shared";

export function FeedbackSection(_: { me: User }) {
  const { data, error, reload } = useAdminData(api.admin.feedback);
  if (!data) return <Loading error={error} onRetry={reload} />;
  if (data.length === 0) {
    return <p className="empty">还没有人提交实拼反馈。入口在工作台可拼性面板底部的「实拼反馈」。</p>;
  }

  return (
    <ul className="admin-feedback">
      {data.map((f) => (
        <li key={f.id}>
          {/* 每格 1 像素的缩略图，放大时保持像素边缘 */}
          <img src={api.admin.thumbUrl(f.pattern_id)} alt={`${f.project_name} 的图纸`}
               loading="lazy" />
          <div>
            <p className="admin-feedback-head">
              <b className="tag">{f.kind}</b>
              <span>{f.project_name}</span>
            </p>
            <p className="admin-feedback-note">{f.note || <span className="empty">（没写说明）</span>}</p>
            <p className="admin-meta">
              {f.username} · {fmtTime(f.created_at)}
              {f.cells > 0 && ` · 圈了 ${f.cells} 格`}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}
