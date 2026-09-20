import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { StylePreset } from "../api/types";
import { useAuth } from "../hooks/useAuth";
import type { AiPhase } from "../hooks/usePattern";

interface Props {
  projectId: string;
  projectName: string;
  aiRenderId: string | null;
  aiPhase: AiPhase;
  aiError: string;
  busy?: boolean;
  onGenerate(stylePresetId: string): void;
  onDismissError(): void;
}

const PHASE_TEXT: Record<AiPhase, string> = {
  idle: "",
  queued: "排队中…",
  running: "AI 出图中…",
  failed: "",
};

export function SourcePanel(props: Props) {
  const { projectId, projectName, aiRenderId, aiPhase, aiError, busy } = props;
  const { user, refresh } = useAuth();
  const [presets, setPresets] = useState<StylePreset[]>([]);
  const [preset, setPreset] = useState("");
  const [view, setView] = useState<"original" | "ai">("original");

  useEffect(() => {
    api.listStylePresets()
      .then((list) => {
        setPresets(list);
        setPreset((cur) => cur || list[0]?.id || "");
      })
      .catch(() => { /* 没有预设就只能不用 AI，不是错误 */ });
  }, []);

  // 出图成功后自动切到 AI 图——用户刚花了额度，当然想先看这张
  useEffect(() => {
    if (aiRenderId) setView("ai");
  }, [aiRenderId]);

  // 额度是在后端扣的，出完图要把顶栏的数字同步过来
  useEffect(() => {
    if (aiPhase === "idle" && aiRenderId) void refresh();
  }, [aiPhase, aiRenderId, refresh]);

  const remaining = user ? user.ai_quota - user.ai_used : 0;
  const working = aiPhase === "queued" || aiPhase === "running";
  const canGenerate = !!preset && !working && !busy && remaining > 0;

  return (
    <section className="panel">
      <h2>原图</h2>

      {aiRenderId && (
        <div className="toolbar" role="tablist" aria-label="图片来源">
          <button type="button" role="tab" aria-selected={view === "original"}
                  aria-pressed={view === "original"}
                  onClick={() => setView("original")}>原图</button>
          <button type="button" role="tab" aria-selected={view === "ai"}
                  aria-pressed={view === "ai"}
                  onClick={() => setView("ai")}>AI 图</button>
        </div>
      )}

      <img
        src={view === "ai" && aiRenderId
          ? api.aiRenderUrl(projectId, aiRenderId)
          : api.sourceUrl(projectId)}
        alt={view === "ai" ? `${projectName}的 AI 重绘图` : projectName}
      />

      <h2>AI 重绘</h2>
      <p className="empty">
        先让 AI 把图重画成适合拼的样子：粗轮廓、纯色平涂、少渐变。
      </p>

      <label htmlFor="preset">风格</label>
      <select id="preset" value={preset} disabled={working || presets.length === 0}
              onChange={(e) => setPreset(e.target.value)}>
        {presets.length === 0 && <option value="">（暂无可用风格）</option>}
        {presets.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>

      <div className="ai-actions">
        <button type="button" className="primary" disabled={!canGenerate}
                onClick={() => props.onGenerate(preset)}>
          {working ? PHASE_TEXT[aiPhase] : "用 AI 重绘"}
        </button>
        <small>剩余额度 {remaining}/{user?.ai_quota ?? 0}</small>
      </div>

      {working && (
        <p className="ai-progress" role="status">
          <span className="ai-dots" aria-hidden="true"><i /><i /><i /></span>
          {PHASE_TEXT[aiPhase]}一般要半分钟到两分钟，这期间可以先不动。
        </p>
      )}

      {remaining <= 0 && !working && (
        <p className="empty">额度用完了。不用 AI 也能直接出图——调右侧参数即可。</p>
      )}

      {aiPhase === "failed" && (
        <p role="alert" className="error">
          {aiError}
          <button type="button" onClick={props.onDismissError}>知道了</button>
        </p>
      )}
    </section>
  );
}
