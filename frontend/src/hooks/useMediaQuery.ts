import { useEffect, useState } from "react";

/** 订阅一条媒体查询。jsdom 没有 matchMedia，拿不到就当不匹配（走桌面布局）。 */
export function useMediaQuery(query: string): boolean {
  const get = () => typeof window !== "undefined" && typeof window.matchMedia === "function"
    && window.matchMedia(query).matches;
  const [matches, setMatches] = useState(get);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** 手机和竖屏平板：工作台改成「画布在上 + 标签页切面板」。再宽一点才走单栏堆叠。 */
export const PHONE_QUERY = "(max-width: 900px)";
/** 手指操作的设备：画布默认是拖动，不是画笔——否则一碰就画上一格，还没法滚动。 */
export const TOUCH_QUERY = "(pointer: coarse)";
