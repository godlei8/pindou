import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { MouseEvent, ReactNode } from "react";

import { AuthProvider, useAuth } from "./hooks/useAuth";
import { WorkbenchNavProvider, useWorkbenchNav } from "./hooks/useWorkbenchNav";
import { AdminPage } from "./pages/AdminPage";
import { LoginPage } from "./pages/LoginPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="loading">加载中…</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

/** 已登录就别再看登录页了——否则顶栏会挂着"已登录"的导航条压在登录表单上面。 */
function GuestOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="loading">加载中…</p>;
  if (user) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function TopBar() {
  const { user, logout } = useAuth();
  const { nav } = useWorkbenchNav();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  if (!user) return null;
  const inAdmin = pathname.startsWith("/admin");

  // 离开工作台的所有出口都要过一遍"有没有未保存改动"
  const leave = (then: () => void) => (e?: MouseEvent) => {
    e?.preventDefault();
    if (nav && !nav.confirmLeave()) return;
    then();
  };
  const goHome = leave(() => navigate("/"));

  return (
    <header className="topbar">
      {nav ? (
        <>
          <button type="button" className="back" onClick={goHome}>← 返回首页</button>
          <span className="crumb" title={nav.title}>{nav.title}</span>
        </>
      ) : (
        <Link to="/" className="brand" onClick={goHome}>拼豆图纸生成</Link>
      )}
      {/* 管理入口只给管理员；在后台里就不再显示自己 */}
      {user.is_admin && !inAdmin && (
        <Link to="/admin" className="admin-link" onClick={leave(() => navigate("/admin"))}>管理后台</Link>
      )}
      <span className="quota">
        {user.username} · AI 额度 {user.ai_quota - user.ai_used}/{user.ai_quota}
      </span>
      <button type="button" onClick={leave(() => void logout())}>退出</button>
    </header>
  );
}

export function App() {
  return (
    <AuthProvider>
      <WorkbenchNavProvider>
        <TopBar />
        <Routes>
          <Route path="/login" element={<GuestOnly><LoginPage /></GuestOnly>} />
          <Route path="/" element={<Protected><ProjectsPage /></Protected>} />
          <Route path="/admin/:section?" element={<Protected><AdminPage /></Protected>} />
          <Route path="/p/:projectId" element={<Protected><WorkbenchPage /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </WorkbenchNavProvider>
    </AuthProvider>
  );
}
