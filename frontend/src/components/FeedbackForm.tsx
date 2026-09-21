import { useState } from "react";

import { FEEDBACK_KINDS } from "./labels";

/** 实拼反馈：拼完之后才会做的事，默认收起来，别占设计阶段的屏幕。
 *  放在可拼性面板里——它反馈的正是可拼性判断准不准。 */
export function FeedbackForm({ onFeedback }: {
  onFeedback(body: { kind: string; note: string }): void;
}) {
  const [kind, setKind] = useState<string>(FEEDBACK_KINDS[0]);
  const [note, setNote] = useState("");

  return (
    <details className="feedback">
      <summary>实拼反馈</summary>
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
    </details>
  );
}
