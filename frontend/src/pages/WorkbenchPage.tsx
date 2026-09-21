import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import type { PatternParams } from "../api/types";
import { ExportBar } from "../components/ExportBar";
import { IssueList } from "../components/IssueList";
import { MaterialList } from "../components/MaterialList";
import { PalettePicker } from "../components/PalettePicker";
import { ParamPanel } from "../components/ParamPanel";
import { PatternCanvas } from "../components/PatternCanvas";
import { SourcePanel } from "../components/SourcePanel";
import { ToolBar } from "../components/ToolBar";
import { useEditor } from "../hooks/useEditor";
import { usePattern } from "../hooks/usePattern";
import { fitCellPx } from "../lib/draw";

export function WorkbenchPage() {
  const { projectId = "" } = useParams();
  const p = usePattern(projectId);
  const editor = useEditor([], []);
  const [saving, setSaving] = useState(false);
  const patternId = p.pattern?.id;

  // 后端返回新版本 → 重置编辑基线
  useEffect(() => {
    if (p.pattern) editor.resetTo(p.pattern.grid, p.pattern.params.protected_cells ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patternId]);

  const colorMap = useMemo(
    () => new Map(p.palette.map((c) => [c.index, c.hex])), [p.palette]);
  const codeMap = useMemo(
    () => new Map(p.palette.map((c) => [c.index, c.code])), [p.palette]);
  const working = useMemo(
    () => Object.keys(p.pattern?.color_stats ?? {}).map(Number).sort((a, b) => a - b),
    [p.pattern]);
  const cellPx = useMemo(
    () => fitCellPx(editor.state.grid, 760, 640), [editor.state.grid]);

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

  return (
    <main className="workbench">
      <div>
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
        {p.pattern && (
          <p className="empty">
            当前版本 {p.pattern.id.slice(0, 8)}
            {/* origin 说的是"怎么产生的"（generated/edited/patched），
                "基于哪张图"只有 ai_render_id 说了算 */}
            （{p.pattern.ai_render_id ? "基于 AI 图" : "基于原图"}）
          </p>
        )}
      </div>

      <div>
        {p.error && <p role="alert" className="error">{p.error}</p>}
        <ToolBar state={editor.state} saving={saving} onTool={editor.setTool}
                 onUndo={editor.undo} onRedo={editor.redo} onSave={() => void save()} />
        <PalettePicker colors={colorMap} working={working} selected={editor.state.color}
                       codeOf={(i) => codeMap.get(i) ?? String(i)} onSelect={editor.setColor} />
        <div className="canvas-wrap">
          <PatternCanvas grid={editor.state.grid} colors={colorMap} cellPx={cellPx}
                         codeOf={(i) => codeMap.get(i) ?? String(i)}
                         showCodes={cellPx >= 18}
                         protectedCells={editor.state.protectedCells}
                         onCellDown={(r, c) => editor.applyAt(r, c)}
                         onCellEnter={(r, c) => editor.applyAt(r, c)}
                         onPointerUp={() => {}} />
        </div>
      </div>

      <div>
        <ParamPanel params={p.params} sizes={p.sizes} disabled={p.busy} onChange={changeParams} />
        <IssueList buildability={p.pattern?.buildability ?? null} applying={p.busy}
                   onApply={(i) => void p.applyPatch(i)} />
        <MaterialList materials={p.pattern?.materials ?? []} />
        {p.pattern && (
          <ExportBar patternId={p.pattern.id}
                     onFeedback={({ kind, note }) => void p.sendFeedback(kind, note, [])} />
        )}
      </div>
    </main>
  );
}
