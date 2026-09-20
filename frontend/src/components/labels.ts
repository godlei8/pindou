export const ISSUE_LABELS: Record<string, string> = {
  disconnected: "不连通",
  isolated_bead: "孤立豆",
  diagonal_link: "对角虚连",
  thin_line: "细线易断",
  hole: "内部空洞",
  small_color: "小色号",
};

export const ACTION_LABELS: Record<string, string> = {
  bridge_with_clear: "补透明豆桥",
  fill_with_clear: "用透明豆填充",
  merge_color: "并入最近色",
  remove: "删除",
  none: "暂无建议",
};

export const TOOL_LABELS: Record<string, string> = {
  brush: "画笔",
  bucket: "油漆桶",
  eyedropper: "吸管",
  eraser: "橡皮",
  protect: "保护标记",
};

export const FEEDBACK_KINDS = ["断裂", "掉豆", "色差", "难数格"] as const;
