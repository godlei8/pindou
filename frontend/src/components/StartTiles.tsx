import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { ACCEPTED_TYPES } from "../hooks/useImageIntake";
import type { IntakeSource } from "../hooks/useImageIntake";
import type { Sample } from "./samples";

type OnFile = (file: File, source: IntakeSource, label?: string) => void;

/** 「+」由五颗豆子拼成——和登录页的草莓同一种画法：没熨烫的豆子从上往下看是个环。 */
const PLUS = [".X.", "XXX", ".X."];

function BeadPlus() {
  return (
    <span className="bead-plus" aria-hidden="true">
      {PLUS.map((row, r) => (
        <span className="bead-plus-row" key={r}>
          {[...row].map((ch, c) => (
            <span key={c} className={ch === "X" ? "bead" : "bead is-empty"}
                  style={ch === "X" ? { "--bead": "var(--bead-red)" } as React.CSSProperties
                                    : undefined} />
          ))}
        </span>
      ))}
    </span>
  );
}

/** 网格里的第一张卡片：开始一张新图纸。
 *
 *  不再单独占一条横幅——像在线文档的首页那样，"新建"就是网格里的第一格，
 *  不额外占高度，也最容易找到。整页拖拽和 Ctrl+V 粘贴照样在别处生效。 */
export function NewTile({ busy, onFile }: { busy?: boolean; onFile: OnFile }) {
  const input = useRef<HTMLInputElement>(null);
  const pick = () => { if (!busy) input.current?.click(); };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); }
  };

  return (
    <li className="project-card tile-new">
      <div className="card-body" role="button" tabIndex={busy ? -1 : 0}
           aria-disabled={busy} aria-label="开始一张新图纸：选一张图片"
           onClick={pick} onKeyDown={onKey}>
        <span className="thumb tile-new-thumb"><BeadPlus /></span>
        <span className="name">{busy ? "正在上传…" : "新图纸"}</span>
        {/* 点卡片就能选图是显然的，不用写；写不显然的：可以拖、可以粘贴 */}
        <span className="meta hint-pointer">拖进来，或 <span><kbd>Ctrl</kbd>+<kbd>V</kbd> 粘贴</span></span>
        {/* 手机上没有拖拽和 Ctrl+V，换成手机上真能做的 */}
        <span className="meta hint-touch">从相册选，或拍一张</span>
      </div>
      <input ref={input} type="file" hidden accept={ACCEPTED_TYPES.join(",")}
             onChange={(e) => {
               const f = e.target.files?.[0];
               e.target.value = "";          // 同一张图再选一次也要触发
               if (f) onFile(f, "pick");
             }} />
    </li>
  );
}

/** 没有项目时，示例图作为卡片排在「新图纸」旁边——和项目卡片同一种样子。 */
export function SampleTile({ sample, disabled, onFile }: {
  sample: Sample; disabled?: boolean; onFile: OnFile;
}) {
  const [loading, setLoading] = useState(false);

  async function use() {
    if (disabled || loading) return;
    setLoading(true);
    try {
      const blob = await fetch(`/samples/${sample.file}`).then((r) => r.blob());
      onFile(new File([blob], sample.file, { type: "image/png" }), "sample", sample.label);
    } finally {
      setLoading(false);
    }
  }

  return (
    <li className="project-card tile-sample">
      <button type="button" className="card-body" disabled={disabled || loading}
              onClick={() => void use()} aria-label={`用示例图「${sample.label}」开始`}>
        <span className="thumb"><img src={`/samples/${sample.file}`} alt="" /></span>
        <span className="name">示例 · {sample.label}</span>
        <span className="meta">{loading ? "载入中…" : "没有图？先用这张试试"}</span>
      </button>
    </li>
  );
}
