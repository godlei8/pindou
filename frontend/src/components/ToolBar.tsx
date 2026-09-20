import type { EditorState, Tool } from "../hooks/useEditor";
import { TOOL_LABELS } from "./labels";

interface Props {
  state: EditorState;
  saving?: boolean;
  onTool(t: Tool): void;
  onUndo(): void;
  onRedo(): void;
  onSave(): void;
}

const TOOLS: Tool[] = ["brush", "bucket", "eyedropper", "eraser", "protect"];

export function ToolBar({ state, saving, onTool, onUndo, onRedo, onSave }: Props) {
  return (
    <div className="toolbar">
      {TOOLS.map((t) => (
        <button key={t} type="button" aria-pressed={state.tool === t} onClick={() => onTool(t)}>
          {TOOL_LABELS[t]}
        </button>
      ))}
      <button type="button" disabled={!state.canUndo} onClick={onUndo}>撤销</button>
      <button type="button" disabled={!state.canRedo} onClick={onRedo}>重做</button>
      <button type="button" disabled={!state.dirty || saving} onClick={onSave}>
        {saving ? "保存中…" : "保存"}
      </button>
      {state.dirty && <span className="dirty">有未保存的改动</span>}
    </div>
  );
}
