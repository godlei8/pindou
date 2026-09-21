import type { Buildability, Fidelity } from "../api/types";
import { FeedbackForm } from "./FeedbackForm";
import { ACTION_LABELS, ISSUE_LABELS } from "./labels";

interface Props {
  buildability: Buildability | null;
  /** 还原度。旧图纸没有。 */
  fidelity?: Fidelity | null;
  applying?: boolean;
  onApply(issueIndex: number): void;
  onFeedback?(body: { kind: string; note: string }): void;
}

/** 还原度排在可拼性前面：先要像，再谈好不好拼。 */
function FidelityBlock({ fidelity }: { fidelity?: Fidelity | null }) {
  if (!fidelity) return null;
  return (
    <div className="fidelity">
      <h2>还原度</h2>
      <p className="score">{fidelity.score}<small>满分 100</small></p>
      <p className="empty">
        图纸和原图有多像（{fidelity.method === "flat" ? "按色块比" : "按远看的效果比"}）。
        格数越多越像；一格只能一个颜色，所以到不了 100。
      </p>
    </div>
  );
}

export function IssueList({ buildability, fidelity, applying, onApply, onFeedback }: Props) {
  if (!buildability) {
    // 可拼性是附加环节：它失败了图纸照样能用，说清楚就行
    return (
      <section className="panel">
        <FidelityBlock fidelity={fidelity} />
        <h2>可拼性</h2>
        <p className="empty">分析不可用，图纸仍可正常导出。</p>
        {onFeedback && <FeedbackForm onFeedback={onFeedback} />}
      </section>
    );
  }

  const { score, confetti_pct, n_components, issues } = buildability;
  return (
    <section className="panel">
      <FidelityBlock fidelity={fidelity} />
      <h2>可拼性</h2>
      <p className="score score-second">{score}<small>满分 100</small></p>
      <p className="empty">
        散点 {confetti_pct}%（&lt;2% 理想，&gt;10% 极难拼）· {n_components} 个连通块
      </p>

      {issues.length === 0 ? (
        <p className="empty">没有发现问题，可以直接拼。</p>
      ) : (
        <ul className="issues">
          {issues.map((it, i) => (
            <li key={`${it.type}-${i}`}>
              <span>{ISSUE_LABELS[it.type] ?? it.type}（{it.cells.length} 格）</span>
              <button type="button" disabled={applying} onClick={() => onApply(i)}>
                应用：{ACTION_LABELS[it.action] ?? it.action}
              </button>
            </li>
          ))}
        </ul>
      )}
      {onFeedback && <FeedbackForm onFeedback={onFeedback} />}
    </section>
  );
}
