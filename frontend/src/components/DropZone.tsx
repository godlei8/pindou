import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";

import { ACCEPTED_TYPES } from "../hooks/useImageIntake";
import type { IntakeSource } from "../hooks/useImageIntake";

/** 自己画的示例图（版权干净），选的都是拼豆最常见的题材。 */
export const SAMPLES = [
  { file: "strawberry.png", label: "草莓" },
  { file: "cat.png", label: "小猫" },
  { file: "mushroom.png", label: "蘑菇" },
] as const;

interface Props {
  /** 已经有项目时收成一条，把位置让给最近的图纸。 */
  compact?: boolean;
  busy?: boolean;
  onFile(file: File, source: IntakeSource, label?: string): void;
}

export function DropZone({ compact, busy, onFile }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [loadingSample, setLoadingSample] = useState<string | null>(null);

  const pick = () => { if (!busy) input.current?.click(); };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); }
  };

  async function useSample(s: (typeof SAMPLES)[number]) {
    if (busy) return;
    setLoadingSample(s.file);
    try {
      const blob = await fetch(`/samples/${s.file}`).then((r) => r.blob());
      onFile(new File([blob], s.file, { type: "image/png" }), "sample", s.label);
    } finally {
      setLoadingSample(null);
    }
  }

  return (
    <section className={`dropzone${compact ? " is-compact" : ""}${busy ? " is-busy" : ""}`}>
      <div className="dropzone-target" role="button" tabIndex={busy ? -1 : 0}
           aria-disabled={busy} aria-label="选一张图片开始出图"
           onClick={pick} onKeyDown={onKey}>
        {busy ? (
          <p className="dropzone-main">正在上传…</p>
        ) : (
          <>
            <p className="dropzone-main">把图片拖到这里</p>
            <p className="dropzone-sub">
              或者 <span className="btn primary dropzone-pick">选一张图</span>
              ，也可以直接 <kbd>Ctrl</kbd>+<kbd>V</kbd> 粘贴截图
            </p>
            {!compact && <p className="dropzone-hint">PNG / JPG / WebP，20 MB 以内</p>}
          </>
        )}
        <input ref={input} type="file" hidden accept={ACCEPTED_TYPES.join(",")}
               onChange={(e) => {
                 const f = e.target.files?.[0];
                 e.target.value = "";          // 同一张图再选一次也要触发
                 if (f) onFile(f, "pick");
               }} />
      </div>

      {!compact && (
        <div className="samples">
          <p>没有图？先拿这几张试试：</p>
          <ul>
            {SAMPLES.map((s) => (
              <li key={s.file}>
                <button type="button" disabled={busy || loadingSample !== null}
                        onClick={() => void useSample(s)}
                        aria-label={`用示例图「${s.label}」开始`}>
                  <img src={`/samples/${s.file}`} alt="" />
                  <span>{loadingSample === s.file ? "载入中…" : s.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
