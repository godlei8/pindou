import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { ExportButtons } from "../src/components/ExportButtons";
import { FeedbackForm } from "../src/components/FeedbackForm";
import { MaterialList } from "../src/components/MaterialList";
import { PalettePicker } from "../src/components/PalettePicker";
import { PatternCanvas } from "../src/components/PatternCanvas";
import { ToolBar } from "../src/components/ToolBar";
import type { EditorState } from "../src/hooks/useEditor";

const COLORS = new Map([[0, "#FF0000"], [1, "#00FF00"], [2, "#0000FF"]]);

describe("MaterialList", () => {
  const MATERIALS = [
    { index: 0, code: "H2", hex: "#FFFFFF", count: 1159, packs: 2 },
    { index: 1, code: "R10", hex: "#FFDD00", count: 858, packs: 1 },
  ];
  const renderList = (props: Partial<{ locating: number | null; onLocate: (i: number | null) => void }> = {}) =>
    render(<MaterialList materials={MATERIALS} locating={null} onLocate={() => {}} {...props} />);

  test("列出色号、颗数与包数", () => {
    renderList();
    expect(screen.getByText("H2")).toBeTruthy();
    expect(screen.getByText("1159")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
  });

  test("给出合计——买豆子的人不该自己逐行加", () => {
    renderList();
    expect(screen.getByText(/共 2017 颗 · 2 色 · 3 包/)).toBeTruthy();
  });

  test("点一行请求在图上定位这个色号，再点取消", async () => {
    const onLocate = vi.fn();
    const { rerender } = render(
      <MaterialList materials={MATERIALS} locating={null} onLocate={onLocate} />);
    await userEvent.click(screen.getByRole("button", { name: /定位 R10/ }));
    expect(onLocate).toHaveBeenCalledWith(1);

    rerender(<MaterialList materials={MATERIALS} locating={1} onLocate={onLocate} />);
    await userEvent.click(screen.getByRole("button", { name: /定位 R10/ }));
    expect(onLocate).toHaveBeenLastCalledWith(null);
  });

  test("占比条按最大色归一——否则色数一多全是看不见的细条", () => {
    const { container } = renderList();
    const bars = [...container.querySelectorAll(".share > span")] as HTMLElement[];
    expect(bars[0].style.width).toBe("100%");            // 1159 是最大的
    expect(parseFloat(bars[1].style.width)).toBeCloseTo(858 / 1159 * 100, 1);
  });

  test("空清单不崩", () => {
    expect(() => render(
      <MaterialList materials={[]} locating={null} onLocate={() => {}} />)).not.toThrow();
  });
});

describe("PalettePicker", () => {
  test("只显示工作色板里的色", () => {
    render(<PalettePicker colors={COLORS} working={[0, 2]} selected={null}
                          codeOf={(i) => `C${i}`} onSelect={() => {}} />);
    expect(screen.getAllByRole("button").length).toBe(2);
  });

  test("点击回调索引，选中项有 aria-pressed", async () => {
    const onSelect = vi.fn();
    render(<PalettePicker colors={COLORS} working={[0, 2]} selected={2}
                          codeOf={(i) => `C${i}`} onSelect={onSelect} />);
    const buttons = screen.getAllByRole("button");
    expect(buttons.find((b) => b.getAttribute("aria-pressed") === "true")).toBeTruthy();
    await userEvent.click(buttons[0]);
    expect(onSelect).toHaveBeenCalledWith(0);
  });
});

describe("ToolBar", () => {
  const state: EditorState = {
    grid: [[0]], tool: "brush", color: 0, protectedCells: [],
    dirty: false, canUndo: false, canRedo: false,
  };

  test("当前工具高亮", () => {
    render(<ToolBar state={{ ...state, tool: "bucket" }} onTool={() => {}} onUndo={() => {}}
                    onRedo={() => {}} onSave={() => {}} />);
    expect(screen.getByRole("button", { name: /油漆桶/ }).getAttribute("aria-pressed")).toBe("true");
  });

  test("没有改动时保存禁用、不显示未保存标识", () => {
    render(<ToolBar state={state} onTool={() => {}} onUndo={() => {}} onRedo={() => {}}
                    onSave={() => {}} />);
    expect((screen.getByRole("button", { name: /保存/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText(/未保存/)).toBeNull();
  });

  test("有改动时显示未保存标识且保存可用", () => {
    render(<ToolBar state={{ ...state, dirty: true }} onTool={() => {}} onUndo={() => {}}
                    onRedo={() => {}} onSave={() => {}} />);
    expect(screen.getByText(/未保存/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /保存/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  test("撤销重做按可用性禁用", () => {
    render(<ToolBar state={{ ...state, canUndo: true, canRedo: false }} onTool={() => {}}
                    onUndo={() => {}} onRedo={() => {}} onSave={() => {}} />);
    expect((screen.getByRole("button", { name: /撤销/ }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole("button", { name: /重做/ }) as HTMLButtonElement).disabled).toBe(true);
  });

  test("切工具回调", async () => {
    const onTool = vi.fn();
    render(<ToolBar state={state} onTool={onTool} onUndo={() => {}} onRedo={() => {}}
                    onSave={() => {}} />);
    await userEvent.click(screen.getByRole("button", { name: /吸管/ }));
    expect(onTool).toHaveBeenCalledWith("eyedropper");
  });
});

describe("PatternCanvas", () => {
  test("渲染一个尺寸正确的 canvas（jsdom 没有 2d 上下文，只验尺寸与事件）", () => {
    const { container } = render(
      <PatternCanvas grid={[[0, 1], [1, 0]]} colors={COLORS} cellPx={10}
                     onCellDown={() => {}} onCellEnter={() => {}} onPointerUp={() => {}} />,
    );
    const c = container.querySelector("canvas")!;
    expect(c.width).toBe(21);
    expect(c.height).toBe(21);
  });

  test("setPointerCapture 抛错时这一笔不能丢", async () => {
    // 浏览器实测：pointer 不是活动指针时 setPointerCapture 抛 NotFoundError，
    // 原来用 ?. 只防了"方法不存在"，防不住它抛错，整个 pointerdown 处理会被中断。
    const onCellDown = vi.fn();
    const { container } = render(
      <PatternCanvas grid={[[0, 1], [1, 0]]} colors={COLORS} cellPx={10}
                     onCellDown={onCellDown} onCellEnter={() => {}} onPointerUp={() => {}} />,
    );
    const c = container.querySelector("canvas")!;
    c.getBoundingClientRect = () => ({ left: 0, top: 0, width: 21, height: 21,
                                       right: 21, bottom: 21, x: 0, y: 0, toJSON: () => ({}) });
    c.setPointerCapture = () => { throw new DOMException("no active pointer", "NotFoundError"); };
    await userEvent.pointer({ target: c, coords: { clientX: 5, clientY: 5 },
                              keys: "[MouseLeft>]" });
    expect(onCellDown).toHaveBeenCalledWith(0, 0);
  });

  test("按下把像素坐标翻成格子坐标", async () => {
    const onCellDown = vi.fn();
    const { container } = render(
      <PatternCanvas grid={[[0, 1], [1, 0]]} colors={COLORS} cellPx={10}
                     onCellDown={onCellDown} onCellEnter={() => {}} onPointerUp={() => {}} />,
    );
    const c = container.querySelector("canvas")!;
    c.getBoundingClientRect = () => ({ left: 0, top: 0, width: 21, height: 21,
                                       right: 21, bottom: 21, x: 0, y: 0, toJSON: () => ({}) });
    await userEvent.pointer({ target: c, coords: { clientX: 15, clientY: 5 },
                              keys: "[MouseLeft>]" });
    expect(onCellDown).toHaveBeenCalledWith(0, 1);
  });
});

describe("ExportButtons", () => {
  test("PNG / PDF 链接指向导出端点", () => {
    render(<ExportButtons patternId="pat1" />);
    const png = screen.getByRole("link", { name: /PNG/ }) as HTMLAnchorElement;
    const pdf = screen.getByRole("link", { name: /PDF/ }) as HTMLAnchorElement;
    expect(png.getAttribute("href")).toContain("/api/patterns/pat1/export?format=png");
    expect(pdf.getAttribute("href")).toContain("format=pdf");
  });
});

describe("FeedbackForm", () => {
  test("默认收起——拼完才用得上，不占设计阶段的屏幕", () => {
    render(<FeedbackForm onFeedback={() => {}} />);
    expect(screen.getByText("实拼反馈").closest("details")!.open).toBe(false);
  });

  test("展开后能提交实拼反馈", async () => {
    const onFeedback = vi.fn();
    render(<FeedbackForm onFeedback={onFeedback} />);
    await userEvent.click(screen.getByText("实拼反馈"));
    await userEvent.selectOptions(screen.getByLabelText(/问题类型/), "断裂");
    await userEvent.type(screen.getByLabelText(/备注/), "发尾断了");
    await userEvent.click(screen.getByRole("button", { name: /提交反馈/ }));
    expect(onFeedback).toHaveBeenCalledWith({ kind: "断裂", note: "发尾断了" });
  });
});
