# AI 重绘 → 像素化 → 拼豆图纸（原始报告 C-C）

## 1. 提示词策略
- 核心结论：靠 prompt 让扩散模型直接输出"真像素网格"不可行（连续潜空间无离散像素概念，unfake 作者）。社区公认流程：生成 8× 过采样伪像素图 → 检测网格 → 最近邻/众数下采样 → 调色板量化。
- 正向词：pixel art / pixel（Pixel Art XL 作者建议只写 pixel）、16 bit / 32 bit、simple, flat colors、16-color palette、retro game sprite、32x32 style。
- 负向词：3d render, realistic, blurry, photograph。Retro Diffusion API 忽略 negative。
- LoRA 强度：Pixel Art XL 1.2（>1.4 伪影）；8bitdiffuser 0.85–1.25。步数 10–30、CFG 4–10。
- img2img strength：diffusers 官方"保构图重风格"0.4–0.6，配 ControlNet 0.45；Retro Diffusion 默认 0.75；即梦 i2i 3.0 `scale` 同义（示例 0.5）。
- ControlNet：canny/depth，conditioning_scale=0.5；ControlNet 1.1 有 lineart/lineart_anime。照片→平面化用 lineart+depth 最贴合。
- 两步法（照片→平面插画→像素画）：无系统总结帖；间接证据：8bitdiffuser 在 cel-shaded/动漫底模效果最好；Onodofthenorth 缩小到目标尺寸再放大可消除颜色浑浊。
- 来源：huggingface.co/nerijs/pixel-art-xl；civitai 120096/185743/277680；diffusers img2img.md、controlnet.md；lllyasviel/ControlNet-v1-1-nightly；agentbus.sh 教程；lexlex47/game-art-prompt-kit（含 "no visible grid lines, high-contrast, solid background"）。

## 2. 像素画模型/LoRA
| 模型 | 底模 | 后处理说明 | 环境 |
|---|---|---|---|
| nerijs/pixel-art-xl | SDXL | Downscale 8× 最近邻得 pixel perfect；fp16-fix VAE；不用 refiner；配 Astropulse PixelDetector | diffusers，LCM-LoRA 8 步，~8GB |
| Pixel Art Diffusion XL (Yamer) | SDXL ckpt | 只求风格不求像素形状 | diffusers |
| 8bitdiffuser 64x | SD1.5 LoRA | 512→8× 缩小=64×64 | 4–6GB |
| Shakker-Labs/FLUX.1-Kontext-dev-LoRA-Pixel-Style | Flux Kontext | "Convert to a pixel art style"，24 步 | ≥24GB |
| UmeAiRT/FLUX.1-dev-LoRA-Modern_Pixel_art | Flux.1-dev | 触发 umempart | |
| tarn59/pixel_art_style_lora_z_image_turbo | Z-Image-Turbo | | |
| Limbicnation/pixel-art-lora | FLUX.2-klein-4B | 4 步 | |
| nerijs/pixel-art-3.5L | SD3.5L | 声称网格对齐 128×128 | |
| Retro Diffusion (Astropulse) | 闭源 API | 直接输出 16–384px 真像素网格，img2img，免费 Pixel Fixer | $0.015–0.18/张，无需 GPU |
- Retro-Diffusion/api-examples（03_img2img.py、10_pixel_fixer.py）；Astropulse/pixeldetector（Aseprite "Repair pixel art" 开源算法）。

## 3. 伪像素画后处理
- 问题：网格不对齐、伪像素越界/模糊、颜色数上千。
- Astropulse pixeldetector（Pillow+NumPy+SciPy）：相邻色差按列/行求和 → find_peaks → 峰间距中位数=像素尺寸；kCentroid（每格 k-means k=2 取众数）下采样；elbow 法定色数。
- unfake.js / unfake.py（pip install unfake，Rust 加速，1MP ~0.5s）：Sobel 边缘 1D 投影 + 峰距直方图投票；遍历 offset 求最佳相位并裁剪；Wu 量化；dominant 色投票（领先>5% 才采纳否则均值回退）；形态学清理；**fixed_palette=[...] 直接对应拼豆色号**。
- spritefusion-pixel-snapper（Rust，有 ComfyUI Python 移植）：k-means + --palette 固定色 + 自动 pixel size。
- Retro Diffusion POST /v2/pixel-fixer/standard|neural：免费 10 次/分钟。
- 下采样：均值会产生新颜色；众数/dominant 最适合像素画。
- 论文：Kopf & Lischinski 2011 Depixelizing；Kopf 2013；SD-πXL 2024（面向 beading/十字绣，24GB，数小时/张，仅离线精品）。2023–2026 无专门 AI 像素画清理论文。
- 链接：github.com/Astropulse/pixeldetector；jenissimo/unfake.js；painebenjamin/unfake.py；dev.to/jenissimo/how-to-tame-your-ai-pixel-art-3pk5；Hugo-Dz/spritefusion-pixel-snapper；dimtoneff/ComfyUI-PixelArt-Detector；hiivelabs.com adaptive-downscaling-pixel-art 博客。

## 4. 国内模型
- 即梦：Datawhale 教程提示词结构"像素风格插画…像素颗粒感强，线条简洁，色彩明快，模拟复古像素游戏画面，8-bit色彩质感"，每个元素加"像素化""简洁色块表现"。官方 API 即梦图生图 3.0 智能参考（req_key: jimeng_i2i_v30）单图+文本指令+scale；输出 512–1536。无官方像素风模板。volcengine.com/docs/85621/1747301
- Seedream 4.0/4.5/5.0：单张或多张（2–14）参考图 + prompt；论文 arXiv 2509.20427。无官方像素案例。
- 通义万相：wanx2.1-imageedit 支持 stylization_all（2 种风格，0.14 元/张）、stylization_local、doodle 线稿生图，有 strength。像素风不在支持列表。help.aliyun.com/zh/model-studio/wanx-image-edit-api-reference
- 可灵：kling-v3-image-generation 参考图生图。无像素资料。
- 豆包图像：无像素风公开案例。
- Datawhale 教程链接：github.com/datawhalechina/design-with-ai/.../Pixel - Style Image + Video Generation by JimengTutorial

## 5. 端到端方案
- 非 AI：Pixel It、Tezumie/Image-to-Pixel 315★、gametorch wasm、sd-webui-pixelart。
- 拼豆专用：Jett-Wu、a31521424/pixel-to-beads、yourlin/Fusible-Beads-Studio。
- AI 商用：Retro Diffusion img2img。

## 适用性判断
1. 本地 GPU 主线（8–12GB）：SDXL + nerijs/pixel-art-xl（1.2）+ ControlNet lineart/depth（0.5）img2img（strength 0.5–0.65）出 1024²；prompt `pixel, <主体>, simple, flat colors, limited palette`，negative `3d render, realistic, blurry, photograph`；再 unfake.process_image_sync(fixed_palette=拼豆色号, downscale_method="dominant", snap_grid=True)。2–10s/张。
2. 无 GPU：Retro Diffusion API（~$0.03/张）+ Pixel Fixer；或即梦 i2i 3.0 / Seedream 参考图 + "像素风格插画，简洁色块，无渐变"，然后本地 unfake 固定调色板量化。国内 API 无像素专项保证，需自行网格检测。
3. Flux Kontext Pixel LoRA 最"一句话转风格"但 ≥24GB。
4. SD-πXL 唯一论文中直接面向拼豆且可指定 n 色与 H×W，但仅离线。
5. 无论哪条路，最后都用 dominant/众数下采样而非均值，并在下采样后再做一次调色板吸附。
