# 有限实体色卡下的量化 / 色差 / 抖动（原始报告 C-B）

前提：≤100 px 宽、色卡 50–300 色、手工摆放。此规模所有算法毫秒级，**速度不是选型依据，散点数和总色数才是**。

## 1. 量化算法
| 方法 | 证据 | Python | 判断 |
|---|---|---|---|
| Median cut (Heckbert 1982) | Pérez-Delgado & Celebi 2024（10 算法×8 IQA，DOI 10.1007/s00530-023-01206-7）：所有指标所有色数下最差 | Pillow MEDIANCUT（默认） | 不推荐 |
| Octree | 同上第三差 | Pillow FASTOCTREE | 仅需 RGBA 时 |
| Wu 1991 | 中上；常作 k-means 初始化（Celebi 2011） | Pillow 无；第三方 | 可作初始化 |
| NeuQuant 1994 | 第 2–4 名 | GIF 编码器 | 无必要 |
| k-means | ADU（k-means 变体）综合最佳 | sklearn | 推荐（改 k-medoids） |
| libimagequant/pngquant | 改良 median cut + k-means 精修；误差扩散只在"邻域量化到同色且非边缘"处施加 | Pillow LIBIMAGEQUANT；imagequant-python | "选择性抖动"思想值得借鉴，但不能约束到实体色卡 |
| pyxelate 1692★ | 降采样 + 学习调色板 + Pal 迁移 | sklearn 风格 | 参考固定调色板迁移接口 |
综述：Celebi 2023 Forty years of color quantization DOI 10.1007/s10462-023-10406-6

## 2. 抖动：默认不抖动
- 误差扩散（F-S 1976、JJN、Atkinson、Ostromoukhov 2001）全部把平滑区变散点。
- 有序/蓝噪声（Bayer、void-and-cluster Ulichney 1993、Yliluoma 任意调色板）逐像素独立但同样散点。
- Riemersma（Hilbert 曲线受限误差扩散）兼顾局部性与任意调色板。
- 结构感知半调（Pang 2008、Chang 2009）面向高分辨率二值，靠增加结构化点保纹理，与目标相反。
- Python：hitherdither 260★（FS/JJN/Stucki/Burkes/Sierra/Atkinson/Bayer/cluster-dot/Yliluoma，任意调色板）；Pillow quantize(palette=img, dither=NONE|FLOYDSTEINBERG)。
- 不抖动依据（工具/社区，无论文）：Stitchmate 定义 confetti=无同色邻居的孤立格，<2% 可接受，>10% 极难做，来源是逐像素独立匹配；pixelbeads.org：抖动=噪声，单颗豆熨烫易倒、工时×3；gridbeads：像素画类应关闭抖动。学术最接近 Gerstner 2012（不含抖动，大色块优先）。
- 建议：默认 posterize 硬映射；若要渐变，只在大面积平滑区用低幅蓝噪声/有序抖动（借 pngquant 门控），再做孤立豆消除，输出 confetti% 指标。

## 3. 色差公式
- CIE76 JND≈2.3；CIEDE2000（Sharma 2005 DOI 10.1002/col.20070，测试数据 https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/）公式不连续(<4%)，设计目标小色差。
- OKLab（Ottosson 2020）：蓝色调色相预测明显优于 CIELAB；中灰附近 L/ab 比例与 CIEDE2000 一致。
- HyAB（Abasi 2020 DOI 10.1002/col.22451）：对 >10 单位大色差优于欧氏与 CIEDE2000——实体色卡稀疏，最近色常是大色差，值得纳入候选。
- 未找到针对"最近实体色匹配"的公式对照研究，属空白。
- 库：skimage.color.deltaE_cie76/ciede94/ciede2000/cmc（向量化）；colour-science 2653★ 含 delta_E_CIE2000/HyAB/HyCH/ITP/CAM16UCS；coloraide；colormath（标量慢，不建议）。
- 建议：主用 OKLab 欧氏（连续、快、色相好），以 ΔE00 与 HyAB 做 A/B；1 万像素×300 色=300 万次距离，numpy 毫秒级。

## 4. 三种映射策略
- 逐像素直接最近色：Stitchmate、pixelbeads 指出是 confetti 与色数爆炸来源。
- 先聚类再映射中心：Stitchmate 声明 confetti 减少 ~79%（厂商数据）；Gerstner 2012 学术版本。缺点：两个中心可能映射同一豆色（需去重），或中心落在色卡空洞处。
- 色卡受限 k-means（k-medoids，中心∈色卡）：直接优化目标，避免上述缺点。scikit-learn-extra KMedoids 203★，或自写 Lloyd 变体（分配步取最近当前子集色，更新步在色卡中选使簇内 ΔE 和最小者）。相关：ColorCNN arXiv 2003.07848；Lakhal 2022 arXiv 2204.12569（逐像素能量最小化并非视觉最优）。
- 建议：OKLab 中 k-medoids（中心限于色卡）+ 空间后处理 + 合并步。

## 5. 附带结论
- 感知空间 k-means 是否更优证据不一致（Maitra 2026 arXiv 2601.19117：约一半图 RGB 最好）。映射步度量比聚类空间更关键；聚类用 OKLab 成本为零。
- 合并阈值：ΔE76≈2.3、ΔE00≈1.0 为 JND；Stitchmate 实操"按用量剔除孤儿色（<50 格）+ 按相似度合并"。建议 ΔE00<2–3 无条件合并；占比很小的色放宽到 <5；OKLab 距离约×100 后与 Lab 同量级（估算需标定）。
