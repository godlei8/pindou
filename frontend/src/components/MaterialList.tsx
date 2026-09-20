import type { Material } from "../api/types";

export function MaterialList({ materials }: { materials: Material[] }) {
  return (
    <section className="panel">
      <h2>材料清单</h2>
      {materials.length === 0 ? (
        <p className="empty">暂无</p>
      ) : (
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
      )}
    </section>
  );
}
