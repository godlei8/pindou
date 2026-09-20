import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { ApiError, api } from "../api/client";
import type { User } from "../api/types";

interface AuthValue {
  user: User | null;
  loading: boolean;
  login(username: string, password: string): Promise<void>;
  register(username: string, password: string, inviteCode: string): Promise<void>;
  logout(): Promise<void>;
  refresh(): Promise<void>;
}

const Ctx = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setUser(await api.me());
    } catch (e) {
      // 401 就是"没登录"，不是错误
      if (e instanceof ApiError && e.status === 401) setUser(null);
      else throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const value: AuthValue = {
    user,
    loading,
    login: async (u, p) => { setUser(await api.login(u, p)); },
    register: async (u, p, code) => { setUser(await api.register(u, p, code)); },
    logout: async () => { await api.logout(); setUser(null); },
    refresh,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth 必须在 AuthProvider 内使用");
  return v;
}
