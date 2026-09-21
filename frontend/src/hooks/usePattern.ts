import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, DEFAULT_PARAMS, api, paramsOf } from "../api/client";
import type { EditCell, PaletteColor, Pattern, PatternBrief, PatternParams, Project,
  SizeSuggestion } from "../api/types";

const DEBOUNCE_MS = 300;
const POLL_MS = 1500;
/** 兜底：AI 任务再慢也不该超过这个数。超了就报出来，别让转圈永远转下去。 */
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

export type AiPhase = "idle" | "queued" | "running" | "failed";

export function usePattern(projectId: string) {
  const [project, setProject] = useState<Project | null>(null);
  const [pattern, setPattern] = useState<Pattern | null>(null);
  const [versions, setVersions] = useState<PatternBrief[]>([]);
  const [params, setParamsState] = useState<PatternParams>(DEFAULT_PARAMS);
  const [sizes, setSizes] = useState<SizeSuggestion[]>([]);
  const [palette, setPalette] = useState<PaletteColor[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [aiPhase, setAiPhase] = useState<AiPhase>("idle");
  const [aiError, setAiError] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);

  /** 已经有对应图纸的那一份参数。用身份比较（不是布尔标志）来决定要不要重算：
   *  标志会在"新参数恰好等于旧参数、React 跳过更新"时卡住，把用户的下一次改动吞掉。 */
  const settled = useRef<PatternParams>(DEFAULT_PARAMS);

  /** 当前图纸基于哪张 AI 图。放 ref 是为了让 recompute 的身份保持稳定——
   *  它是挂载 effect 的依赖，一变就会把整个项目重新拉一遍。 */
  const aiRenderId = useRef<string | null>(null);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.detail : String(e));

  /** 这段连续调参里上一次重算出来的版本。下一次重算请后端用新结果替换它——
   *  拖一下滑块停一下就存一版，调一轮参数版本列表能多出七八个几乎一样的。
   *  任何别的动作（载入、切版本、手改、修复、AI）都会经过 adopt 把它清空：
   *  那之后的第一次调参必须新增一版，不能把用户刚选中、刚做出来的版本替换掉。
   *  （后端还会再复核一遍能不能删，见 patterns.discard_draft。） */
  const replaceable = useRef<string | null>(null);
  /** 重算串行化：有一个在算时只记下最新的参数，中间的直接跳过。 */
  const running = useRef(false);
  const pending = useRef<PatternParams | null>(null);

  const adopt = useCallback((p: Pattern) => {
    setPattern(p);
    aiRenderId.current = p.ai_render_id;
    replaceable.current = null;
    // 乐观维护版本列表：新版本的信息这里全都有，不必为此再请求一次项目
    setVersions((vs) => vs.some((v) => v.id === p.id) ? vs : [{
      id: p.id, origin: p.origin, parent_id: p.parent_id,
      ai_render_id: p.ai_render_id, created_at: p.created_at,
      score: p.buildability?.score ?? null,
      n_colors: Object.keys(p.color_stats ?? {}).length,
      rows: p.grid.length, cols: p.grid[0]?.length ?? 0,
    }, ...vs]);
  }, []);

  const recompute = useCallback(async (next: PatternParams) => {
    // 已经有一个在算：只记下最新的参数，等它回来再算这一个，中间的全跳过。
    // 不串行的话，慢的请求后回来会用旧参数的结果盖掉新的；两个请求还会争着
    // 替换同一个过渡版本，其中一个扑空，漏下一版删不掉。
    if (running.current) { pending.current = next; return; }
    running.current = true;
    setBusy(true);
    setError("");
    try {
      let todo: PatternParams | null = next;
      while (todo) {
        pending.current = null;
        // 带上 aiRenderId：否则调了个 λ 就悄悄退回原图，用户的 AI 额度白花了
        const res = await api.recompute(projectId, todo, aiRenderId.current, replaceable.current);
        adopt(res);
        if (res.replaced_id) {
          const gone = res.replaced_id;
          setVersions((vs) => vs.filter((v) => v.id !== gone));
        }
        replaceable.current = res.id;     // 下一次调参替换的就是它
        todo = pending.current;
      }
    } catch (e) {
      fail(e);
    } finally {
      running.current = false;
      setBusy(false);
    }
  }, [projectId, adopt]);

  // 首次载入：项目 + 色卡 + 尺寸推荐；有版本就取最新，没有就生成一张
  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const [proj, colors] = await Promise.all([
          api.getProject(projectId),
          api.listPaletteColors(DEFAULT_PARAMS.palette_id),
        ]);
        if (!mounted) return;
        setProject(proj);
        setVersions(proj.patterns);
        setPalette(colors);
        api.suggestSizes(projectId, DEFAULT_PARAMS.grid_long_side)
          .then((s) => { if (mounted) setSizes(s); })
          .catch(() => { /* 尺寸推荐失败不影响主流程 */ });

        if (proj.patterns.length > 0) {
          const latest = await api.getPattern(proj.patterns[0].id);
          if (!mounted) return;
          const merged = paramsOf(latest);
          adopt(latest);
          settled.current = merged;
          setParamsState(merged);
        } else {
          await recompute(DEFAULT_PARAMS);
        }
      } catch (e) {
        if (mounted) fail(e);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, [projectId, recompute, adopt]);

  // 参数变化防抖重算。已经有图纸的那份参数不重算——挂载时、以及 AI 出完图之后。
  useEffect(() => {
    if (settled.current === params) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { void recompute(params); }, DEBOUNCE_MS);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [params, recompute]);

  /** 提交 AI 重绘并轮询到结束。AI 出图是异步的：后端返回 job，这里等它。 */
  const generateWithAi = useCallback(async (stylePresetId: string) => {
    setAiError("");
    setAiPhase("queued");
    setError("");
    try {
      const job = await api.generate(projectId, {
        use_ai: true, style_preset_id: stylePresetId, params,
      });
      const deadline = Date.now() + POLL_TIMEOUT_MS;

      for (;;) {
        if (!alive.current) return;
        const cur = await api.getJob(job.id);
        if (cur.status === "done") {
          const patternId = cur.result?.pattern_id;
          if (!patternId) throw new Error("任务完成但没有返回图纸");
          const next = await api.getPattern(patternId);
          if (!alive.current) return;
          const merged = paramsOf(next);
          adopt(next);
          settled.current = merged;   // 这份参数已经有图纸了，别再重算一轮
          setParamsState(merged);
          setAiPhase("idle");
          return;
        }
        if (cur.status === "failed") {
          setAiPhase("failed");
          setAiError(cur.error || "AI 出图失败");
          return;
        }
        if (cur.status === "running") setAiPhase("running");
        if (Date.now() > deadline) {
          setAiPhase("failed");
          setAiError("等待超时。任务可能还在跑，刷新页面看看。");
          return;
        }
        await new Promise((r) => setTimeout(r, POLL_MS));
      }
    } catch (e) {
      if (!alive.current) return;
      setAiPhase("failed");
      setAiError(e instanceof ApiError ? e.detail : String(e));
    }
  }, [projectId, params, adopt]);

  /** 切到某个历史版本。之前生成了一堆版本却没有任何路径回去。 */
  const selectVersion = useCallback(async (id: string) => {
    setBusy(true);
    setError("");
    try {
      const pat = await api.getPattern(id);
      const merged = paramsOf(pat);
      adopt(pat);
      settled.current = merged;   // 这份参数已经有图纸了，别触发一轮重算
      setParamsState(merged);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }, [adopt]);

  return {
    project, pattern, params, sizes, palette, loading, busy, error, versions, selectVersion,
    aiPhase, aiError, aiRenderId: pattern?.ai_render_id ?? null,
    setParams: setParamsState,
    generateWithAi,
    dismissAiError: () => { setAiPhase("idle"); setAiError(""); },
    applyPatch: async (issueIndex: number) => {
      if (!pattern) return;
      setBusy(true);
      setError("");
      try {
        adopt(await api.applyPatch(pattern.id, issueIndex));
      } catch (e) { fail(e); } finally { setBusy(false); }
    },
    saveEdits: async (edits: EditCell[], protectedCells: [number, number][]) => {
      if (!pattern || edits.length === 0) return null;
      setBusy(true);
      setError("");
      try {
        const next = await api.applyEdits(pattern.id, edits, protectedCells);
        adopt(next);
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
