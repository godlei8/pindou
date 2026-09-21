import { INTRO_EXAMPLE as EX } from "./introExample";

/** 首页左栏：这工具做什么、和别家差在哪。
 *
 *  不用"三张功能卡片"——那是任何产品首页都长的样子。这里直接摆一张**真实输出**
 *  （流水线跑出来的，见 backend/scripts/make_intro_example.py），在图上标出要讲的东西。
 *  标注只说图上确实成立的事；"比别家干净"这种判断放在正文里讲，不拿这张图去证明。 */

/** 图上格子的尺寸（百分比），用来画"就是这一格"的方框。 */
const CELL_W = (18 / EX.width) * 100;
const CELL_H = (18 / EX.height) * 100;

function Badge({ n }: { n: number }) {
  return <span className="mark-badge" aria-hidden="true">{n}</span>;
}

export function IntroPanel() {
  const { markers } = EX;
  return (
    <aside className="intro" aria-labelledby="intro-title">
      <h1 id="intro-title" className="intro-title">
        把一张图，<br />变成拼得出来的图纸
      </h1>
      <p className="intro-lead">
        不是把照片打成马赛克。每一格都用买得到的 MARD 色号，同色尽量连成一片；
        出图前先检查哪里拼不牢——孤立的豆、断开的块、只靠一个角连着的地方，
        都会标出来，能一键补上。
      </p>

      <figure className="intro-example">
        <div className="intro-sheet">
          <img src="/intro/mushroom-sheet.png" width={EX.width} height={EX.height}
               alt={`示例：一朵蘑菇生成的 ${EX.grid[0]}×${EX.grid[1]} 格图纸，每格印着色号，`
                 + `底下是材料清单，共 ${EX.beads} 颗、${EX.colors} 种颜色`} />

          {/* 原图钉在右上角：一眼看出"给它这个，得到这个"。那一角是背景格，不挡内容 */}
          <span className="intro-source">
            <img src="/intro/mushroom-source.png" alt="" />
            <span>原图</span>
          </span>

          <span className="mark-ring" aria-hidden="true" style={{
            left: `${markers.code.x}%`, top: `${markers.code.y}%`,
            width: `${CELL_W}%`, height: `${CELL_H}%`,
          }} />
          <span className="mark-at mark-at-code"
                style={{ left: `${markers.code.x}%`, top: `${markers.code.y}%` }}>
            <Badge n={1} />
          </span>
          <span className="mark-at mark-at-legend"
                style={{ left: `${markers.legend.x}%`, top: `${markers.legend.y}%` }}>
            <Badge n={2} />
          </span>
        </div>
        <figcaption>
          示例 · {EX.grid[0]}×{EX.grid[1]} 格 · 平整度 λ={EX.smoothness} · 可拼性 {EX.score}
        </figcaption>
      </figure>

      <ol className="intro-notes">
        <li>
          <Badge n={1} />
          <p>每一格印着色号，就是 MARD 豆盒上的那个编号。框出来的这一格是 <b>{EX.capCode}</b>。</p>
        </li>
        <li>
          <Badge n={2} />
          <p>
            底下附材料清单：共 {EX.beads} 颗、{EX.colors} 种颜色，按色号排好，
            照着去豆盒里拿就行。下载的 PNG 和 PDF 里都有。
          </p>
        </li>
      </ol>
    </aside>
  );
}
