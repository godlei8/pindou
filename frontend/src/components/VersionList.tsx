import type { PatternBrief } from "../api/types";

interface Props {
  versions: PatternBrief[];
  currentId: string | null;
  disabled?: boolean;
  onSelect(id: string): void;
}

/** origin 是"怎么产生的"，和"基于哪张图"是两回事（后者看 ai_render_id）。 */
const ORIGIN_LABELS: Record<string, string> = {
  generated: "生成",
  edited: "手改",
  patched: "修复",
};

function timeLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  const sameDay = new Date().toDateString() === d.toDateString();
  return sameDay
    ? `${pad(d.getHours())}:${pad(d.getMinutes())}`
    : `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function VersionList({ versions, currentId, disabled, onSelect }: Props) {
  return (
    <section className="panel versions-panel">
      <h2>版本</h2>
      {versions.length === 0 ? (
        <p className="empty">还没有版本</p>
      ) : (
        <ul className="versions">
          {versions.map((v, i) => {
            const current = v.id === currentId;
            return (
              <li key={v.id}>
                <button type="button" className="version-row" aria-current={current || undefined}
                        disabled={disabled || current} onClick={() => onSelect(v.id)}
                        title={`${ORIGIN_LABELS[v.origin] ?? v.origin} · `
                          + `${v.ai_render_id ? "基于 AI 图" : "基于原图"}`}
                        aria-label={`第 ${versions.length - i} 版，`
                          + `${v.ai_render_id ? "基于 AI 图" : "基于原图"}，`
                          + `${ORIGIN_LABELS[v.origin] ?? v.origin}，`
                          + `还原度 ${v.fidelity ?? "未知"}，可拼性 ${v.score ?? "未知"}，${v.n_colors} 色`
                          + (current ? "，当前版本" : "")}>
                  {/* 列宽有限（左栏 260px），生成/手改/修复 只进 aria-label 和 title：
                      挑版本时先看的是评分和来源，不是它怎么来的 */}
                  {/* 主数字是还原度（第一优先）；旧图纸没有还原度，退回显示可拼性 */}
                  <span className="score">{v.fidelity ?? v.score ?? "—"}</span>
                  <span className="source">{v.ai_render_id ? "AI 图" : "原图"}</span>
                  <span className="colors">{v.n_colors} 色</span>
                  <span className="time">{current ? "当前" : timeLabel(v.created_at)}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
