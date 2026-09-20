import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { ApiError, api } from "../api/client";
import type { Project } from "../api/types";

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setProjects(await api.listProjects());
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : String(e));
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function upload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError("");
    setBusy(true);
    try {
      await api.createProject(name || file.name, file);
      setName("");
      setFile(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="projects">
      <h1>我的项目</h1>

      <form onSubmit={upload} className="upload">
        <label htmlFor="file">图片</label>
        <input id="file" type="file" accept="image/png,image/jpeg,image/webp"
               onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <label htmlFor="name">项目名</label>
        <input id="name" value={name} onChange={(e) => setName(e.target.value)}
               placeholder="不填就用文件名" />
        <button type="submit" disabled={!file || busy}>上传</button>
      </form>

      {error && <p role="alert" className="error">{error}</p>}

      {projects.length === 0 ? (
        <p className="empty">还没有项目。上传一张图片开始吧。</p>
      ) : (
        <ul className="project-list">
          {projects.map((p) => {
            const latest = p.patterns[0];
            return (
              <li key={p.id}>
                <Link to={`/p/${p.id}`}>
                  <strong>{p.name}</strong>
                  <span>{p.patterns.length} 个版本</span>
                  {latest?.score != null && <span>可拼性 {latest.score}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}
