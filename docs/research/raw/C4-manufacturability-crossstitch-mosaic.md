# 邻近领域可制作性约束调研（原始报告 C-D：十字绣/钻石画/LEGO/马赛克）

## 1. 十字绣软件对 confetti（散点）的处理
结论：老牌商业软件（PCStitch / HobbyWare Pattern Maker / WinStitch）无自动去 confetti，靠"限色数 + 关抖动 + 手工清理"；新一代 Web 工具（Xstitchify、Stitchmate）把"邻域分析 + 孤立点合并"做成核心卖点。

| 软件 | 描述 | 来源 |
|---|---|---|
| HobbyWare Pattern Maker | Max colors + Dithering(None/F-S 最轻/Stucki 中/Burkes 最重)，手册明说抖动产生 speckling，无抖动则 blotchy；导入后需手工 clean up；有 Merging colors | needlelibrary.wordpress.com/wp-content/uploads/2014/06/pmaker.pdf |
| WinStitch/MacStitch | Max Colors、Dither(Photo) 开关、勾选可用线色（有库存才勾=固定色卡）、Suggest Colors；"先允许多色再手动减色"；背景清理逐针删除 | ursasoftware.com/help/2023/AdvancedImageImport.html |
| PCStitch 11 | 无 confetti 相关功能 | pcstitch.com/Features/Import/Import.aspx |
| Xstitchify | 每针与 8 邻域多轮平滑、孤立色并入周围；confetti 清理刷(Light/Medium/Strong)；建议 15–25 色、宽 80–120 针、关抖动 | xstitchify.com/cross-stitch-confetti/ |
| Stitchmate | confetti=无同色邻居的单针，<2% 可忽略、>10% 难受；先把邻域像素分组成可绣区域再匹配线色；CIEDE2000；Auto 清理 strength 0–100%；ConfettiScope 热图按同色邻居数分级；建议 8–15 色(图标)、15–25(宠物)、≤40 | stitchmate.app/handbook/confetti-cleanup |
| Pic2Pat / FlossCross / Pixel-Stitch | 只有针数+色数参数 | |

开源十字绣项目均 ≤34★ 且无 confetti 处理（nitfeh/tarraz、jklintan/Cross-Stitch-Generator、kohsuke/dmc-cross-stitch）。

## 2. 钻石画 + DMC 色卡
- 钻石画与十字绣共用逻辑；GridBeads 用 447 色 DMC 钻码 + CIEDE2000。
- 色卡来源：maxcleme/beadcolors（Diamond Dotz 461、Perler 103、Hama 92、Artkal、Nabbi、MARD 291，CSV 含 RGB/HSL/**Lab**）github.com/maxcleme/beadcolors；nathantspencer/DMC-ColorCodes；sharlagelfand/dmc；**所有 DMC RGB 表都是社区估值，非官方**。
- 色差：新工具一致 CIEDE2000；旧工具/开源多 RGB 欧氏。

## 3. 拼豆领域现成工具（补充视角）
- Zippland/perler-beads 965★：主导色 → RGB 欧氏 → **BFS 连通区域合并（阈值内相邻格聚区，统一为区内众数色号）** → 边界洪水填充去背景。色卡 `src/app/colorSystemMapping.json`（MARD/COCO/漫漫/盼盼/咪小窝 291 色映射）。
- a31521424/pixel-to-beads：**"个位数用量颜色一键取消并替换为最近色"**；连通块换色；`mard-color.json`。
- maxcleme/beadifier：多品牌预设，色卡外置 beadcolors。
- 国内主流路线"低分辨率化→最近色→连通域/用量阈值合并"，无人用 MRF。

## 4. 马赛克/LEGO/图像抽象中的可制作性约束
| 方法 | 原理 | 评价 | Python |
|---|---|---|---|
| 连通域+最小面积合并 | 面积<N 的块并入周边众数色 | 简单 O(n)；逐色迭代可能产生新孤点需多轮 | skimage.morphology.remove_small_objects / area_opening |
| 众数/多数滤波 | 邻域最常见标签 | 极快；会磨圆细线和 1 像素高光（Xstitchify：眼睛高光不能删） | skimage.filters.rank.modal |
| Mean-shift 分割 (DeCarlo & Santella 2002) | 先聚类成区域再着色 | 天然消 confetti；参数敏感慢 | cv2.pyrMeanShiftFiltering |
| Gerstner 2012 | SLIC + 联合优化 | 最贴合；色板自由色需改造 | 无官方 Python |
| **Pixel2Brick (CGF 2015, DOI 10.1111/cgf.12772)** | **CIELAB 数据项 + Potts 平滑项 → 多标签 graph cut 映射到 26 色 LEGO 色板；再检测悬空块 2×2 局部改色修连通** | 与拼豆几乎同构（固定小色板+连通性），最有力一手证据 | pygco 复现 |
| brickMosaic | RGB 贪心 + 库存计数 + 交换优化 | "每色只有 N 颗"约束可借鉴 | JS |
| Hausner 2001 / Kim&Pellacini 2002 | Voronoi 拼图 | 不规则瓷片，不适用 | |

## 5. Potts 模型 + graph cut（把连通性直接纳入优化）
- Boykov-Veksler-Zabih α-expansion（PAMI 2001, DOI 10.1109/34.969114）：标签=色号，数据项=ΔE(像素,色号)，平滑项=λ·[l_p≠l_q]，一次优化抑制散点且保边（Pixel2Brick §5.2，α=0.5，CIELAB）。
- Python：gco-wrapper(pyGCO, PyPI 3.0.9, cut_grid_graph_simple) github.com/Borda/pyGCO；yujiali/pygco；PyMaxflow 260★（教程含网格 Potts 去噪 add_grid_edges）。
- 成本：100×100 × 50 标签，α-expansion 数十毫秒~1 秒。缺点：软抑制不保证最小面积，需再跑面积过滤；λ 按 ΔE 量级调。

## 选型建议（50–100 宽、固定几十色、手摆）
1. 缩图：主导色/内容自适应降采样（避免均值灰边）。
2. 匹配：CIELAB + CIEDE2000，色卡 beadcolors / Zippland JSON。
3. 平滑：优先 Potts graph cut（gco-wrapper），或低成本连通域 + area_opening；可叠加。
4. 用量约束：色号总数 < N 颗自动取消重映射；色数上限 15–30。
5. 保护：允许用户标记"保留孤点"（高光），业界共识无算法能全自动判断。
