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
import { usePattern } from "../hooks/usePattern";
import { useWorkbenchNav } from "../hooks/useWorkbenchNav";
import { fitCellPx } from "../lib/draw";
import { MAX_ZOOM, MIN_ZOOM, SHOW_CODES_MIN, cellPxFor, zoomIn, zoomOut } from "../lib/zoom";
import type { ZoomMode } from "../lib/zoom";

/** 留 2px 余量。正好卡在边界上时，滚动条一出一进会让尺寸来回抖。 */
const SAFETY_PAD = 2;
/** 量不到容器时的回退预算（jsdom 没有 ResizeObserver）。 */
const FALLBACK_BOX = { w: 760, h: 640 };

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

  // 后端返回新版本 → 重置编辑基线
  useEffect(() => {
    if (p.pattern) editor.resetTo(p.pattern.grid, p.pattern.params.protected_cells ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patternId]);

  // 换了项目才回到默认；同一项目里改参数、切版本时保留用户选的缩放方式——
  // codes / fit 本来就会跟着格数自己调，没必要每出一版就把人弹回去
  useEffect(() => { setZoom("codes"); }, [projectId]);
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

  return (
    <main className="workbench">
      <div className="side">
        {p.project && (
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
        )}
        <VersionList versions={p.versions} currentId={p.pattern?.id ?? null}
                     disabled={p.busy} onSelect={(id) => void p.selectVersion(id)} />
      </div>

      <div className="editor">
        {p.error && <p role="alert" className="error">{p.error}</p>}
        <ToolBar state={editor.state} saving={saving} onTool={editor.setTool}
                 onUndo={editor.undo} onRedo={editor.redo} onSave={() => void save()}
                 extra={p.pattern ? <ExportButtons patternId={p.pattern.id} /> : null} />
        <PalettePicker colors={colorMap} working={working} selected={selected}
                       codeOf={(i) => codeMap.get(i) ?? String(i)} onSelect={editor.setColor} />
        <CanvasBar
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
        <div className="canvas-wrap" ref={wrapRef}>
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

      <div className="side">
        <ParamPanel params={p.params} sizes={p.sizes} disabled={p.busy} onChange={changeParams}
                    faceHint={p.pattern?.face_hint ?? null}
                    current={p.pattern && p.pattern.grid.length > 0
                      ? { rows: p.pattern.grid.length, cols: p.pattern.grid[0].length }
                      : null} />
        <IssueList buildability={p.pattern?.buildability ?? null} applying={p.busy}
                   onApply={(i) => void p.applyPatch(i)}
                   onFeedback={p.pattern
                     ? ({ kind, note }) => void p.sendFeedback(kind, note, [])
                     : undefined} />
        <MaterialList materials={p.pattern?.materials ?? []}
                      locating={locating} onLocate={setLocating} />
      </div>
    </main>
  );
}
