import { NavLink, Navigate, useParams } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { AiUsageSection } from "./admin/AiUsageSection";
import { FeedbackSection } from "./admin/FeedbackSection";
import { InvitesSection } from "./admin/InvitesSection";
import { PresetsSection } from "./admin/PresetsSection";
import { UsersSection } from "./admin/UsersSection";

/** 顺序按"多久看一次"排：反馈和花费天天看，预设很少动。 */
const SECTIONS = [
  { key: "feedback", label: "实拼反馈", Comp: FeedbackSection },
  { key: "ai", label: "AI 用量", Comp: AiUsageSection },
  { key: "users", label: "用户和额度", Comp: UsersSection },
  { key: "invites", label: "邀请码", Comp: InvitesSection },
  { key: "presets", label: "风格预设", Comp: PresetsSection },
] as const;

export function AdminPage() {
  const { user } = useAuth();
  const { section } = useParams();
  // 后端每个接口都会再查一遍权限；这里只是别让普通用户看到一堆 403
  if (!user?.is_admin) return <Navigate to="/" replace />;

  const current = SECTIONS.find((s) => s.key === section);
  if (!current) return <Navigate to={`/admin/${SECTIONS[0].key}`} replace />;
  const { Comp } = current;

  return (
    <main className="admin">
      <nav className="admin-nav" aria-label="管理后台">
        <h1>管理后台</h1>
        {SECTIONS.map((s) => (
          <NavLink key={s.key} to={`/admin/${s.key}`}>{s.label}</NavLink>
        ))}
      </nav>
      <section className="admin-body" aria-labelledby="admin-title">
        <h2 id="admin-title">{current.label}</h2>
        <Comp me={user} />
      </section>
    </main>
  );
}
