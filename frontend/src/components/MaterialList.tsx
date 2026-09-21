import type { Material } from "../api/types";

interface Props {
  materials: Material[];
  /** 正在图上定位的色号索引。null = 没在定位。 */
  locating: number | null;
  onLocate(index: number | null): void;
}

export function MaterialList({ materials, locating, onLocate }: Props) {
  const beads = materials.reduce((s, m) => s + m.count, 0);
  const packs = materials.reduce((s, m) => s + m.packs, 0);
  const max = materials.reduce((s, m) => Math.max(s, m.count), 0);

  return (
    <section className="panel materials-panel">
      <h2>材料清单</h2>
      {materials.length === 0 ? (
        <p className="empty">暂无</p>
      ) : (
        <>
          {/* 买豆子的人关心的是总数和要买几包，不是逐行去加 */}
          <p className="materials-total">
            共 {beads} 颗 · {materials.length} 色 · {packs} 包
          </p>
          {/* 单位提到表头，省掉每行重复的"颗""包" */}
          <p className="materials-head" aria-hidden="true">
            <span className="code">色号</span>
            <span className="share">占比</span>
            <span className="count">颗</span>
            <span className="packs">包</span>
          </p>
          <ul className="materials">
            {materials.map((m) => {
              const pct = beads > 0 ? (m.count / beads) * 100 : 0;
              const on = locating === m.index;
              return (
                <li key={m.index}>
                  <button
                    type="button"
                    className="material-row"
                    aria-pressed={on}
                    // 行内是四个零散数字，读屏念出来是"R10 1159 1"。给个完整描述。
                    aria-label={`定位 ${m.code}，${m.count} 颗，${m.packs} 包，占 ${pct.toFixed(1)}%`}
                    title={`在图上定位 ${m.code}`}
                    onClick={() => onLocate(on ? null : m.index)}
                  >
                    <i style={{ background: m.hex }} aria-hidden="true" />
                    <span className="code">{m.code}</span>
                    {/* 条长按最大色归一，不按总数——否则色数一多全是看不见的细条 */}
                    <span className="share" aria-hidden="true">
                      <span style={{ width: `${max > 0 ? (m.count / max) * 100 : 0}%` }} />
                    </span>
                    <span className="count">{m.count}</span>
                    <span className="packs">{m.packs}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
