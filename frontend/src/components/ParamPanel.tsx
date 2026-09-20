import type { PatternParams, SizeSuggestion } from "../api/types";

interface Props {
  params: PatternParams;
  sizes: SizeSuggestion[];
  disabled?: boolean;
  onChange(next: PatternParams): void;
}

export function ParamPanel({ params, sizes, disabled, onChange }: Props) {
  const set = <K extends keyof PatternParams>(k: K, v: PatternParams[K]) =>
    onChange({ ...params, [k]: v });

  return (
    <section className="panel">
      <h2>参数</h2>

      <label htmlFor="grid">长边格数</label>
      <input id="grid" type="number" min={8} max={200} value={params.grid_long_side}
             disabled={disabled}
             onChange={(e) => set("grid_long_side", Number(e.target.value))} />

      {sizes.length > 0 && (
        <div className="toolbar">
          {sizes.map((s) => (
            <button key={s.long_side} type="button" disabled={disabled}
                    onClick={() => set("grid_long_side", s.long_side)}>
              {s.long_side} 格
            </button>
          ))}
        </div>
      )}

      <label htmlFor="colors">最多色数</label>
      <input id="colors" type="number" min={2} max={64} value={params.max_colors}
             disabled={disabled}
             onChange={(e) => set("max_colors", Number(e.target.value))} />

      <label htmlFor="lambda">平整度 λ</label>
      <input id="lambda" type="range" min={0} max={8} step={0.5} value={params.smoothness}
             disabled={disabled}
             onChange={(e) => set("smoothness", Number(e.target.value))} />
      <small>{params.smoothness === 0
        ? "0 = 纯最近色，等同市面工具的行为"
        : `λ=${params.smoothness}，越大散点越少、越平整`}</small>

      <label htmlFor="dither">抖动</label>
      <input id="dither" type="checkbox" checked={params.dither} disabled={disabled}
             onChange={(e) => set("dither", e.target.checked)} />
      <small>开启会显著降低可拼性（散点变多）</small>
    </section>
  );
}
