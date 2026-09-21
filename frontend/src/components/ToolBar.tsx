import type { ReactNode } from "react";

import type { EditorState, Tool } from "../hooks/useEditor";
import { TOOL_LABELS } from "./labels";

interface Props {
  state: EditorState;
  saving?: boolean;
  onTool(t: Tool): void;
  onUndo(): void;
  onRedo(): void;
  onSave(): void;
  /** 额外的操作组（导出按钮）。同属"对图纸做点什么"，排在一起。 */
  extra?: ReactNode;
}

const TOOLS: Tool[] = ["brush", "bucket", "eyedropper", "eraser", "protect"];

export function ToolBar({ state, saving, onTool, onUndo, onRedo, onSave, extra }: Props) {
  return (
    <div className="toolbar">
      {/* 工具和操作是两类东西，别排成一排等重的按钮 */}
      <div className="toolbar-group" role="group" aria-label="工具">
        {TOOLS.map((t) => (
          <button key={t} type="button" aria-pressed={state.tool === t} onClick={() => onTool(t)}>
            {TOOL_LABELS[t]}
          </button>
        ))}
      </div>

      <div className="toolbar-group" role="group" aria-label="操作">
        <button type="button" disabled={!state.canUndo} onClick={onUndo}>撤销</button>
        <button type="button" disabled={!state.canRedo} onClick={onRedo}>重做</button>
        <button type="button" className={state.dirty ? "primary" : undefined}
                disabled={!state.dirty || saving} onClick={onSave}>
          {saving ? "保存中…" : "保存"}
        </button>
        {/* 紧挨着保存按钮——原来靠 margin-left:auto 甩到最右边，
            宽屏下和保存隔着一千多像素，等于没提示 */}
        {state.dirty && <span className="dirty">有未保存的改动</span>}
      </div>

      {extra}
    </div>
  );
}
