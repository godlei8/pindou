import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { MouseEvent, ReactNode } from "react";

import { AuthProvider, useAuth } from "./hooks/useAuth";
import { WorkbenchNavProvider, useWorkbenchNav } from "./hooks/useWorkbenchNav";
import { AdminLoginPage } from "./pages/AdminLoginPage";
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

/** 后台：没登录去后台自己的登录页，不是管理员回首页。 */
function AdminOnly({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="loading">加载中…</p>;
  if (!user) return <Navigate to="/admin/login" replace />;
  if (!user.is_admin) return <Navigate to="/" replace />;
  return <>{children}</>;
}

/** 后台登录页：已经是管理员就直接进后台。普通用户登着也能打开它，换管理员账号登录。 */
function AdminGuest({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="loading">加载中…</p>;
  if (user?.is_admin) return <Navigate to="/admin" replace />;
  return <>{children}</>;
}

function TopBar() {
  const { user, logout } = useAuth();
  const { nav } = useWorkbenchNav();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  // 后台登录页是独立的一页，不挂用户站的顶栏
  if (!user || pathname === "/admin/login") return null;
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
          {/* 手机上只显示「← 首页」，给项目名多留点地方 */}
          <button type="button" className="back" aria-label="← 返回首页" onClick={goHome}>
            ← <span className="wide-only">返回</span>首页
          </button>
          <span className="crumb" title={nav.title}>{nav.title}</span>
        </>
      ) : (
        <Link to="/" className="brand" onClick={goHome}>馨豆</Link>
      )}
      {/* 管理入口只给管理员；在后台里就不再显示自己 */}
      {user.is_admin && !inAdmin && (
        <Link to="/admin" className="admin-link" aria-label="管理后台" onClick={leave(() => navigate("/admin"))}>
          <span className="wide-only">管理</span>后台
        </Link>
      )}
      <span className="quota">
        <span className="wide-only">{user.username} · </span>
        AI <span className="wide-only">额度 </span>{user.ai_quota - user.ai_used}/{user.ai_quota}
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
          {/* 邀请链接 /register?code=XXXX：打开就是注册页，邀请码填好 */}
          <Route path="/register" element={<GuestOnly><LoginPage /></GuestOnly>} />
          <Route path="/admin/login" element={<AdminGuest><AdminLoginPage /></AdminGuest>} />
          <Route path="/admin/:section?" element={<AdminOnly><AdminPage /></AdminOnly>} />
          <Route path="/p/:projectId" element={<Protected><WorkbenchPage /></Protected>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </WorkbenchNavProvider>
    </AuthProvider>
  );
}
