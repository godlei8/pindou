# 开源"图片 → 拼豆图纸"工具算法横评（原始报告 A）

调研方式：直接阅读各仓库默认分支源码 + Issues。日期 2026-09-20。
额外发现：pgp00/beadrelief（313★，与 Jett-Wu 同引擎）、liangdabiao/perler-beads-ai（306★，Zippland fork + AI 前置）、Python 参考 HansBug/pypindou、wuZHeBoy/bead-pattern。

## 横向对比

| 项目(★) | 下采样 | 量化/选色 | 色差 | 抖动(默认) | 可拼性 | 背景 | 底板 |
|---|---|---|---|---|---|---|---|
| Zippland/perler-beads (965) | 逐格精确 RGB 三元组众数(默认"卡通")或 sRGB 均值；默认 50 格 | 逐格直接匹配 MARD 291，再按频次全局合并相近色号(阈值默认 30)，无 maxColors | Oklab 欧氏×100（2026-04 PR#10 前为 RGB 欧氏） | 无（#15 提议 F-S 被 not planned） | 无自动；手动排除色号 | alpha<128→透明格；一键去背景=边缘最多色号 4 连通洪水填充 | 无 |
| LunarXuan/Pindo (400) | 线性 RGB 面积平均(默认)/6-bit 桶主色/edge-aware；默认 35×35 | 逐格 CIEDE2000 直接匹配全色卡→按使用频次保留前 N(默认 16)+保护最暗/最亮/最饱和→重匹配 | CIEDE2000 自实现 | F-S(默认 none)；ordered 是空实现 | removeIsolatedNoise(≤2 格)+3×3 多数滤波，仅 lowResOptimize 且≤58 格启用，默认关 | white/black 填充；transparent 模式 alpha 被完全忽略 | ceil(w/29) 固定切块 |
| zwhy149/bead-grid-studio (175) | 缩到≤4MP 后精确面积覆盖加权；cartoon(默认)=逐像素匹配后加权投票；photo=线性均值；pixel=中心 NN；默认 60×60 | 直接匹配→Oklab 相近色合并(mergeStrength 默认 10)→按 count·d²·importance 贪心压到 maxColors(默认 32)，锚定色保护 | Oklab 欧氏取前 32 候选→CIEDE2000 决选；cartoon 模式 RGB 5-bit 桶缓存 | 无 | cartoon：≤2 格彩色孤岛并入邻域多数；线稿模式 Zhang-Suen 骨架保连通；描边色保护 | whiteMode=auto：边框亮中性色中值+洪水填充；扫描黑边剔除 | 6 种板型(52/26/50/78/29/14)×tiles |
| pgp00/beadrelief (313) / Jett-Wu (50) | 每格 7×7/5×5/1×1 点采样取众数（非全面积） | 先统计样本→启发式加权排名→选≤maxColors(默认 24)候选→逐格只在候选中匹配；后处理由 speckleReduction 控制（默认 0=关） | redmean 加权 RGB | 无 | 有但默认关 | 边框 16 步桶众数估背景；tolerance 32；≥72% 背景样本→空格；默认 keep | 板宽高辅助线 |
| real-jiakai/perler-studio (3) | canvas 逐次减半 drawImage（sRGB 双线性） | 逐格直接匹配，无色数限制 | CIEDE2000 | F-S 默认开 | 无 | alpha<128→空格 | 仅计数 |
| yourlin/Fusible-Beads-Studio (4) | 预压 1024px 后最近邻缩到 29 格 | 逐格直接匹配，无限制 | CIEDE2000 | F-S 默认关 | 无 | alpha<128 或近白→空格 | 29/58/87 预设 |
| cornelk/beadmachine (20, Go) | Lanczos | 逐像素直接匹配 Hama | CIEDE2000 | 无 | 无 | alpha 丢弃 | 硬编码 29，四舍五入 |
| a31521424/pixel-to-beads (11) | canvas 两步双线性(sRGB)或 NN；再在 52 格小图上 Oklab 双边滤波 | KD-tree Oklab top-6 + 中性色偏置重打分；色卡用固定预设(24/48/96/160/291) | 加权 Oklab（ΔL×1.6） | F-S 0.55 默认开/Atkinson/Bayer8；serpentine 未实现 | 多数投票 coherence + despeckle，仅无抖动时生效 | alpha<128→白珠（无空格） | 无 |

## 逐项目关键细节

### Zippland/perler-beads
- `src/utils/pixelation.ts` L140-199：dominant 模式用 `${r},${g},${b}` 精确三元组计数取众数——对 JPEG/照片每格几乎无重复三元组，主色退化为随机像素，这是"卡通模式"对照片差的根因。average 为 sRGB 均值未做 gamma 线性化。
- `page.tsx` L947-1012 全局颜色合并：按频次降序，低频与高频 Oklab 距离×100 < 30 则整色号替换。只看频次不看空间位置；0.30 Oklab 相当大（黑↔白=1.0），造成整片色调偏移。
- Issues：#1 去杂色恢复后颜色不对；#2 色号 RGB 来源不明；#13 透明背景导出 CSV 再导入变 T01；#20 希望隐藏 T01 白格数字；#3 要连续填色/油漆桶；#15 F-S 提议被拒。

### LunarXuan/Pindo
- `lib/engine/downscaler.ts` L109-146 downscaleAverage 做 sRGB→线性→均值→sRGB（少数正确处理 gamma 的实现）。edge-aware 阈值 edgeMin=0.25/edgeRatioMin=0.045/edgeShareMin=0.55/edgeLumaDelta=18 全为 magic number。
- `palette-limit.ts` L43-108 按使用频次取前 maxColors，保留最暗/最亮/最饱和，剔除"灰泥色"(sat<30 且 50<luma<220)。不是误差最小化聚类，低频关键色（眼睛高光）会被丢。
- `dithering.ts` L10-14 ordered 直接 return pixels；F-S 在 sRGB 空间每步 clamp 截断累积误差。
- `page.tsx` L178-179 useLowResOptimize = lowResOpt && w<=58 && h<=58，lowResOptimize 默认 false → 默认路径无任何清理。stroke-extract.ts 死代码。
- transparent 模式下 downscaler 从不读 alpha，透明区以底层 RGB（常为 0,0,0）参与平均。
- Issues 全是 dependabot。

### zwhy149/bead-grid-studio
- `packages/core/src/quantize.js` 单函数 1503 行。
- L780-830 精确像素-格子重叠面积权重；cartoon 投票权重：描边×1.66+梯度、饱和×1.45+、近白×0.92。
- L1350-1400 锚定色（最暗、最亮中性 + 最多 3 个色相差>0.55rad 饱和色）；L1424-1462 loss = count·d²·(0.7+importance)·(1+2.2·chroma)，锚定×40。彩色永不并入中性色。
- L664-720 Oklab 粗筛 32 候选→CIEDE2000 决选；cartoon 5-bit 桶缓存精度损失 ±4/通道。
- L1270-1345 cartoon 下 8 连通≤2 格且 support<0.42 的彩色孤岛替换；L440-660 线稿(彩色≤1.2%)且≤60 格时 Zhang-Suen 细化保连通。
- Issues：#13 请求改进细节图色彩匹配（维护者要 fixture）；#12 基准测试未发布。
- 缺陷：投票对抗锯齿敏感；两套色空间混用；≥60 个 magic 阈值；H2 白色码硬编码。

### pgp00/beadrelief / Jett-Wu
- `sampleGridCells` L89-146 点采样，细线可能落在采样点之间消失。
- `rankPaletteColors` L148-184 chroma>48 ×2.25、暗线 ×1.55、亮中性 ×0.82；`selectCandidateColors` 四轮挑选；`chooseCellColor` 众数或均值匹配（主色占比<0.26）。
- `mergeSimilarColors`/`reduceTinyRegions`(≤1/2/5/9 格)/`reduceSpeckles` 由 speckleReduction 控制，默认 0 全关。
- `palette.ts` L370-376 redmean RGB。

### real-jiakai/perler-studio
- 默认 dither=true（L110），照片得到满是噪点、色数爆炸的图纸；无色数限制、无清理。

### yourlin/Fusible-Beads-Studio
- 1024→29 最近邻，相当于每 35×35 像素取 1 个，锯齿与断线严重。

### cornelk/beadmachine
- alpha 丢弃；硬编码 29 且 floor(x+.5)；-y 参数同时绑定两个选项；boardDimension 默认 20 与 29 不一致。

### a31521424/pixel-to-beads
- alpha<128→(255,255,255) 白珠，无空格概念；52 格小图上 Oklab 双边滤波 sigmaRange 0.045。
- KD-tree 距离 (1.6ΔL)²+Δa²+Δb²；亮低彩像素 top-6 后 darkPenalty/warmPenalty/chromaPenalty 重打分。
- 色数用固定子集（24/48/96/160/291）而非自适应。
- Oklab 空间 F-S/Atkinson/Bayer8；serpentine 未实现。清理仅 dither=none 时运行 → 默认档无清理。
- Issue #1：mard-color.json E2 写成 #FECODF（字母 O），开放 9 个月未修。

### liangdabiao/perler-beads-ai
- Zippland 旧 fork（RGB 欧氏）+ `aiOptimize.ts` 调火山引擎图生图，提示词 "chibi画风，背景白底。pixel art style, 16-bit…"。

### Python 参考
- HansBug/pypindou：CIELab MiniBatchKMeans(max_colors)→中心找最近色卡去重→不足按频次补；CIE76；F-S 带 strength；8 邻域多数清理；merge_small_regions；PIL BOX/LANCZOS。
- wuZHeBoy/bead-pattern：BOX 平均、numpy 向量化 CIEDE2000、Lab 洪水去背景(tol 12)、despeckle、limit_colors 迭代把用量最少色号并入最近保留色、rembg、29 基板。

## 共性缺陷汇总
1. 色数限制普遍是事后截断（频次取前 N / count·d² 贪心 / 频次阈值合并 / 启发式排名），无一在 Lab/Oklab 先聚类再映射（仅 pypindou）。小面积关键色被吞，大面积渐变硬切。
2. 匹配与合并度量不一致/随意：CIEDE2000、Oklab、redmean、混用。合并阈值（0.30/0.10 Oklab）无 JND 依据。
3. gamma：只有 Pindo 和 bead-grid(photo) 在线性 RGB 平均；其余 sRGB 或 canvas drawImage，暗部偏亮、边缘发灰。
4. "主色"实现粗糙：精确三元组众数、6-bit 桶、匹配后投票——无格内聚类或中值。
5. 抖动要么无、要么在 sRGB 扩散、要么与清理互斥。无"受限抖动"（只在低梯度区抖 + 最小连通块约束）。
6. 可拼性检查几乎缺席或默认关闭。无项目检查细线断裂、1 格宽斜线；无"某色号总用量<k 颗并入"（wuZHeBoy limit_colors 最接近）。
7. 透明/背景各自为政：alpha 阈值 128/24/0.12/丢弃/置白/忽略。自动去背景只有边缘单色洪水填充。
8. 底板分片停留在几何切块，不避板缝切细小图案。
9. 色卡数据不可靠：色号 RGB 无出处、十六进制打字错误。任何算法改进会被色卡误差抵消 → 自建带出处/实测 Lab 的色卡。
10. 参数即魔法数，无可复现基准。

推荐链路（没有任一项目完整做到）：线性 RGB 面积平均（可加中值/双边预处理）→ Oklab/CIELab 加权 k-means ≤N 簇 → CIEDE2000 映射色卡并去重/最小用量约束 → 可选受限抖动 → 连通块/细线/最小用量后处理 → 板缝感知分片。
