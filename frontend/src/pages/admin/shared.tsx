import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../../api/client";

/** 读一份后台数据：加载中 / 出错 / 数据，外加一个手动刷新。 */
export function useAdminData<T>(load: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setError(null);
    try {
      setData(await load());
    } catch (e) {
      setError(errorText(e));
    }
  }, [load]);

  useEffect(() => { void reload(); }, [reload]);
  return { data, setData, error, setError, reload };
}

export function errorText(e: unknown): string {
  return e instanceof ApiError ? e.detail : e instanceof Error ? e.message : String(e);
}

/** "09-21 20:10"：后台列表里年份几乎没用，占宽度 */
export function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function Loading({ error, onRetry }: { error: string | null; onRetry(): void }) {
  if (!error) return <p className="empty">加载中…</p>;
  return (
    <p className="error" role="alert">
      {error} <button type="button" onClick={onRetry}>重试</button>
    </p>
  );
}
