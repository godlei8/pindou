import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError, api } from "../api/client";
import type { Project } from "../api/types";

interface Props {
  project: Project;
  onRename(id: string, name: string): Promise<void>;
}

function dateLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function ProjectCard({ project, onRename }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(project.name);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const saving = useRef(false);
  const latest = project.patterns[0];

  // 进入改名就全选：改名几乎总是整个换掉，光标停在末尾只会让新名字追加到旧名字后面
  useEffect(() => { if (editing) input.current?.select(); }, [editing]);

  async function save(e?: FormEvent) {
    e?.preventDefault();
    // 回车保存后输入框卸载，可能再补一次 blur——别为同一次改名发两个请求
    if (saving.current) return;
    const name = draft.trim();
    if (!name || name === project.name) { setEditing(false); setDraft(project.name); return; }
    saving.current = true;
    try {
      await onRename(project.id, name);
      setEditing(false);
      setError("");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      saving.current = false;
    }
  }

  function onKey(e: KeyboardEvent) {
    // 拼音输入法选字时：回车是确认候选字，Esc 是取消拼音。这时候都不该当成我们的快捷键。
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Enter") {
      // 显式处理，不靠表单的隐式提交——那个在真浏览器里实测并不可靠
      e.preventDefault();
      void save();
    } else if (e.key === "Escape") {
      setEditing(false); setDraft(project.name); setError("");
    }
  }

  // 重新进站的人靠认图，不是认文件名——两个都叫 avatar.jpg 的项目原来根本分不出来。
  // 有图纸就显示图纸本身（每格 1 像素，浏览器按 pixelated 放大），还没出图就退回原图。
  const thumb = (
    <span className="thumb">
      <img src={latest ? api.thumbUrl(latest.id) : api.sourceUrl(project.id)}
           className={latest ? "is-pattern" : undefined} alt="" loading="lazy" />
    </span>
  );

  const meta = (
    <span className="meta">
      {project.patterns.length} 个版本
      {latest?.score != null && <> · 可拼性 {latest.score}</>}
      {" · "}{dateLabel(project.created_at)}
    </span>
  );

  if (editing) {
    return (
      <li className="project-card is-editing">
        <form className="card-body" onSubmit={save}>
          {thumb}
          <input ref={input} aria-label="项目名" value={draft} autoFocus maxLength={100}
                 onChange={(e) => setDraft(e.target.value)}
                 onKeyDown={onKey} onBlur={() => void save()} />
          {error ? <span role="alert" className="card-error">{error}</span> : meta}
        </form>
      </li>
    );
  }

  return (
    <li className="project-card">
      <Link to={`/p/${project.id}`} className="card-body">
        {thumb}
        <span className="name">{project.name}</span>
        {meta}
      </Link>
      {/* 改名按钮在链接外面：按钮嵌在链接里，键盘和读屏都会乱 */}
      <button type="button" className="card-rename" aria-label={`重命名「${project.name}」`}
              onClick={() => { setDraft(project.name); setEditing(true); }}>改名</button>
    </li>
  );
}
