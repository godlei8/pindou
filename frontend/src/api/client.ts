import type {
  EditCell, Job, PaletteColor, Pattern, PatternParams, Project, SizeSuggestion,
  StylePreset, User,
} from "./types";

const BASE = "/api";

export class ApiError extends Error {
  constructor(public status: number, public detail: string) {
    super(`HTTP ${status}: ${detail}`);
    this.name = "ApiError";
  }
}

/** 新出图用的默认参数。除 remove_background 外与 backend/app/core/types.py 保持一致。
 *
 *  remove_background 是唯一有意不同的：算法层默认关，保证旧图纸（参数里没这个键）的含义不变；
 *  产品默认开——拼豆一般拼一个"形状"不是一整块矩形，纯色底的图背景就不该填豆。
 *  照片边缘颜色不统一，后端会自动跳过，不会误删。 */
export const DEFAULT_PARAMS: PatternParams = {
  grid_long_side: 58,
  max_colors: 24,
  smoothness: 2.0,
  dither: false,
  palette_id: "mard",
  small_color_threshold: 10,
  lock_outlines: true,
  remove_background: true,
};

/** 从一张已有图纸取回它的参数。参数里缺的键按"当时的含义"补：
 *  去背景功能上线前的图纸没有 remove_background，它们当时就是没去背景的。 */
export function paramsOf(p: { params: Partial<PatternParams> }): PatternParams {
  return { ...DEFAULT_PARAMS, remove_background: false, ...p.params };
}

function readDetail(payload: unknown, fallback: string): string {
  if (typeof payload === "string" && payload.trim()) return payload.slice(0, 500);
  if (payload && typeof payload === "object" && "detail" in payload) {
    const d = (payload as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    // Pydantic 422：detail 是一个数组，拼成人能读的一行
    if (Array.isArray(d)) {
      return d
        .map((item) => {
          const loc = Array.isArray((item as { loc?: unknown }).loc)
            ? ((item as { loc: unknown[] }).loc).join(".")
            : "";
          const msg = String((item as { msg?: unknown }).msg ?? "");
          return loc ? `${loc}: ${msg}` : msg;
        })
        .join("；");
    }
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, { credentials: "include", ...init });
  if (resp.status === 204) return null as T;

  const text = await resp.text();
  let payload: unknown = text;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    /* 非 JSON（比如反代吐的 HTML 错误页），保留原文 */
  }
  if (!resp.ok) throw new ApiError(resp.status, readDetail(payload, resp.statusText || "请求失败"));
  return payload as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  // auth
  me: () => request<User>("/auth/me"),
  login: (username: string, password: string) =>
    postJson<User>("/auth/login", { username, password }),
  register: (username: string, password: string, invite_code: string) =>
    postJson<User>("/auth/register", { username, password, invite_code }),
  logout: () => request<null>("/auth/logout", { method: "POST" }),

  // projects
  listProjects: () => request<Project[]>("/projects"),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  createProject: (name: string, file: File) => {
    const fd = new FormData();
    fd.append("name", name);
    fd.append("file", file);
    // 不要手动设 Content-Type：那会丢掉 multipart 的 boundary
    return request<Project>("/projects", { method: "POST", body: fd });
  },
  renameProject: (id: string, name: string) =>
    request<Project>(`/projects/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  sourceUrl: (id: string) => `${BASE}/projects/${id}/source`,
  aiRenderUrl: (projectId: string, renderId: string) =>
    `${BASE}/projects/${projectId}/ai-renders/${renderId}/image`,
  suggestSizes: (id: string, base: number) =>
    request<SizeSuggestion[]>(`/projects/${id}/suggest-sizes?base=${base}`),
  generate: (id: string, body: {
    use_ai: boolean; style_preset_id?: string | null; provider?: string | null;
    params: Partial<PatternParams>;
  }) => postJson<Job>(`/projects/${id}/generate`, body),
  /** replaces：这段连续调参里上一次算出来的过渡版本，请后端用新结果替换它。
   *  后端会复核能不能删；真删了会在响应的 replaced_id 里告诉你。 */
  recompute: (id: string, params: Partial<PatternParams>, aiRenderId?: string | null,
              replaces?: string | null) =>
    postJson<Pattern>(`/projects/${id}/patterns`, {
      source: aiRenderId ? "ai" : "original",
      ai_render_id: aiRenderId ?? null,
      params,
      replaces: replaces ?? null,
    }),

  // patterns
  getJob: (id: number) => request<Job>(`/jobs/${id}`),
  getPattern: (id: string) => request<Pattern>(`/patterns/${id}`),
  /** 每格 1 像素的缩略图，要配 image-rendering: pixelated 放大。 */
  thumbUrl: (id: string) => `${BASE}/patterns/${id}/thumb`,
  applyPatch: (id: string, issue_index: number) =>
    postJson<Pattern>(`/patterns/${id}/apply-patch`, { issue_index }),
  applyEdits: (id: string, edits: EditCell[], protected_cells?: [number, number][]) =>
    postJson<Pattern>(`/patterns/${id}/edits`, { edits, protected_cells: protected_cells ?? null }),
  sendFeedback: (id: string, body: { kind: string; cells: [number, number][]; note?: string }) =>
    postJson<null>(`/patterns/${id}/feedback`, body),
  exportUrl: (id: string, opts: { format: "png" | "pdf"; cell_px?: number; bead_mm?: number }) => {
    const q = new URLSearchParams({ format: opts.format });
    if (opts.cell_px !== undefined) q.set("cell_px", String(opts.cell_px));
    if (opts.bead_mm !== undefined) q.set("bead_mm", String(opts.bead_mm));
    return `${BASE}/patterns/${id}/export?${q}`;
  },

  // meta
  listPaletteColors: (paletteId: string) =>
    request<PaletteColor[]>(`/palettes/${paletteId}/colors`),
  listStylePresets: () => request<StylePreset[]>("/style-presets"),
};
