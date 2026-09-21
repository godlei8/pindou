import { createContext, useContext, useMemo, useState } from "react";
import type { ReactNode } from "react";

/** 工作台告诉顶栏的两件事：当前项目叫什么，以及离开前要不要确认。
 *
 *  顶栏在路由外面，拿不到编辑器的"有没有未保存改动"。
 *  改参数时早就会确认"重算会丢掉改动"——返回首页、退出登录同样会丢，不能悄悄丢。
 *  （用的是 BrowserRouter 不是数据路由，react-router 的 useBlocker 用不了。） */
export interface WorkbenchNav {
  title: string;
  /** 返回 true 表示可以离开。有未保存改动时会先问用户。 */
  confirmLeave(): boolean;
}

interface Value {
  nav: WorkbenchNav | null;
  setNav(nav: WorkbenchNav | null): void;
}

const Ctx = createContext<Value | null>(null);

export function WorkbenchNavProvider({ children }: { children: ReactNode }) {
  const [nav, setNav] = useState<WorkbenchNav | null>(null);
  const value = useMemo(() => ({ nav, setNav }), [nav]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkbenchNav(): Value {
  // 不在 Provider 里（比如单独测某个页面）就当没有工作台导航，别炸
  return useContext(Ctx) ?? { nav: null, setNav: () => {} };
}
