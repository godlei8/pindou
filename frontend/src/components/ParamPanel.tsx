import type { FaceHint, PatternParams, SizeSuggestion } from "../api/types";
import { BEAD_MM, gridText, physicalText } from "../lib/size";

interface Props {
  params: PatternParams;
  sizes: SizeSuggestion[];
  /** 当前图纸的实际尺寸（格）。还没出图时为 null。 */
  current: { rows: number; cols: number } | null;
  /** 检测到的人脸在当前格数下有多宽。 */
  faceHint?: FaceHint | null;
  disabled?: boolean;
  onChange(next: PatternParams): void;
}

export function ParamPanel({ params, sizes, current, faceHint, disabled, onChange }: Props) {
  const set = <K extends keyof PatternParams>(k: K, v: PatternParams[K]) =>
    onChange({ ...params, [k]: v });

  return (
    <section className="panel">
      <h2>参数</h2>

      {/* 两个数字并排。原来各占一整行，一个参数面板吃掉右栏的一半高度，
          材料清单只剩表头。 */}
      <div className="field-pair">
        <div>
          <label htmlFor="grid">长边格数</label>
          <input id="grid" type="number" min={8} max={200} value={params.grid_long_side}
                 disabled={disabled}
                 onChange={(e) => set("grid_long_side", Number(e.target.value))} />
        </div>
        <div>
          <label htmlFor="colors">最多色数</label>
          <input id="colors" type="number" min={2} max={64} value={params.max_colors}
                 disabled={disabled}
                 onChange={(e) => set("max_colors", Number(e.target.value))} />
        </div>
      </div>

      {/* 精确尺寸：填的是"长边格数"，另一边按原图比例算出来。原来只能出图后自己去数。 */}
      {current && (
        <p className="size-readout" aria-live="polite">
          <b>{gridText(current.rows, current.cols)}</b>
          <span>实物 {physicalText(current.rows, current.cols)}（按 {BEAD_MM} mm 豆）</span>
        </p>
      )}

      {/* 脸太小是分辨率的极限：眉眼之间那条皮肤不到一格，算法怎么算眼睛都会糊。
          明确告诉用户调到多少格，而不是让他自己去试。 */}
      {faceHint?.too_small && faceHint.suggested_long_side && (
        <div className="face-hint" role="note">
          <p>
            检测到人脸，只有 <b>{faceHint.cells_wide} 格</b>宽。
            脸宽不到 {faceHint.min_cells} 格时五官容易糊，尤其是眼睛。
          </p>
          <button type="button" disabled={disabled}
                  onClick={() => set("grid_long_side", faceHint.suggested_long_side!)}>
            长边调到 {faceHint.suggested_long_side} 格
          </button>
        </div>
      )}

      {sizes.length > 0 && (
        <div className="sizes">
          {sizes.map((s) => (
            <button key={s.long_side} type="button" disabled={disabled}
                    aria-pressed={params.grid_long_side === s.long_side}
                    aria-label={`${gridText(s.rows, s.cols)}，实物 ${physicalText(s.rows, s.cols)}`}
                    title={`实物 ${physicalText(s.rows, s.cols)}`}
                    onClick={() => set("grid_long_side", s.long_side)}>
              {s.cols}×{s.rows}
            </button>
          ))}
        </div>
      )}

      <label htmlFor="lambda">平整度 λ</label>
      <input id="lambda" type="range" min={0} max={8} step={0.5} value={params.smoothness}
             disabled={disabled}
             onChange={(e) => set("smoothness", Number(e.target.value))} />
      <small>{params.smoothness === 0
        ? "0 = 纯最近色，等同市面工具的行为"
        : `λ=${params.smoothness}，越大散点越少、越平整`}</small>

      {/* 复选框和它的说明排一行，别竖着堆三层 */}
      <label className="field-inline" htmlFor="dither">
        <input id="dither" type="checkbox" checked={params.dither} disabled={disabled}
               onChange={(e) => set("dither", e.target.checked)} />
        抖动<small>开启会显著降低可拼性（散点变多）</small>
      </label>
    </section>
  );
}
