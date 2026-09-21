import { useState } from "react";
import type { FormEvent } from "react";

import { api } from "../../api/client";
import type { AdminPreset, User } from "../../api/types";
import { Loading, errorText, useAdminData } from "./shared";

type Draft = Pick<AdminPreset, "name" | "prompt" | "sort_order" | "is_active">;
const BLANK: Draft = { name: "", prompt: "", sort_order: 100, is_active: true };

/** 一张预设的编辑表单。新建和修改共用。 */
function PresetForm({ initial, version, submitLabel, onSubmit }: {
  initial: Draft;
  version?: number;
  submitLabel: string;
  onSubmit(d: Draft): Promise<void>;
}) {
  const [d, setD] = useState<Draft>(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const dirty = JSON.stringify(d) !== JSON.stringify(initial);
  const id = initial.name || "new";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      await onSubmit({ ...d, name: d.name.trim(), prompt: d.prompt.trim() });
    } catch (x) {
      setErr(errorText(x));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className={`admin-preset${d.is_active ? "" : " dim"}`} onSubmit={submit}>
      <div className="admin-preset-row">
        <label>名称<input value={d.name} maxLength={64} required
                        onChange={(e) => setD({ ...d, name: e.target.value })} /></label>
        <label>排序<input type="number" min={0} max={10000} value={d.sort_order}
                        onChange={(e) => setD({ ...d, sort_order: Number(e.target.value) })} /></label>
        <label className="field-inline">
          <input type="checkbox" checked={d.is_active}
                 onChange={(e) => setD({ ...d, is_active: e.target.checked })} />
          前台可选
        </label>
        {version !== undefined && <span className="tag" title="改提示词会升一个版本">v{version}</span>}
      </div>
      <label htmlFor={`prompt-${id}`}>提示词</label>
      <textarea id={`prompt-${id}`} rows={3} value={d.prompt} maxLength={4000} required
                onChange={(e) => setD({ ...d, prompt: e.target.value })} />
      {err && <p className="error" role="alert">{err}</p>}
      <button type="submit" disabled={busy || !dirty || !d.name.trim() || !d.prompt.trim()}>
        {submitLabel}
      </button>
    </form>
  );
}

export function PresetsSection(_: { me: User }) {
  const { data, setData, error, reload } = useAdminData(api.admin.presets);
  const [newKey, setNewKey] = useState(0);     // 建完清空新建表单
  if (!data) return <Loading error={error} onRetry={reload} />;

  const sorted = (xs: AdminPreset[]) =>
    [...xs].sort((a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name));

  return (
    <>
      <p className="admin-meta">
        前台 AI 重绘的风格下拉框按「排序」从小到大列出启用的预设。
        改提示词会升一个版本：已经画好的图不变，之后的重绘按新提示词重新画、重新计费。
      </p>
      <details className="admin-new">
        <summary>新建风格</summary>
        <PresetForm key={newKey} initial={BLANK} submitLabel="新建"
                    onSubmit={async (d) => {
                      const made = await api.admin.createPreset(d);
                      setData(sorted([...data, made]));
                      setNewKey((k) => k + 1);
                    }} />
      </details>
      {data.length === 0 && <p className="empty">还没有风格预设，前台的 AI 重绘用不了。</p>}
      {data.map((p) => (
        // key 带上版本和内容：保存成功后用服务器返回的值重建表单，"未修改"状态才对
        <PresetForm key={`${p.id}-${p.version}-${p.name}-${p.sort_order}-${p.is_active}`}
                    initial={{ name: p.name, prompt: p.prompt, sort_order: p.sort_order,
                               is_active: p.is_active }}
                    version={p.version} submitLabel="保存"
                    onSubmit={async (d) => {
                      const next = await api.admin.patchPreset(p.id, d);
                      setData(sorted(data.map((x) => (x.id === p.id ? next : x))));
                    }} />
      ))}
    </>
  );
}
