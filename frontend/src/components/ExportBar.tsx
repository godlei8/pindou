import { useState } from "react";

import { api } from "../api/client";
import { FEEDBACK_KINDS } from "./labels";

interface Props {
  patternId: string;
  onFeedback(body: { kind: string; note: string }): void;
}

export function ExportBar({ patternId, onFeedback }: Props) {
  const [kind, setKind] = useState<string>(FEEDBACK_KINDS[0]);
  const [note, setNote] = useState("");

  return (
    <section className="panel">
      <h2>导出</h2>
      <div className="toolbar">
        <a href={api.exportUrl(patternId, { format: "png", cell_px: 28 })} download>
          下载 PNG
        </a>
        <a href={api.exportUrl(patternId, { format: "pdf", bead_mm: 5 })} download>
          下载 PDF（1:1 可打印）
        </a>
      </div>

      <h2>实拼反馈</h2>
      <label htmlFor="fb-kind">问题类型</label>
      <select id="fb-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
        {FEEDBACK_KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
      </select>
      <label htmlFor="fb-note">备注</label>
      <input id="fb-note" value={note} onChange={(e) => setNote(e.target.value)}
             placeholder="哪里出的问题" />
      <button type="button" onClick={() => { onFeedback({ kind, note }); setNote(""); }}>
        提交反馈
      </button>
    </section>
  );
}
