import type { Buildability } from "../api/types";
import { FeedbackForm } from "./FeedbackForm";
import { ACTION_LABELS, ISSUE_LABELS } from "./labels";

interface Props {
  buildability: Buildability | null;
  applying?: boolean;
  onApply(issueIndex: number): void;
  onFeedback?(body: { kind: string; note: string }): void;
}

export function IssueList({ buildability, applying, onApply, onFeedback }: Props) {
  if (!buildability) {
    // 可拼性是附加环节：它失败了图纸照样能用，说清楚就行
    return (
      <section className="panel">
        <h2>可拼性</h2>
        <p className="empty">分析不可用，图纸仍可正常导出。</p>
        {onFeedback && <FeedbackForm onFeedback={onFeedback} />}
      </section>
    );
  }

  const { score, confetti_pct, n_components, issues } = buildability;
  return (
    <section className="panel">
      <h2>可拼性</h2>
      <p className="score">{score}<small>满分 100</small></p>
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
