import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError, api } from "../api/client";
import type { Project } from "../api/types";
import { IntroPanel } from "../components/IntroPanel";
import { ProjectCard } from "../components/ProjectCard";
import { SAMPLES } from "../components/samples";
import { NewTile, SampleTile } from "../components/StartTiles";
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

/** 首页：左栏介绍，右栏干活。
 *
 *  原来是一条投图横幅压在一列 960px 的网格上面，宽屏两边全空。
 *  现在左边固定讲清楚这是什么，右边铺满图纸网格、自己滚动，「新图纸」是网格第一格。 */
export function ProjectsPage() {
  const navigate = useNavigate();
  /** null = 还在加载。加载完才决定网格里放示例还是放项目，免得闪一下。 */
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

  const hasProjects = (projects?.length ?? 0) > 0;

  return (
    <main className="home">
      <IntroPanel />

      <section className="home-work" aria-labelledby="work-title">
        {/* 加载完才定标题：否则老用户会先闪一下「从这里开始」再变成「最近的图纸」 */}
        <h2 id="work-title" className="work-title">
          {projects === null ? "图纸"
            : hasProjects ? <>最近的图纸<small>{projects.length} 张</small></>
            : "从这里开始"}
        </h2>
        {error && <p role="alert" className="error">{error}</p>}

        {projects === null ? (
          <p className="loading">加载中…</p>
        ) : (
          <ul className="project-grid" aria-label="图纸">
            <NewTile busy={busy} onFile={start} />
            {hasProjects
              ? projects.map((p) => <ProjectCard key={p.id} project={p} onRename={rename} />)
              : SAMPLES.map((s) => (
                  <SampleTile key={s.file} sample={s} disabled={busy} onFile={start} />
                ))}
          </ul>
        )}
      </section>

      {/* 整页都能投，拖进来时给个明确的落点提示 */}
      {dragging && (
        <div className="drop-overlay" aria-hidden="true">
          <p>松手就开始出图</p>
        </div>
      )}
    </main>
  );
}
