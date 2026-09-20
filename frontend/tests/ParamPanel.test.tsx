import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, test, vi } from "vitest";

import { DEFAULT_PARAMS } from "../src/api/client";
import type { PatternParams } from "../src/api/types";
import { ParamPanel } from "../src/components/ParamPanel";

const SIZES = [
  { long_side: 44, detail_loss: 0.0116 },
  { long_side: 58, detail_loss: 0.0092 },
  { long_side: 87, detail_loss: 0.006 },
];

test("展示当前参数值", () => {
  render(<ParamPanel params={DEFAULT_PARAMS} sizes={[]} onChange={() => {}} />);
  expect((screen.getByLabelText(/格数/) as HTMLInputElement).value).toBe("58");
  expect((screen.getByLabelText(/色数/) as HTMLInputElement).value).toBe("24");
  expect((screen.getByLabelText(/平整度/) as HTMLInputElement).value).toBe("2");
});

/** ParamPanel 是受控组件：不给它一个 state 容器，输入框会被旧 props 拽回去。 */
function Controlled({ onChange }: { onChange?: (p: PatternParams) => void }) {
  const [params, setParams] = useState<PatternParams>(DEFAULT_PARAMS);
  return (
    <ParamPanel params={params} sizes={SIZES}
                onChange={(p) => { setParams(p); onChange?.(p); }} />
  );
}

test("改格数会回调新参数", async () => {
  const onChange = vi.fn();
  render(<Controlled onChange={onChange} />);
  const input = screen.getByLabelText(/格数/) as HTMLInputElement;
  await userEvent.clear(input);
  await userEvent.type(input, "40");
  expect(onChange).toHaveBeenCalled();
  expect(onChange.mock.calls.at(-1)![0].grid_long_side).toBe(40);
  expect(input.value).toBe("40");
});

test("勾抖动会回调 dither=true", async () => {
  const onChange = vi.fn();
  render(<Controlled onChange={onChange} />);
  await userEvent.click(screen.getByLabelText(/抖动/));
  expect(onChange.mock.calls.at(-1)![0].dither).toBe(true);
});

test("λ=0 标注成市面工具行为，抖动标注降低可拼性", () => {
  render(<ParamPanel params={{ ...DEFAULT_PARAMS, smoothness: 0 }} sizes={[]}
                     onChange={() => {}} />);
  expect(screen.getByText(/最近色/)).toBeTruthy();
  expect(screen.getByText(/降低可拼性/)).toBeTruthy();
});

test("尺寸推荐可一键采用", async () => {
  const onChange = vi.fn();
  render(<ParamPanel params={DEFAULT_PARAMS} sizes={SIZES} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: /87/ }));
  expect(onChange.mock.calls.at(-1)![0].grid_long_side).toBe(87);
});

test("disabled 时所有输入禁用", () => {
  render(<ParamPanel params={DEFAULT_PARAMS} sizes={SIZES} disabled onChange={() => {}} />);
  expect((screen.getByLabelText(/格数/) as HTMLInputElement).disabled).toBe(true);
  expect((screen.getByLabelText(/抖动/) as HTMLInputElement).disabled).toBe(true);
});
