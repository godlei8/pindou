import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, DEFAULT_PARAMS, api } from "../api/client";
import type { EditCell, PaletteColor, Pattern, PatternParams, Project, SizeSuggestion }
  from "../api/types";

const DEBOUNCE_MS = 300;

export function usePattern(projectId: string) {
  const [project, setProject] = useState<Project | null>(null);
  const [pattern, setPattern] = useState<Pattern | null>(null);
  const [params, setParamsState] = useState<PatternParams>(DEFAULT_PARAMS);
  const [sizes, setSizes] = useState<SizeSuggestion[]>([]);
  const [palette, setPalette] = useState<PaletteColor[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const firstRun = useRef(true);

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.detail : String(e));

  const recompute = useCallback(async (next: PatternParams) => {
    setBusy(true);
    setError("");
    try {
      setPattern(await api.recompute(projectId, next));
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }, [projectId]);

  // 首次载入：项目 + 色卡 + 尺寸推荐；有版本就取最新，没有就生成一张
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const [proj, colors] = await Promise.all([
          api.getProject(projectId),
          api.listPaletteColors(DEFAULT_PARAMS.palette_id),
        ]);
        if (!alive) return;
        setProject(proj);
        setPalette(colors);
        api.suggestSizes(projectId, DEFAULT_PARAMS.grid_long_side)
          .then((s) => { if (alive) setSizes(s); })
          .catch(() => { /* 尺寸推荐失败不影响主流程 */ });

        if (proj.patterns.length > 0) {
          const latest = await api.getPattern(proj.patterns[0].id);
          if (!alive) return;
          setPattern(latest);
          setParamsState({ ...DEFAULT_PARAMS, ...latest.params });
        } else {
          await recompute(DEFAULT_PARAMS);
        }
      } catch (e) {
        if (alive) fail(e);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [projectId, recompute]);

  // 参数变化防抖重算（首次渲染不触发）
  useEffect(() => {
    if (firstRun.current) {
      firstRun.current = false;
      return;
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { void recompute(params); }, DEBOUNCE_MS);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [params, recompute]);

  return {
    project, pattern, params, sizes, palette, loading, busy, error,
    setParams: setParamsState,
    applyPatch: async (issueIndex: number) => {
      if (!pattern) return;
      setBusy(true);
      setError("");
      try {
        setPattern(await api.applyPatch(pattern.id, issueIndex));
      } catch (e) { fail(e); } finally { setBusy(false); }
    },
    saveEdits: async (edits: EditCell[], protectedCells: [number, number][]) => {
      if (!pattern || edits.length === 0) return null;
      setBusy(true);
      setError("");
      try {
        const next = await api.applyEdits(pattern.id, edits, protectedCells);
        setPattern(next);
        return next;
      } catch (e) {
        fail(e);
        return null;
      } finally {
        setBusy(false);
      }
    },
    sendFeedback: async (kind: string, note: string, cells: [number, number][]) => {
      if (!pattern) return;
      try {
        await api.sendFeedback(pattern.id, { kind, cells, note });
      } catch (e) { fail(e); }
    },
  };
}
