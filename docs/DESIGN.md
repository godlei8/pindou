# 拼豆图纸生成 · 设计规范

> 全站唯一的样式依据。新增页面、新增组件一律按本文件来；要偏离，先改本文件。
>
> 更新于 2026-09-20

---

## 1. 设计命题

**这个工具的对象是一块插着豆子的底板。界面就建在同一张栅格上。**

不是"加点像素装饰"，而是三件事落在同一套度量里：

1. 底板的孔距
2. 字体的字身（汉字 advance 恰好 1.000 em，数字恰好 0.5 em）
3. 布局的间距

所以 `24px` 这个数同时是：2 个汉字、4 个数字、1 个底板孔距、2 行 12px 文本的行高。
百分比、数量、坐标这些数字列能真的对齐成列，而不是"看着差不多齐"。（浏览器实测，非推断。）

> **精确边界：字体保证等宽的只有数字（6px）和汉字（12px）。**
> 这是比例模式，**拉丁字母各自宽度不同**——实测 `A`=8px、`H`=7px、`i`=4px、`W`=10px。
> 所以 `A1` 是 14px 而 `H2` 是 13px：**色号列靠字体对不齐，必须给固定列宽**（见 §7.4）。
> 想让字母也等宽得换等宽模式（monospaced），但那会把汉字之外的排版挤得很难看，不值得。

**配色约束：界面上每一个颜色都必须是一个真实存在的 MARD 色号。**

这条约束是自找的，但它有用——它保证界面不会漂成那种"米色底 + 衬线标题 + 陶土色强调"的通用样子，
而且用户在界面上看到的每一种颜色，都是他真的能买到的一袋豆子。

---

## 2. 三条不可违反的原则

### 2.1 像素风只作用于外壳，画布区域保持中性

调研过三个头部像素画编辑器（Piskel / Lospec Pixel Editor / Pixilart），
**它们都刻意不做像素风 UI**：外壳一律中性扁平、系统字体 11–14px。

它们是对的，但理由不是"像素风不好"，而是：**画布里的东西才是像素艺术，外壳一旦也来抢，就没法判断画布了。**

我们的画布里是图纸——用户要靠它判断颜色准不准、散点多不多、能不能拼。所以：

- **外壳**（顶栏、侧栏、卡片、按钮、清单）：像素风，硬边框、硬投影、直角、像素字。
- **画布及其紧邻控件**（缩放、网格开关、色号标注）：克制。背景中性，不加纹理，不加装饰角标。

违反这条的具体表现：给画布容器加斜纹底、给图纸加外发光、把网格线画成彩色。不要做。

### 2.2 不混排两套像素字体

`Press Start 2P` 之类的拉丁像素字体**不进 font-family 回退链**。理由是实测的，不是口味问题：

- PS2P 的设计网格是 **8 px/em**，缝合像素字体是 **12 px/em**。
  同一个 font-size 下一行里会出现两种大小的"像素颗粒"，像两张不同分辨率的素材拼在一起。
- PS2P **每个字符都占满 1.000 em**——色号 `A1` 会和两个汉字一样宽。
- PS2P 的 `descent = 0`。它若排在回退链首位，整行的行盒由它决定，汉字的下伸部会溢出内容区
  （CSS Inline Layout 3：内容区高度只取决于 first available font）。
- **而且这条链根本不会触发**——缝合像素字体的 Basic Latin 覆盖率是 100%，
  中文字体排前面时拉丁字母永远轮不到 PS2P。

一套字体搞定中英数。这也是 Pixelium Design 和 NES.css 官方文档的立场
（NES.css 的原话是 "use another font"，不是 "add a fallback"）。

### 2.3 字号只能是 12 的整数倍

字体的设计尺寸是 12px（upem=1200，每个设计像素 100 units）。
非整数倍会让字形落在半个设备像素上，被抗锯齿糊掉——像素字体一糊就失去全部意义。

**允许的字号：12px / 24px / 36px。没有 14、16、18。**

需要一个"介于之间"的尺寸时，那是布局出了问题，不是字号出了问题。

---

## 3. 颜色令牌

全部取自 `backend/app/palettes/mard.json`。`confidence` 一列是两个数据源的一致性
（`conflict` = 两源色值 ΔE00 > 3，实物可能与屏幕有出入，见 spec §11）。

```css
:root {
  /* —— 面 —— */
  --board:        #F9F0CD;  /* A1  底板米黄，页面背景          agree    */
  --surface:      #FFFDF0;  /* H18 卡片面                      agree    */
  --surface-sunk: #F1EDED;  /* H17 凹陷区、表头、只读块        agree    */
  --peg:          #E2DFD7;  /* T1  透明豆色，底板凸点/细分隔   conflict */
  --white:        #FFFFFF;  /* H2  输入框底                    agree    */

  /* —— 墨 —— */
  --ink:          #3B2F23;  /* H16 文字与边框    12.72:1 on surface  AAA */
  --ink-mute:     #55514C;  /* R13 次要文字       7.71:1 on surface  AAA */

  /* —— 功能色 —— */
  --accent:       #C80020;  /* F15 主操作底色     白字 6.04:1        AA  */
  --info:         #1757A8;  /* C16 AI 相关        白字 7.08:1        AA  */
  --warn:         #FFDB4D;  /* R10 焦点环、警告底 ink 9.58:1        AAA */

  /* —— 只许当色块，禁止承载文字 —— */
  --bead-red:     #FC3D45;  /* F2  草莓红，装饰/豆子 */
  --bead-green:   #00BD35;  /* B5  叶绿，状态点      */
}
```

### 硬规则

| 规则 | 原因 |
|---|---|
| `--bead-green` / `--bead-red` **上面不许放任何文字** | 白字在 B5 上 2.52:1，在 F2 上 3.56:1，都不合格 |
| 需要红色按钮时用 `--accent`（F15），不是 `--bead-red`（F2） | F2 承载白字不合格；F15 深一档，6.04:1 通过 |
| 色块 + 文字的组合，文字一律 `--ink` | ink 在本调色板任一浅色上都 ≥ 5:1 |
| 次要文字用 `--ink-mute`，不要 `opacity` 或 `color-mix` 调淡 `--ink` | 调淡后对比度不可控；R13 是实算过的 |

> **F2 曾经是登录页主按钮的底色，白字 3.56:1——不合格。**
> 15px/700 不满足 WCAG 的"大文本"豁免（需 18.66px+bold 或 24px）。
> 已改为 F15，F2 退回它本来的角色：草莓的红。

---

## 4. 字体

### 选型

`frontend/public/fonts/fusion-pixel-12px-zh_hans-subset.woff2` — 132 KB

缝合像素字体 / Fusion Pixel Font 12px proportional zh_hans 的子集。
协议 **SIL OFL 1.1，无 Reserved Font Name**，可自由商用、子集化、改名。

> ⚠️ GitHub 仓库侧边栏把它标成 MIT——**那是构建程序的协议，不是字体的协议**。合规审查别照抄侧边栏。

选它而不是其他中文像素字体的决定性理由（全部实测）：

| | Fusion Pixel | Zpix | Cubic 11 |
|---|---|---|---|
| 商用 | OFL，免费 | **¥7000/产品，且条款禁止"修改、转换、拆分"** | OFL，免费 |
| 数字等宽 | ✅ 全部 600 units | ❌ `1` 是 4px，其余 7px | ❌ 混合 |
| 汉字 advance | ✅ **1.000 em** | 1.083 em | 1.083 em |
| 半角:全角 | ✅ 严格 1:2 | 非严格 | 非严格 |
| GB2312 一级 | 100% | 100% | 100% |

"数字等宽 + 汉字 1.000 em + 半角恰好半格"三条同时成立，
栅格对齐才是**真的**成立，而不是靠 `tabular-nums` 和固定列宽硬凑。
Zpix 的授权条款字面上连子集化都禁止，一开始就出局。

### 用法

```css
@font-face {
  font-family: "Fusion Pixel";
  src: url("/fonts/fusion-pixel-12px-zh_hans-subset.woff2") format("woff2");
  font-weight: 400;          /* 只有这一个字重 */
  font-display: swap;
}

:root {
  --font: "Fusion Pixel", "Microsoft YaHei", "PingFang SC", sans-serif;
  --fs-body:  12px;   --lh-body:  16px;   /* 字体自身行盒 1.33 em */
  --fs-title: 24px;   --lh-title: 32px;
  --fs-hero:  36px;   --lh-hero:  48px;   /* 只用于评分数字 */
}
```

**不要 `font-weight: bold`。** 这个字体只有 400 一个字重，`bold` 会触发浏览器的合成加粗——
把 1px 的笔画涂成 2px，像素字一加粗就糊。需要强调时换颜色或加底色块。

**不要 `-webkit-font-smoothing: none`。** MDN 明确标注非标准、不建议生产使用；
而且没必要——这是轮廓字体（纯 `glyf`，无位图表），字号取 12 的倍数时字形本来就落在整数像素上。

**不要 `letter-spacing`。** 会破坏半角:全角 = 1:2 的关系，栅格立刻散掉。
唯一例外是页面主标题这种单行装饰性文字。

### 后端导出也要用它

下载的 PNG 底部材料清单、PDF 清单页和每页页脚都有中文，
后端用同一份子集的 TTF（`backend/app/assets/fonts/`，Pillow 读不了 woff2）。

> **Pillow 的 `ImageFont.load_default()` 没有中文字形。** 之前 PDF 清单里的"颗""包"、
> 页脚的"第 1 行 / 第 1 列 页"一直渲染成方块，一直没人发现。
> 凡是要画汉字的地方一律用 `render.cjk_font()`；`_font()` 只留给纯 ASCII（格子里的色号、坐标轴）。
> 回归测试用"两个不同的字画出来位图不同"来判断——缺字时它们会是同一个方块。

### 子集覆盖范围与重建

当前子集 = GB2312 一级汉字 3755 字 + 界面/后端文案用字 + ASCII + 常用标点 = 3910 码位。

**新增界面文案后需要重跑子集**，否则新字会掉成豆腐块。步骤见
`frontend/public/fonts/README.md`。用户自己起的项目名走 GB2312 一级覆盖，日常中文不会缺字。

---

## 5. 栅格与间距

```css
:root {
  --pitch: 24px;   /* 底板孔距 = 2 汉字 = 4 数字 = 2 行正文 */

  --sp-1:  4px;    --sp-2:  8px;    --sp-3: 12px;
  --sp-4: 16px;    --sp-6: 24px;    --sp-8: 32px;
}
```

间距一律取上表的值，不要写 `5px` `10px` `15px` 这种。

**底板背景**（只用在登录页和空状态这类大片留白处，不要铺满工作台）：

```css
background-color: var(--board);
background-image: radial-gradient(circle at center, var(--peg) 0 3px, transparent 3px);
background-size: var(--pitch) var(--pitch);
background-position: calc(var(--pitch) / 2) calc(var(--pitch) / 2);
```

---

## 6. 边框、投影、圆角

```css
:root {
  --bd:   2px;   /* 控件 */
  --bd-2: 3px;   /* 卡片、主按钮 */
}
```

- **边框只有 2px 和 3px。** 不用 1px（太细，不像素）。颜色一律 `--ink`。
- **`border-radius: 0`，全站无例外**——除了豆子本身（`50%`，那是物理对象不是 UI）。
- **投影一律零模糊**：`box-shadow: Npx Npx 0 var(--ink)`。不许出现模糊半径。

**投影距离编码层级**（越重要投得越远）：

| 距离 | 用在 |
|---|---|
| `6px` | 卡片、画布外框 |
| `4px` | 面板、主按钮 |
| `3px` | 次级按钮、chip、tab |
| `2px` | 小控件（swatch、滑块 thumb） |

---

## 7. 组件模式

### 7.1 按钮

按下的表现是**位移 + 投影收缩，且位移量等于投影收缩量**，所以按钮的"总高"恒定，不会把周围顶动：

```css
.btn {
  border: var(--bd-2) solid var(--ink);
  border-radius: 0;
  box-shadow: 4px 4px 0 var(--ink);
  padding: var(--sp-2) var(--sp-4);
  font: inherit;
  transition: transform 90ms ease, box-shadow 90ms ease;
}
.btn:hover:not(:disabled)  { transform: translate(2px, 2px); box-shadow: 2px 2px 0 var(--ink); }
.btn:active:not(:disabled) { transform: translate(4px, 4px); box-shadow: 0 0 0 var(--ink); }
.btn:disabled { opacity: .55; cursor: not-allowed; box-shadow: 4px 4px 0 var(--peg); }
```

主按钮 `background: var(--accent); color: #fff`，次级 `background: var(--surface); color: var(--ink)`。

> 另一条可选路线是 Win98 式的"多层 inset box-shadow 翻转"，不位移。
> 它更适合控件极密的面板（鼠标扫过不抖），但触屏反馈弱。我们用位移式。
> **若某个面板控件密到 hover 会满屏抖动，那个面板局部可以关掉 hover 位移**，保留 active 位移。

### 7.2 焦点

```css
:root { --focus: 0 0 0 3px var(--warn), 0 0 0 5px var(--ink); }
.btn:focus-visible, input:focus-visible { outline: none; box-shadow: var(--focus); }
```

黄环外面必须套一圈 ink。单独的黄环在米黄底板上只有 1.2:1，看不见；
外圈 ink 对任何背景都 ≥ 3:1，保证 WCAG 2.2 的焦点可见性。

带投影的元素聚焦时，投影和焦点环要写在同一条 `box-shadow` 里：
`box-shadow: 4px 4px 0 var(--ink), var(--focus)`。

### 7.3 输入框

```css
input, select, textarea {
  border: var(--bd) solid var(--ink);
  border-radius: 0;
  background: var(--white);
  padding: var(--sp-2) var(--sp-3);
  font: inherit;
  color: var(--ink);
  appearance: none;        /* select 必须，否则系统箭头破风格 */
}
```

`select` 的箭头用内联 SVG（`utf8` 直写，`%23` 转义 `#`，比 base64 小）：

```css
select {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='M1 1l5 5 5-5' fill='none' stroke='%233B2F23' stroke-width='2'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  padding-right: 30px;
}
```

### 7.4 清单（材料清单、问题清单）

调研的五个像素风框架（98.css / 7.css / XP.css / NES.css / BitSugar）**无一使用斑马纹**，
一致用"整行高亮"。照做：

- 行分隔：`border-bottom: 2px solid var(--peg)`，最后一行去掉
- hover：`background: var(--surface-sunk)`
- 选中：整行反色 `background: var(--ink); color: var(--board)`
- **不要斑马纹**

列用 `grid-template-columns` 定死，数字列右对齐：

```css
.material-row { display: grid; grid-template-columns: 20px 48px 1fr auto; gap: var(--sp-2); }
.material-row .count { text-align: right; font-variant-numeric: tabular-nums; }
```

`tabular-nums` 在 Fusion Pixel 下是冗余的（数字本来就等宽），但**回退字体需要它**——
字体没加载完或掉到微软雅黑时，不加这条数字列会左右跳。

**色号列的 `48px` 是必须的，不是随手填的。** 拉丁字母在比例模式下不等宽
（`A1`=14px、`H2`=13px），靠字体对不齐；固定列宽把边界钉死，列内左对齐即可。
48px 能放下四个最宽的字母（`W`=10px），够覆盖 MARD 的全部色号格式。

色块 `.swatch` 固定 `20px × 20px`，`border: 2px solid var(--ink)`。

**占比条用实心方块，不要 `linear-gradient` 的硬停止点**——§10 禁渐变背景，
而且实体 `<span>` 加百分比宽度更好读也更好测。条长按**最大值**归一，不按总和：
色号一多时按总和算出来全是看不见的细条。
**色号和数量的文字颜色恒为 `--ink`，不要按豆子颜色做反色自适应**——
文字在卡片底上，不在色块上。

### 7.5 滑块

跨浏览器有四个必须处理的坑（全部实测）：

```css
input[type="range"] {
  -webkit-appearance: none; appearance: none;
  width: 100%;
  height: 32px;            /* ← 点击热区来自 input 本体，不是轨道 */
  background: transparent;
}
input[type="range"]::-webkit-slider-runnable-track {
  height: 12px; border: var(--bd) solid var(--ink);
  border-radius: 0; background: var(--surface-sunk);
}
input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;      /* ← 必须在 thumb 里再写一次 */
  width: 16px; height: 16px; margin-top: -4px;
  border: var(--bd) solid var(--ink);
  border-radius: 0;              /* ← 不写 Chrome 默认给圆的 */
  background: var(--accent);
  box-shadow: 2px 2px 0 var(--ink);
}
input[type="range"]::-moz-range-thumb {
  width: 12px; height: 12px;     /* ← Firefox 不把 border 计入尺寸，要减 2×border */
  border: var(--bd) solid var(--ink); border-radius: 0;
  background: var(--accent); box-shadow: 2px 2px 0 var(--ink);
}
```

1. `-webkit-appearance: none` 在 input 上写了不够，**thumb 伪元素里必须再写一次**
2. `border-radius: 0` 必须显式写在 thumb 上，否则 Chrome 给圆的
3. **Firefox 的 thumb 尺寸不含 border**，要比 webkit 小 2×border-width
4. 扩点击热区靠 **input 本体的 height/padding**，不要加高轨道（轨道一高就不像像素条了）

### 7.6 画布区（遵守 §2.1，克制）

```css
.canvas-wrap {
  border: var(--bd-2) solid var(--ink);
  box-shadow: 6px 6px 0 var(--ink);
  background: repeating-conic-gradient(#EFEFF6 0 25%, #FFFFFF 0 50%) 50% / 20px 20px;
  overflow: auto;
  min-width: 0;             /* 否则在 grid/flex 子项里会被内部 canvas 撑爆 */
  touch-action: none;       /* 触屏拖拽平移不被页面滚动拦截 */
}
canvas { display: block; image-rendering: pixelated; }
```

- 透明棋盘格用 `repeating-conic-gradient` 一行搞定（比 4 层 linear-gradient 干净）
- **网格线不要烧进主 canvas**，用独立的覆盖层，可整层开关、可跟随缩放换 `background-size`
- `image-rendering` **做成可切换**：缩小看整体时 `auto` 更好看，放大看单颗豆时才 `pixelated`
- **默认缩放是「看色号」，不是「看全貌」。** 拼的时候要逐格对色号，一进来就该看得到。
  每格 ≥ 18px 才画色号（`SHOW_CODES_MIN`），所以默认取档位里第一个 ≥ 18 的（20px）；
  窗口够大、适应尺寸本身就 ≥ 20px 时就等于适应，不多余放大。
  图纸大到放不下时画布自己滚——这正是 §7.7 说的"除非图特别大"。
  看构图再点「看全貌」。两个预设用按下态标出当前处在哪个。

### 7.7 工作台是视口锁定布局

**工作台占满一屏且整体不滚动**，只有两样东西允许自己滚：图纸特别大时的画布、
色号特别多时的材料清单。其余内容必须一屏装下。

```css
body { height: 100dvh; overflow: hidden; }   /* 不能用 min-height */
#root { height: 100%; display: flex; flex-direction: column; }
#root > .topbar { flex: 0 0 auto; }
#root > main    { flex: 1 1 0; min-height: 0; overflow-y: auto; }
```

三个坑，都是实际踩过的：

1. **`min-height: 100vh` 锁不住。** 内容一高 body 就跟着长，整页照样滚。必须 `height`。
   用 `dvh` 不用 `vh`：移动端地址栏收起时 `vh` 会算多一截。
2. **`flex-basis` 必须是 `0`。** 写 `flex: 1 1 auto` 时基准是内容高度，
   `main` 会被内部面板撑大，等于没约束。
3. **真正的 flex 容器是 `#root`，不是 `body`。** React 挂在 `#root` 上。

侧栏用 flex 竖排，让"可以滚的那一个"吃掉剩余高度（`flex: 1 1 auto` + `min-height`），
其余面板 `flex: none`。这样底部的面板永远在屏幕上，而不是被十几行色号顶出视口。

### 7.8 量容器尺寸

画布这类"按可用空间自适应"的元素，尺寸**必须量出来**，不能写死预算。两个必踩的坑：

```ts
// 对：量内容盒
const cs = getComputedStyle(node);
const w = node.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);

// 错：getBoundingClientRect 是边框盒，把 border + padding 也算进去了，
//     内容会大出一圈，逼出一根本不该有的滚动条
```

1. **量内容盒。** `clientWidth` 已排除 border 和滚动条，再扣掉 padding。
2. **用回调 ref，不要 `useRef` + `[]` 依赖的 effect。**
   目标元素常常不是一开始就在的（加载期走早退分支时压根没渲染），
   `[]` 的 effect 只在挂载时跑一次，那时 `ref.current` 还是 null，
   元素后来出现也没人去观察它——尺寸永远停在 0。见 `useElementSize`。

留 2px 余量：正好卡在边界上时，滚动条一出一进会让尺寸来回抖。

### 7.9 首页：左栏介绍，右栏干活

宽屏左右分栏、各自滚动（和工作台一样视口锁定）；窄于 1100px 时上下排。

- **介绍不用"三张功能卡片"**——那是任何产品首页都长的样子。左栏摆一张**真实输出**，
  在图上用编号方块标出要讲的东西，旁边逐条解释。编号是有信息的：它把图上的点和正文对上。
- **这张示例必须是流水线真跑出来的**，由 `backend/scripts/make_intro_example.py` 生成，
  连同标注位置和统计数字写进 `introExample.ts`。**别手改、别手画**——那就成了宣传图。
  算法改了就重跑脚本。
- **标注只说图上确实成立的事。** 示例参数是挑过的（24 格、λ=4），这组参数原样印在图下；
  "比别家干净"这类判断放在正文里讲，不拿这张图去证明——它边上还有过渡色，撑不住这句话。
- **「新图纸」是网格第一格**，不单独占横幅。没有项目时示例图作为卡片排在它旁边；
  有项目后示例让位。整页拖拽和 Ctrl+V 在哪都生效，所以不需要一个巨大的投放框。
- 卡片上的浮动按钮（改名）钉在缩略图角上，不按"离底部多少"定位——
  文字一换行，按底部算的位置就会压到文字上。

---

## 8. 可访问性底线

不是加分项，是每个组件的交付条件：

- 正文对比度 ≥ 4.5:1（§3 的令牌已全部验过）
- 每个可聚焦元素都有 §7.2 的焦点环，且键盘可达
- 色块必须配文字（色号），**不能只靠颜色传达信息**——
  拼豆用户里色觉障碍的比例和普通人群一样，而这个工具的全部内容就是颜色
- **目标尺寸分两档，按指针类型**：
  - 鼠标（默认）：≥ 24px —— WCAG 2.2 AA 的实际门槛（2.5.8 Target Size Minimum）。
    这是个信息密集的桌面工具，工具栏按钮 28px、色块 24px 是对的，不要为了"更安全"一刀切放大。
  - 触屏（`@media (pointer: coarse)`）：≥ 44px —— WCAG 2.5.5 AAA。手指不是鼠标。
  - 滑块是例外，两档都给足高度（`input` 本体 32px），因为它要拖不是点。
- `prefers-reduced-motion: reduce` 时关掉位移和熨烫动画，保留颜色变化
- 移动端 375px 宽下无横向滚动

---

## 9. 动效

| 用途 | 时长 | 缓动 |
|---|---|---|
| 按钮按下 | 90ms | `ease` |
| 面板展开/收起 | 180ms | `ease` |
| 熨烫（登录成功） | 420ms | `cubic-bezier(.2,.8,.3,1)` |
| 等待指示（AI 出图） | 900ms 循环 | `steps(3)` |

就这四档，**不要再加第五种**——像素风的克制体现在这里，满屏微动画会让它显得廉价。

等待指示必须用 `steps()`：像素风里没有平滑补间，连续缓动的转圈会立刻露馅。
它也是唯一允许循环播放的动效，且只在真的有后台任务在跑时出现。

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition-duration: 1ms !important; animation-duration: 1ms !important; }
}
```

---

## 10. 不要做的事

| 不要 | 因为 |
|---|---|
| `border-radius` 非 0（豆子除外） | 直角是这套风格的地基 |
| 带模糊半径的 `box-shadow` | 像素风的投影是硬的 |
| 渐变背景（棋盘格 / 底板点阵除外） | 同上 |
| `font-weight: bold` | 字体只有 400，合成加粗会糊 |
| 12 的非整数倍字号 | 字形落在半像素上 |
| `letter-spacing`（主标题除外） | 破坏半角:全角 = 1:2 |
| 斑马纹表格 | 五个像素风框架一致不用；整行高亮更清楚 |
| 在 `--bead-red` / `--bead-green` 上放文字 | 对比度 3.56 / 2.52，不合格 |
| 给画布区加纹理、发光、装饰角标 | 违反 §2.1，会干扰对图纸本身的判断 |
| 引入第二套像素字体 | 见 §2.2 |
| AI 风格预设里出现"像素风" | 实测：AI 出的"像素风"色数 38714（平涂方案 13088），图纸评分 82.4 ≈ 不用 AI 的 81.6。像素化是我们流水线的事，不是 AI 的事 |

---

## 11. 调研来源

- 字体度量：本机 fontTools 解析 Fusion Pixel / Zpix / Cubic 11 / Ark Pixel 实测
- 组件模式：98.css、7.css、XP.css、NES.css 源码；BitSugar、belleqaq、Jett-Wu 三个拼豆开源项目源码
- 反面参照：Piskel、Lospec Pixel Editor、Pixilart（均刻意不做像素风外壳）
- 对比度：WCAG 2.1 相对亮度公式，对 `mard.json` 实算
- AI 预设结论：`scratchpad/design/ai-prompt-findings.md`（真实 API 调用测试）
