import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import type { Buildability } from "../src/api/types";
import { IssueList } from "../src/components/IssueList";

const B: Buildability = {
  score: 86,
  confetti_pct: 5.51,
  n_components: 2,
  metrics: {},
  issues: [
    { type: "diagonal_link", cells: [[1, 1], [2, 2]], action: "bridge_with_clear",
      target_color: null, delta_e: null, patch_cells: [[1, 2]], severity: 1 },
    { type: "small_color", cells: [[0, 0]], action: "merge_color",
      target_color: 3, delta_e: 2.4, patch_cells: [[0, 0]], severity: 1 },
  ],
};

test("显示评分与 confetti%", () => {
  render(<IssueList buildability={B} onApply={() => {}} />);
  expect(screen.getByText("86")).toBeTruthy();
  expect(screen.getByText(/5\.51/)).toBeTruthy();
});

test("问题类型与动作显示成中文", () => {
  render(<IssueList buildability={B} onApply={() => {}} />);
  expect(screen.getByText(/对角虚连/)).toBeTruthy();
  expect(screen.getByText(/补透明豆/)).toBeTruthy();
  expect(screen.getByText(/小色号/)).toBeTruthy();
});

test("点击某条建议回调它的序号", async () => {
  const onApply = vi.fn();
  render(<IssueList buildability={B} onApply={onApply} />);
  const buttons = screen.getAllByRole("button", { name: /应用/ });
  await userEvent.click(buttons[1]);
  expect(onApply).toHaveBeenCalledWith(1);
});

test("零问题时说清楚而不是留空", () => {
  render(<IssueList buildability={{ ...B, issues: [], score: 100, confetti_pct: 0 }}
                    onApply={() => {}} />);
  expect(screen.getByText(/没有发现问题/)).toBeTruthy();
});

test("buildability 为 null 时提示分析不可用（出图本身没失败）", () => {
  render(<IssueList buildability={null} onApply={() => {}} />);
  expect(screen.getByText(/分析不可用/)).toBeTruthy();
});

test("applying 时按钮禁用防重复提交", () => {
  render(<IssueList buildability={B} applying onApply={() => {}} />);
  for (const b of screen.getAllByRole("button", { name: /应用/ })) {
    expect((b as HTMLButtonElement).disabled).toBe(true);
  }
});

test("还原度排在可拼性前面", () => {
  render(<IssueList buildability={B} onApply={() => {}}
                    fidelity={{ score: 84.8, mean_delta_e: 2.1, worst_delta_e: 13, method: "flat" }} />);
  const heads = screen.getAllByRole("heading").map((h) => h.textContent);
  expect(heads.indexOf("还原度")).toBeLessThan(heads.indexOf("可拼性"));
  expect(screen.getByText("84.8")).toBeTruthy();
  expect(screen.getByText(/按色块比/)).toBeTruthy();
});

test("旧图纸没有还原度：只显示可拼性，不出空的还原度块", () => {
  render(<IssueList buildability={B} onApply={() => {}} fidelity={null} />);
  expect(screen.queryByRole("heading", { name: "还原度" })).toBeNull();
});
