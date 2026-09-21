import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, api } from "../api/client";
import type { Project } from "../api/types";
import { DropZone } from "../components/DropZone";
import { ProjectCard } from "../components/ProjectCard";
import { checkImage, useImageIntake } from "../hooks/useImageIntake";
import type { IntakeSource } from "../hooks/useImageIntake";

/** 上传前不再问名字（出结果前不该问任何问题），按来源给个能认出来的默认名，事后可改。 */
function defaultName(file: File, source: IntakeSource, label?: string): string {
  if (source === "sample" && label) return `示例 · ${label}`;
  if (source === "paste") {
    const d = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    return `截图 ${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }
  // 去掉扩展名：avatar.jpg → avatar
  return file.name.replace(/\.[^.]+$/, "") || "未命名";
}

export function ProjectsPage() {
  const navigate = useNavigate();
  /** null = 还在加载。加载完才决定投图区大还是小，免得老用户先看到一闪大区再缩回去。 */
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setProjects(await api.listProjects());
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
      setProjects([]);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  /** 投图 = 建项目 + 立刻进工作台。工作台自己会出第一张图纸，中间不停。 */
  const start = useCallback(async (file: File, source: IntakeSource, label?: string) => {
    const bad = checkImage(file);
    if (bad) { setError(bad); return; }
    setError("");
    setBusy(true);
    try {
      const proj = await api.createProject(defaultName(file, source, label), file);
      navigate(`/p/${proj.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
      setBusy(false);
    }
  }, [navigate]);

  const dragging = useImageIntake(start, !busy && projects !== null);

  async function rename(id: string, name: string) {
    const updated = await api.renameProject(id, name);
    setProjects((ps) => (ps ?? []).map((p) => (p.id === id ? updated : p)));
  }

  if (projects === null) return <main className="projects"><p className="loading">加载中…</p></main>;

  const hasProjects = projects.length > 0;

  return (
    <main className="projects">
      <h1 className="sr-only">拼豆图纸生成</h1>

      <DropZone compact={hasProjects} busy={busy} onFile={start} />
      {error && <p role="alert" className="error">{error}</p>}

      {hasProjects && (
        <section className="recent">
          <h2>最近的图纸</h2>
          <ul className="project-grid">
            {projects.map((p) => <ProjectCard key={p.id} project={p} onRename={rename} />)}
          </ul>
        </section>
      )}

      {/* 整页都能投，拖进来时给个明确的落点提示 */}
      {dragging && (
        <div className="drop-overlay" aria-hidden="true">
          <p>松手就开始出图</p>
        </div>
      )}
    </main>
  );
}
