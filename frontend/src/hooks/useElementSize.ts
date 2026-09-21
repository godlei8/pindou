import { useCallback, useEffect, useState } from "react";

/** 观察一个元素的实际内容尺寸。
 *
 *  画布原来按写死的 760×640 算格子大小，屏幕再宽也白搭——右边留一大片空棋盘格。
 *  要按真实可用空间算，就得量。
 *
 *  用「回调 ref + state」而不是 useRef：目标元素常常不是一开始就在的
 *  （工作台加载期走的是早退分支，`.canvas-wrap` 压根没渲染）。
 *  useRef 配 `[]` 依赖的 effect 只在挂载时跑一次，那时 ref.current 还是 null，
 *  元素后来出现也没人去观察它，尺寸就永远停在 0。
 *
 *  jsdom 没有 ResizeObserver，量不到时返回 0；调用方据此回退到一个固定预算。 */
export function useElementSize<T extends HTMLElement>() {
  const [node, setNode] = useState<T | null>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });

  const ref = useCallback((n: T | null) => setNode(n), []);

  useEffect(() => {
    if (!node) return;

    const read = () => {
      // 量内容盒，不是边框盒：clientWidth 已经排除了 border 和滚动条，再扣掉 padding。
      // 用 getBoundingClientRect 会把 border+padding 算进去，画布就会大出一圈、
      // 逼出一根本不该有的滚动条。
      const cs = getComputedStyle(node);
      const w = node.clientWidth
        - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      const h = node.clientHeight
        - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom);
      // 亚像素抖动会让 ResizeObserver 反复触发，差不到 1px 就当没变
      setSize((s) => (Math.abs(s.w - w) < 1 && Math.abs(s.h - h) < 1 ? s : { w, h }));
    };
    read();

    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read);
    ro.observe(node);
    return () => ro.disconnect();
  }, [node]);

  return [ref, size, node] as const;
}
