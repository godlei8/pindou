export type Cell = number | null;
export type Grid = Cell[][];

export interface User {
  id: string;
  username: string;
  ai_quota: number;
  ai_used: number;
  is_admin: boolean;
}

export interface PatternBrief {
  id: string;
  origin: string;
  parent_id: string | null;
  /** 这版基于哪张 AI 图。null = 基于原图。origin 说的是另一件事。 */
  ai_render_id: string | null;
  created_at: string;
  score: number | null;
  n_colors: number;
  /** 图纸尺寸（格）。首页卡片上写"58×44"，不能只写"58 格"。 */
  rows: number;
  cols: number;
}

export interface Project {
  id: string;
  name: string;
  created_at: string;
  patterns: PatternBrief[];
}

export interface Issue {
  type: string;
  cells: [number, number][];
  action: string;
  target_color: number | null;
  delta_e: number | null;
  patch_cells: [number, number][];
  severity: number;
}

export interface Buildability {
  score: number;
  confetti_pct: number;
  n_components: number;
  issues: Issue[];
  metrics: Record<string, number>;
}

export interface Material {
  index: number;
  code: string;
  hex: string;
  count: number;
  packs: number;
}

export interface PatternParams {
  grid_long_side: number;
  max_colors: number;
  smoothness: number;
  dither: boolean;
  palette_id: string;
  small_color_threshold: number;
  lock_outlines: boolean;
  protected_cells?: [number, number][];
  background_seed?: [number, number] | null;
  background_tolerance?: number;
  /** 自动去掉纯色背景：边缘一圈几乎同色时，背景不填豆。 */
  remove_background?: boolean;
}

export interface Pattern {
  id: string;
  project_id: string;
  parent_id: string | null;
  origin: string;
  /** 这张图纸是基于哪张 AI 重绘图算的。null = 基于原图。
   *  改参数重算时必须带上它，否则会悄悄退回原图。 */
  ai_render_id: string | null;
  /** 检测到人脸时：脸在这张图纸上有多宽，太窄时建议调到多少格。没检测到人脸为 null。 */
  face_hint?: FaceHint | null;
  /** 只有重算接口会带：这次顺手替换掉（删除）的过渡版本。 */
  replaced_id?: string | null;
  params: PatternParams;
  grid: Grid;
  color_stats: Record<string, number>;
  buildability: Buildability | null;
  materials: Material[];
  palette_id: string;
  created_at: string;
}

export interface PaletteColor {
  index: number;
  code: string;
  name: string;
  hex: string;
  role: string | null;
  confidence: string;
}

export interface StylePreset {
  id: string;
  name: string;
  prompt: string;
  version: number;
}

export interface Job {
  id: number;
  type: string;
  status: "pending" | "running" | "done" | "failed";
  result: { pattern_id?: string; ai_render_id?: string | null } | null;
  error: string | null;
  created_at: string;
}

export interface SizeSuggestion {
  long_side: number;
  rows: number;
  cols: number;
  detail_loss: number;
}

export interface EditCell {
  cell: [number, number];
  to: number | null;
}

export interface FaceHint {
  cells_wide: number;
  min_cells: number;
  too_small: boolean;
  suggested_long_side: number | null;
}
