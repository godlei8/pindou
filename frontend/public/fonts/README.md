# 字体

`fusion-pixel-12px-zh_hans-subset.woff2`

缝合像素字体 / Fusion Pixel Font 12px proportional zh_hans 的子集。

- 上游：https://github.com/TakWolf/fusion-pixel-font  版本 2026.09.01
- 协议：**SIL Open Font License 1.1**（见同目录 `OFL.txt`），无 Reserved Font Name，
  可自由商用、子集化、改名、再分发。
  ⚠️ GitHub 仓库侧边栏显示的 MIT 是**构建程序**的协议，不是字体的协议，别照抄。
- 子集内容：GB2312 一级汉字 3755 字 + 本项目界面/后端文案用字 + ASCII + 常用标点
  = 3910 码位，130 KB（完整字体 646 KB）

## 为什么选它

| | Fusion Pixel | Zpix | Cubic 11 |
|---|---|---|---|
| 商用授权 | OFL，免费 | **¥7000/产品，且条款禁止修改/转换/拆分** | OFL，免费 |
| 数字等宽 | ✅ 全部 600u | ❌ `1` 是 4px，其余 7px | ❌ 混合 |
| 汉字 advance | ✅ **1.000 em** | 1.083 em（13px） | 1.083 em（13px） |
| GB2312 一级 | 100% | 100% | 100% |
| GBK 覆盖 | 91.5% | 100% | 43.8% |
| 维护 | 每月发版 | 一年动几个字 | 最新 tag 未重编译 |

数字等宽 + 汉字 advance 恰好 1.000 em，意味着「2 个半角 = 1 个全角」严格成立，
满屏色号（A1/H2/R10）、百分比、坐标能按栅格对齐。这是本项目选它的决定性原因。

## 重新生成子集

```bash
# 下载 fusion-pixel-font-12px-proportional-ttf-v<版本>.zip，解压出 zh_hans.ttf
python -m fontTools.subset fusion-pixel-12px-proportional-zh_hans.ttf \
  --text-file=chars.txt --flavor=woff2 --layout-features='*' \
  --no-hinting --desubroutinize \
  --output-file=fusion-pixel-12px-zh_hans-subset.woff2
```
`chars.txt` = GB2312 一级汉字 + `grep` 出的项目用字。界面新增文案后需重跑。
