import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import type { PatternParams } from "../api/types";
import { CanvasBar } from "../components/CanvasBar";
import { ExportButtons } from "../components/ExportButtons";
import { IssueList } from "../components/IssueList";
import { MaterialList } from "../components/MaterialList";
import { PalettePicker } from "../components/PalettePicker";
import { ParamPanel } from "../components/ParamPanel";
import { PatternCanvas } from "../components/PatternCanvas";
import { SourcePanel } from "../components/SourcePanel";
import { ToolBar } from "../components/ToolBar";
import { VersionList } from "../components/VersionList";
import { useEditor } from "../hooks/useEditor";
import { useElementSize } from "../hooks/useElementSize";
import { PHONE_QUERY, TOUCH_QUERY, useMediaQuery } from "../hooks/useMediaQuery";
import { usePattern } from "../hooks/usePattern";
import { useWorkbenchNav } from "../hooks/useWorkbenchNav";
import { fitCellPx } from "../lib/draw";
import { MAX_ZOOM, MIN_ZOOM, SHOW_CODES_MIN, cellPxFor, zoomIn, zoomOut } from "../lib/zoom";
import type { ZoomMode } from "../lib/zoom";

/** 留 2px 余量。正好卡在边界上时，滚动条一出一进会让尺寸来回抖。 */
const SAFETY_PAD = 2;
/** 量不到容器时的回退预算（jsdom 没有 ResizeObserver）。 */
const FALLBACK_BOX = { w: 760, h: 640 };

/** 手机上两侧栏收进标签页：画布常驻上半屏，改参数时图纸一直看得见。 */
const PHONE_TABS = [
  ["params", "参数"],
  ["materials", "清单"],
  ["issues", "体检"],
  ["versions", "版本"],
  ["source", "原图·AI"],
] as const;
type PhoneTab = (typeof PHONE_TABS)[number][0];

/** 双指张合超过这个比例才换一档。缩放是整数档位，太灵敏会一下跳好几档。 */
const PINCH_STEP = 1.25;

export function WorkbenchPage() {
  const { projectId = "" } = useParams();
  const p = usePattern(projectId);
  const editor = useEditor([], []);
  const [saving, setSaving] = useState(false);
  const patternId = p.pattern?.id;

  // 告诉顶栏：项目名，以及离开前要不要确认。dirty 放 ref 里读最新值，
  // 免得每画一笔都重新注册一次。
  const { setNav } = useWorkbenchNav();
  const dirty = useRef(false);
  dirty.current = editor.state.dirty;
  const projectName = p.project?.name ?? "";
  useEffect(() => {
    setNav({
      title: projectName,
      confirmLeave: () => !dirty.current
        || window.confirm("有未保存的改动，离开会丢掉它们。确定离开？"),
    });
    return () => setNav(null);
  }, [projectName, setNav]);

  const [wrapRef, wrapSize, wrapNode] = useElementSize<HTMLDivElement>();
  /** 默认 codes：一进来就能逐格看清色号。看全貌点「适应」。 */
  const [zoom, setZoom] = useState<ZoomMode>("codes");
  /** 正在图上定位的色号索引。点材料清单里的一行就能看见它铺在哪儿。 */
  const [locating, setLocating] = useState<number | null>(null);
  const isPhone = useMediaQuery(PHONE_QUERY);
  const isTouch = useMediaQuery(TOUCH_QUERY);
  const [tab, setTab] = useState<PhoneTab>("params");
  const [fullscreen, setFullscreen] = useState(false);

  /** 全屏预览。页面内铺满是主体（哪都能用）；浏览器支持的话顺便请求系统全屏，
   *  把地址栏、底栏也收起来。内置浏览器常常不给，失败就只做页面内铺满。 */
  function toggleFullscreen() {
    const next = !fullscreen;
    setFullscreen(next);
    if (next) setZoom("fit");                       // 进来先看全貌，再自己放大看细节
    try {
      if (next) void document.documentElement.requestFullscreen?.().catch(() => {});
      else if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
    } catch {
      /* 老 WebView 没有 Fullscreen API：页面内铺满照样可用 */
    }
  }

  // 系统全屏被返回键/手势退掉时，页面内的铺满也一起退；Esc 同理
  useEffect(() => {
    if (!fullscreen) return;
    const onChange = () => { if (!document.fullscreenElement) setFullscreen(false); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setFullscreen(false); };
    document.addEventListener("fullscreenchange", onChange);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("fullscreenchange", onChange);
      window.removeEventListener("keydown", onKey);
    };
  }, [fullscreen]);

  // 触屏默认拖动：画笔当默认的话，想滚一下画布就先画上了一格
  useEffect(() => {
    if (isTouch) editor.setTool("pan");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isTouch]);

  // 后端返回新版本 → 重置编辑基线
  useEffect(() => {
    if (p.pattern) editor.resetTo(p.pattern.grid, p.pattern.params.protected_cells ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patternId]);

  // 换了项目才回到默认；同一项目里改参数、切版本时保留用户选的缩放方式——
  // codes / fit 本来就会跟着格数自己调，没必要每出一版就把人弹回去
  // 手机例外：画布只有小半屏，看色号只看得到左上角一小块，先给全貌
  useEffect(() => { setZoom(isPhone ? "fit" : "codes"); }, [projectId, isPhone]);
  useEffect(() => { setLocating(null); }, [patternId]);

  const colorMap = useMemo(
    () => new Map(p.palette.map((c) => [c.index, c.hex])), [p.palette]);
  const codeMap = useMemo(
    () => new Map(p.palette.map((c) => [c.index, c.code])), [p.palette]);
  const working = useMemo(
    () => Object.keys(p.pattern?.color_stats ?? {}).map(Number).sort((a, b) => a - b),
    [p.pattern]);

  const fitPx = useMemo(() => {
    const w = (wrapSize.w > 0 ? wrapSize.w : FALLBACK_BOX.w) - SAFETY_PAD;
    const h = (wrapSize.h > 0 ? wrapSize.h : FALLBACK_BOX.h) - SAFETY_PAD;
    // 封顶：小图纸（比如 8 格）在大屏上会算出每格一两百像素，荒唐
    return Math.min(MAX_ZOOM, fitCellPx(editor.state.grid, w, h));
  }, [editor.state.grid, wrapSize.w, wrapSize.h]);

  const cellPx = cellPxFor(zoom, fitPx);

  const highlight = useMemo<[number, number][]>(() => {
    if (locating === null) return [];
    const out: [number, number][] = [];
    editor.state.grid.forEach((row, r) =>
      row.forEach((v, c) => { if (v === locating) out.push([r, c]); }));
    return out;
  }, [locating, editor.state.grid]);

  // Ctrl+滚轮缩放。必须用原生监听器：React 的 onWheel 是被动的，preventDefault 无效，
  // 不拦住浏览器就会去缩放整个页面。
  useEffect(() => {
    if (!wrapNode) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.ctrlKey) return;          // 不按 Ctrl 就是正常滚动画布
      e.preventDefault();
      setZoom(e.deltaY < 0 ? zoomIn(cellPx) : zoomOut(cellPx));
    };
    wrapNode.addEventListener("wheel", onWheel, { passive: false });
    return () => wrapNode.removeEventListener("wheel", onWheel);
  }, [wrapNode, cellPx]);

  // 双指缩放。原生监听器 + passive:false，才能拦住浏览器去缩放整个页面。
  const cellPxRef = useRef(cellPx);
  cellPxRef.current = cellPx;
  useEffect(() => {
    if (!wrapNode) return;
    let base = 0;
    const dist = (t: TouchList) =>
      Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
    const onStart = (e: TouchEvent) => { if (e.touches.length === 2) base = dist(e.touches); };
    const onMove = (e: TouchEvent) => {
      if (e.touches.length !== 2 || base === 0) return;
      e.preventDefault();
      const d = dist(e.touches);
      if (d / base >= PINCH_STEP) { setZoom(zoomIn(cellPxRef.current)); base = d; }
      else if (base / d >= PINCH_STEP) { setZoom(zoomOut(cellPxRef.current)); base = d; }
    };
    const onEnd = (e: TouchEvent) => { if (e.touches.length < 2) base = 0; };
    wrapNode.addEventListener("touchstart", onStart, { passive: true });
    wrapNode.addEventListener("touchmove", onMove, { passive: false });
    wrapNode.addEventListener("touchend", onEnd);
    wrapNode.addEventListener("touchcancel", onEnd);
    return () => {
      wrapNode.removeEventListener("touchstart", onStart);
      wrapNode.removeEventListener("touchmove", onMove);
      wrapNode.removeEventListener("touchend", onEnd);
      wrapNode.removeEventListener("touchcancel", onEnd);
    };
  }, [wrapNode]);

  function changeParams(next: PatternParams) {
    if (editor.state.dirty &&
        !window.confirm("有未保存的改动，重算参数会丢弃它们。继续？")) return;
    p.setParams(next);
  }

  async function save() {
    const edits = editor.pendingEdits();
    if (edits.length === 0) return;
    setSaving(true);
    await p.saveEdits(edits, editor.state.protectedCells);
    setSaving(false);
  }

  if (p.loading) return <main><p className="loading">加载中…</p></main>;

  const selected = editor.state.color;

  const source = p.project && (
    <SourcePanel
      projectId={projectId}
      projectName={p.project.name}
      aiRenderId={p.aiRenderId}
      originalQuality={
        // 只在还看着原图出的图纸时才有意义：已经花过额度就别马后炮了
        p.pattern && !p.pattern.ai_render_id && p.pattern.buildability
          ? { score: p.pattern.buildability.score,
              confetti_pct: p.pattern.buildability.confetti_pct }
          : null
      }
      aiPhase={p.aiPhase}
      aiError={p.aiError}
      busy={p.busy}
      onGenerate={(presetId) => void p.generateWithAi(presetId)}
      onDismissError={p.dismissAiError}
    />
  );
  const versions = (
    <VersionList versions={p.versions} currentId={p.pattern?.id ?? null}
                 disabled={p.busy} onSelect={(id) => void p.selectVersion(id)} />
  );
  const params = (
    <ParamPanel params={p.params} sizes={p.sizes} disabled={p.busy} onChange={changeParams}
                faceHint={p.pattern?.face_hint ?? null}
                backgroundNotFound={!!p.pattern?.params.remove_background
                  && p.pattern.grid.every((row) => row.every((v) => v !== null))}
                current={p.pattern && p.pattern.grid.length > 0
                  ? { rows: p.pattern.grid.length, cols: p.pattern.grid[0].length }
                  : null} />
  );
  const issues = (
    <IssueList buildability={p.pattern?.buildability ?? null} applying={p.busy}
               onApply={(i) => void p.applyPatch(i)}
               onFeedback={p.pattern
                 ? ({ kind, note }) => void p.sendFeedback(kind, note, [])
                 : undefined} />
  );
  const materials = (
    <MaterialList materials={p.pattern?.materials ?? []}
                  locating={locating} onLocate={setLocating} />
  );
  const exportButtons = p.pattern ? <ExportButtons patternId={p.pattern.id} /> : null;

  const editorColumn = (
    <div className="editor">
      {p.error && <p role="alert" className="error">{p.error}</p>}
      {/* 手机上导出挪进「清单」标签：工具条要压成一行，放不下 */}
      <ToolBar state={editor.state} saving={saving} onTool={editor.setTool}
               onUndo={editor.undo} onRedo={editor.redo} onSave={() => void save()}
               withPan={isTouch}
               extra={isPhone ? null : exportButtons} />
      <PalettePicker colors={colorMap} working={working} selected={selected}
                     codeOf={(i) => codeMap.get(i) ?? String(i)} onSelect={editor.setColor} />
      <div className={`canvas-stage${fullscreen ? " is-full" : ""}`}>
        <CanvasBar
          fullscreen={fullscreen}
          onToggleFullscreen={toggleFullscreen}
          colorCode={selected === null ? null : (codeMap.get(selected) ?? String(selected))}
          colorHex={selected === null ? null : (colorMap.get(selected) ?? null)}
          cellPx={cellPx}
          mode={typeof zoom === "number" ? "manual" : zoom}
          showsCodes={cellPx >= SHOW_CODES_MIN}
          canZoomIn={cellPx < MAX_ZOOM}
          canZoomOut={cellPx > MIN_ZOOM}
          onZoomIn={() => setZoom(zoomIn(cellPx))}
          onZoomOut={() => setZoom(zoomOut(cellPx))}
          onFit={() => setZoom("fit")}
          onCodes={() => setZoom("codes")}
        />
        <div className={`canvas-wrap${editor.state.tool === "pan" ? " is-pan" : ""}`} ref={wrapRef}>
          <PatternCanvas grid={editor.state.grid} colors={colorMap} cellPx={cellPx}
                         codeOf={(i) => codeMap.get(i) ?? String(i)}
                         showCodes={cellPx >= SHOW_CODES_MIN}
                         highlight={highlight}
                         protectedCells={editor.state.protectedCells}
                         onCellDown={(r, c) => editor.applyAt(r, c)}
                         onCellEnter={(r, c) => editor.applyAt(r, c)}
                         onPointerUp={() => {}} />
        </div>
      </div>
    </div>
  );

  if (isPhone) {
    return (
      <main className="workbench is-phone">
        {editorColumn}
        <div className="phone-tabs" role="tablist" aria-label="面板">
          {PHONE_TABS.map(([key, label]) => (
            <button key={key} type="button" role="tab" id={`tab-${key}`}
                    aria-selected={tab === key} aria-controls="phone-panel"
                    onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </div>
        <div className="phone-panel" id="phone-panel" role="tabpanel"
             aria-labelledby={`tab-${tab}`}>
          {tab === "params" && params}
          {tab === "materials" && <>
            {materials}
            {exportButtons && <section className="panel"><h2>导出</h2>{exportButtons}</section>}
          </>}
          {tab === "issues" && issues}
          {tab === "versions" && versions}
          {tab === "source" && source}
        </div>
      </main>
    );
  }

  return (
    <main className="workbench">
      <div className="side">
        {source}
        {versions}
      </div>
      {editorColumn}
      <div className="side">
        {params}
        {issues}
        {materials}
      </div>
    </main>
  );
}
