import type { Material } from "../api/types";

export function MaterialList({ materials }: { materials: Material[] }) {
  const beads = materials.reduce((s, m) => s + m.count, 0);
  const packs = materials.reduce((s, m) => s + m.packs, 0);

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
          <ul className="materials">
            {materials.map((m) => (
              <li key={m.index}>
                <i style={{ background: m.hex }} aria-hidden="true" />
                <span className="code">{m.code}</span>
                <span className="count">{m.count} 颗</span>
                <span className="packs">{m.packs} 包</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
