import { Navigate, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import { AuthProvider, useAuth } from "./hooks/useAuth";
import { LoginPage } from "./pages/LoginPage";
import { ProjectsPage } from "./pages/ProjectsPage";
import { WorkbenchPage } from "./pages/WorkbenchPage";

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <p className="loading">加载中…</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function TopBar() {
  const { user, logout } = useAuth();
  if (!user) return null;
  return (
    <header className="topbar">
      <a href="/">拼豆图纸生成</a>
      <span>{user.username} · AI 额度 {user.ai_quota - user.ai_used}/{user.ai_quota}</span>
      <button type="button" onClick={() => void logout()}>退出</button>
    </header>
  );
}

export function App() {
  return (
    <AuthProvider>
      <TopBar />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Protected><ProjectsPage /></Protected>} />
        <Route path="/p/:projectId" element={<Protected><WorkbenchPage /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AuthProvider>
  );
}
