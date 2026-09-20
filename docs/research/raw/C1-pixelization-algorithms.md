# 图像→像素画算法调研（原始报告 C-A）

目标：照片/插画 → 50×50~100×100 网格、几十种固定色号。

## 一、经典优化/滤波型下采样（不含调色板）

1. Kopf/Shamir/Peers 2013 Content-Adaptive Image Downscaling (SIGGRAPH Asia)
- 每个输出像素对应可变形双边高斯核（空间×颜色），约束 EM 迭代优化核形状/位置。
- 保边、不振铃、线条细且连通；论文明确适合卡通/矢量→像素画。
- 迭代式，明显慢于线性滤波；C++。Python 实现无成熟：martin041313/EMC（1★）。
- 卡通 ★★★★★ 照片 ★★★★。DOI 10.1145/2508363.2508370；https://johanneskopf.de/publications/downscaling/

2. Öztireli & Gross 2015 Perceptually Based Downscaling (SIGGRAPH)
- 最小化 SSIM 损失，闭式解——局部均值/方差求和与卷积。
- 像"锐化过的 box"；对噪声/纹理会放大，小网格颗粒感。
- 与线性滤波同量级。实现：JefersonFG/perceptual_downscaling（C++）；Luke100000/scalerack（PyPI，未核验）。十几行 NumPy 可复现。
- 照片 ★★★★ 插画 ★★★。DOI 10.1145/2766891

3. Weber et al. 2016 DPID Rapid Detail-Preserving Downscaling (SIGGRAPH Asia)
- box 引导图，再按"与引导图色差^λ"加权求和。单遍极快；λ 调保细节 vs 平滑；小网格易把噪点当细节。
- mergian/dpid（35★ CUDA/MATLAB），rlabbe/dpid（Python+numba，未充分测试）。
- 照片 ★★★★ 插画 ★★★★。DOI 10.1145/2980179.2980239

## 二、下采样 + 调色板联合优化（最贴近拼豆）

4. Gerstner et al. 2012 Pixelated Image Abstraction (NPAR)；2013 扩展版 with Integrated User Constraints (C&G 37(5))
- 每个输出像素 = 输入图上一个超像素。迭代：① 改良 SLIC（LAB，m=45 均匀；超像素颜色用当前调色板色而非均值；Laplacian 平滑拉回 8 邻接方格）；② 质量约束确定性退火 MCDA 同时求 K 色调色板并软分配；温度下降簇分裂到 K 色。扩展版加用户约束（钉住色、重要性区域、手动调色板）。
- 专为极小网格 + 极少色设计：评估 22×32、11×16、约 8 色、照片输入；用户研究优于 nearest/cubic + median-cut。保边、保留眼睛等语义特征、肤色更准。
- 迭代 O(输入像素数)×数十至上百次；纯 Python 慢，需 Cython/numba。
- 官方源码 ZIP https://cragl.cs.gmu.edu/pixelate/code.zip（非 Python）；Python 复现 NikolayBlagoev/Pixelated-Image-Abstraction（Cython，3★）、harry75369/Resample（9★）。都不成熟，建议自行复现（算法不长）。
- 固定色号适配：MCDA 求色板可改为"从固定色号集合里选 K 色"（簇中心投影到最近色号），结构天然兼容。
- 照片 ★★★★★ 插画 ★★★★。https://pixl.cs.princeton.edu/pubs/Gerstner_2012_PIA/index.php ；https://cragl.cs.gmu.edu/pixelate/journal.html

## 三、深度学习

5a. Han/Wen/He 2018 Deep Unsupervised Pixelization (SIGGRAPH Asia)：GridNet→PixelNet→DepixelNet 级联，clip-art 训练；固定缩放比例，不控调色板。csqiangwen/Deep-Unsupervised-Pixelization（PyTorch 0.4，28★）。
5b. Wu/Zhao 2022 Make Your Own Sprites (SIGGRAPH Asia)：I2PNet/P2INet + AliasNet，可控 cell size；需 GPU，非商业许可。WuZongWei6/Pixelization（442★）；A1111 扩展 637★；comfy_pixelization 136★。
5c. Binninger & Sorkine-Hornung 2024 SD-πXL (SIGGRAPH Asia)：H×W×n Gumbel-softmax 类别张量作可微生成器，SD score distillation；用户指定任意尺寸 + 任意 n 色调色板；README 面向十字绣等。GPU 分钟级（其他报告说数小时）；重绘而非忠实缩放。AlexandreBinninger/SD-piXL（67★）；arXiv 2410.06236。
5d. 2025 保真下采样：ADK-Net arXiv 2511.01620；Structure-Aware Downscaling arXiv 2510.22551；共现引导大倍率 arXiv 2510.24334。只在 4×~16× 验证，无 Python 实现。

## 四、工程实践型工具

| 工具 | 原理 | 备注 |
|---|---|---|
| sedthh/pyxelate 1692★ | 3×3 tile 内按梯度方向（HOG 思想）选代表色迭代下采样；Bayesian GMM 求调色板；支持固定 Pal 调色板（CIEDE2000 匹配）、bayer/floyd/atkinson | 纯 Python/sklearn/numba，MIT。最贴近拼豆的现成库 |
| KohakuBlueleaf/PixelOE 501★ | 先"轮廓扩张"（按局部对比度把细结构加粗）再下采样，模式 center/contrast/k-centroid；可选色量化 | PyTorch，CPU 可跑；pip 安装 |
| dimtoneff/ComfyUI-PixelArt-Detector 445★ | 封装 Astropulse/pixeldetector（检测像素网格并还原）、调色板、抖动 | 面向 SDXL 生成像素画的后处理 |
| Pillow reduce()/resize(BOX) + quantize(MEDIANCUT/MAXCOVERAGE/FASTOCTREE/LIBIMAGEQUANT) | 面积平均 + 经典量化 | Gerstner 对照基线，小网格下模糊 |
| gametorch/image_to_pixel_art_wasm 168★ | nearest + k-means | Rust/WASM |

## 五、50~100 格时谁退化、谁可用
- 退化：Pillow BOX/bicubic + median-cut（模糊）；Öztireli/DPID 20×+ 缩放把纹理/噪声当细节；2025 保真系列只在 4~16×；Han 2018 缩放比固定；PixelOE 轮廓扩张在极小网格线条过粗。
- 可用：Gerstner（设计目标 11×16~64×64 + ≤16 色，最合适）；Kopf（线条连通性最好，需自实现且慢）；pyxelate（工程上立即可用）；SD-πXL（可指定 H×W 与调色板，但是生成非转换，GPU）。

## 六、选型建议
1. 快速基线：pyxelate 传拼豆色号 Pal（或 PixelOE contrast + CIEDE2000 映射）。
2. 主方案：自实现 Gerstner 2012（SLIC + MCDA，调色板更新步改为投影到固定色号集合，numba 加速），插画/照片通吃、极小网格最稳。
3. 可选前置：照片先用 DPID/Öztireli 做 2~4× 预缩再喂 Gerstner。
4. 深度方案仅实验：SD-πXL。
