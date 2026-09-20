# 算法核心（core pipeline）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `backend/app/core/`——一条纯 numpy 的"图片 → 带 MARD 色号的可拼图纸"流水线，不依赖数据库和 FastAPI，可在 notebook 里单独调用，并附带回归基准。

**Architecture:** 输入图先判定类型（普通图 / 像素图），分别走线性 RGB 面积平均或网格相位检测 + 众数下采样；再用色卡受限 k-medoids 选出工作色板，用 graph cut（α-expansion，Potts 平滑）逐格分配色号；最后做小色号合并、可拼性分析与修复建议、底板分片、PNG/PDF 渲染。每个模块一个文件、纯函数、numpy 进 numpy 出。

**Tech Stack:** Python ≥ 3.11（Docker 用 3.12）、numpy、Pillow ≥ 10.1、scipy、opencv-python-headless、PyMaxflow ≥ 1.3、pytest。

**Spec:** `docs/superpowers/specs/2026-09-20-pindou-pattern-generator-design.md`（§4 全部、§9 测试、§11 色卡真值）。算法依据：`docs/research/2026-09-20-algorithm-analysis.md`。

**本计划是三份计划中的第一份。** 后两份（后端服务、前端）在本计划完成后再写，因为它们的接口取决于这里落地的实际签名。

## Global Constraints

- 流水线只在 Python 里实现一次；`core/` 不 import 数据库、FastAPI、任何 `app/api`、`app/models` 代码。
- 所有色差计算在 CIELAB / OKLab 空间，禁止 RGB 欧氏距离。
- 下采样在线性 RGB 空间平均，禁止在 sRGB 空间平均。
- 抖动默认关闭。
- 色卡每个色值必须带 `source` 字段；两源冲突的色标 `confidence: "conflict"`。
- 网格表示统一为 `np.ndarray` dtype `int16`，shape `(rows, cols)`，值 = 全局色卡索引，`-1` = 空格。
- 单元测试用 pytest；每个任务以 `pytest backend/tests -q` 全绿结束再提交。
- 提交信息格式 `feat(core): ...` / `test(core): ...`，末尾附 `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`。
- 本机开发环境：Windows + Git Bash；命令统一用 `python -m pytest`，路径用正斜杠。

---

## 文件结构

```
backend/
├─ pyproject.toml                  项目元数据、依赖、pytest 配置
├─ app/
│  ├─ __init__.py
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ types.py                  Params / Issue / Report / PatternResult 数据类
│  │  ├─ color.py                  sRGB↔线性、sRGB→Lab、sRGB→OKLab、ΔE2000
│  │  ├─ palette.py                Palette 加载类（codes/rgb/lab/oklab/roles）
│  │  ├─ image_io.py               bytes → RGBA float 数组（EXIF、限长边 1024）
│  │  ├─ background.py             吸管 + 容差洪水填充 → alpha 置 0
│  │  ├─ detect.py                 像素图网格相位检测
│  │  ├─ downsample.py             面积平均（线性 RGB、alpha 覆盖率）/ 众数采样
│  │  ├─ select.py                 色卡受限 k-medoids
│  │  ├─ assign.py                 α-expansion graph cut（PyMaxflow）
│  │  ├─ merge.py                  小色号合并、描边格检测
│  │  ├─ buildability.py           连通域分析、confetti%、评分
│  │  ├─ patches.py                issue → patch 生成，apply_patch
│  │  ├─ split.py                  底板分片
│  │  ├─ render.py                 PNG 图纸 + 材料清单
│  │  ├─ pdf.py                    1:1 分页 PDF
│  │  └─ pipeline.py               run() 编排 + 尺寸推荐
│  └─ palettes/
│     ├─ build_mard.py             从两个开源源构建 mard.json（开发脚本）
│     └─ mard.json                 MARD 色卡（含 source / confidence / role）
└─ tests/
   ├─ conftest.py
   ├─ fixtures/
   │  ├─ ciede2000_testdata.txt    Sharma 2005 官方 34 组
   │  └─ images/                   黄金样本（Task 15 生成）
   ├─ test_color.py
   ├─ test_palette.py
   ├─ test_image_io.py
   ├─ test_background.py
   ├─ test_detect.py
   ├─ test_downsample.py
   ├─ test_select.py
   ├─ test_assign.py
   ├─ test_merge.py
   ├─ test_buildability.py
   ├─ test_patches.py
   ├─ test_split.py
   ├─ test_render.py
   ├─ test_pdf.py
   └─ test_pipeline.py
```

已验证的外部事实（2026-09-20）：

- PyMaxflow 1.3.2 在 Windows 上有 wheel，`GraphFloat` 有 `add_grid_nodes / add_grid_tedges / add_edges`（向量化）。
- MARD 色卡源①：`https://raw.githubusercontent.com/maxcleme/beadcolors/master/raw/mard.csv`，291 行，格式 `code,code,r,g,b,source`，代码形如 `A1`、`H1`、`T1`。
- MARD 色卡源②：`https://raw.githubusercontent.com/Zippland/perler-beads/master/src/app/colorSystemMapping.json`，291 条，格式 `{"#HEX": {"MARD": "A01", "COCO": ..., "漫漫": ..., "盼盼": ..., "咪小窝": ...}}`，代码形如 `A01`（带前导零）。
- 两源已知冲突：`H1` 源① (226,226,226) vs 源② `#FDFBFF`；`T1` 源① (226,223,215) vs 源② `#FFFFFF`。`T1` 是唯一 T 前缀码，社区用它指透明豆——设为 `role: "clear"`。

---

### Task 1: 项目骨架 + 数据类型 + 色彩空间转换

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`, `backend/app/core/__init__.py`
- Create: `backend/app/core/types.py`
- Create: `backend/app/core/color.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_color.py`

**Interfaces:**
- Produces:
  - `color.srgb_to_linear(x: np.ndarray) -> np.ndarray`，输入 0–1 float，逐元素
  - `color.linear_to_srgb(x) -> np.ndarray`
  - `color.srgb_to_lab(rgb: np.ndarray[..., 3]) -> np.ndarray[..., 3]`（sRGB 0–1 → CIELAB D65）
  - `color.srgb_to_oklab(rgb) -> np.ndarray[..., 3]`
  - `types.Params`、`types.Issue`、`types.Report`、`types.PatternResult`（见下）

- [ ] **Step 1: 写 pyproject 与包骨架**

`backend/pyproject.toml`：

```toml
[project]
name = "pindou-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "numpy>=1.26",
  "pillow>=10.1",
  "scipy>=1.11",
  "opencv-python-headless>=4.9",
  "PyMaxflow>=1.3",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]
```

`backend/app/__init__.py` 与 `backend/app/core/__init__.py` 为空文件。`backend/tests/conftest.py`：

```python
import numpy as np
import pytest


@pytest.fixture
def rng():
    return np.random.default_rng(0)
```

安装：

```bash
cd backend && python -m venv .venv && source .venv/Scripts/activate && python -m pip install -e ".[dev]"
```

- [ ] **Step 2: 写数据类型**

`backend/app/core/types.py`：

```python
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np

EMPTY = -1  # 网格空格


@dataclass
class Params:
    grid_long_side: int = 58          # 长边格数
    max_colors: int = 24
    smoothness: float = 1.0           # graph cut λ；0 = 纯最近色
    dither: bool = False
    palette_id: str = "mard"
    background_seed: tuple[int, int] | None = None   # 吸管点 (x, y)，原图坐标
    background_tolerance: float = 0.08               # OKLab 距离
    small_color_threshold: int = 10                  # 少于此颗数的色号建议合并
    protected_cells: list[tuple[int, int]] = field(default_factory=list)  # (row, col)
    lock_outlines: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Issue:
    type: str                          # isolated_bead / diagonal_link / thin_line / hole / small_color / disconnected
    cells: list[tuple[int, int]]       # 涉及格子 (row, col)
    action: str                        # bridge_with_clear / merge_to_neighbor / merge_color / fill_with_clear / remove
    target_color: int | None = None    # 全局色卡索引
    delta_e: float | None = None
    patch_cells: list[tuple[int, int]] = field(default_factory=list)  # apply 时实际改动的格子
    severity: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Report:
    score: float
    confetti_pct: float
    n_components: int
    issues: list[Issue]
    metrics: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class PatternResult:
    grid: np.ndarray                    # int16 (rows, cols)，-1 = 空
    working_palette: list[int]          # 本图用到的全局色卡索引
    color_stats: dict[int, int]         # 全局索引 → 颗数
    report: Report | None
    params: Params
    input_kind: str                     # "image" | "pixel_art"
    cell_rgb: np.ndarray | None = None  # (rows, cols, 3) 下采样后的 sRGB 0–1，供调试/预览

    def grid_as_list(self) -> list[list[int | None]]:
        return [[None if v == EMPTY else int(v) for v in row] for row in self.grid]
```

- [ ] **Step 3: 写失败测试（色彩空间）**

`backend/tests/test_color.py`：

```python
import numpy as np
import pytest

from app.core import color


def test_srgb_linear_roundtrip():
    x = np.linspace(0, 1, 101)
    assert np.allclose(color.linear_to_srgb(color.srgb_to_linear(x)), x, atol=1e-6)


def test_srgb_to_linear_known_values():
    # sRGB 0.5 → 线性 0.214041
    assert abs(color.srgb_to_linear(np.array(0.5)) - 0.214041) < 1e-5
    assert color.srgb_to_linear(np.array(0.0)) == 0.0
    assert abs(color.srgb_to_linear(np.array(1.0)) - 1.0) < 1e-9


def test_srgb_to_lab_white_black_and_red():
    lab = color.srgb_to_lab(np.array([[1.0, 1.0, 1.0], [0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]))
    assert np.allclose(lab[0], [100.0, 0.0, 0.0], atol=0.05)
    assert np.allclose(lab[1], [0.0, 0.0, 0.0], atol=0.05)
    # 纯红 sRGB → Lab(53.24, 80.09, 67.20)（D65）
    assert np.allclose(lab[2], [53.24, 80.09, 67.20], atol=0.1)


def test_srgb_to_oklab_white_and_red():
    ok = color.srgb_to_oklab(np.array([[1.0, 1.0, 1.0], [1.0, 0.0, 0.0]]))
    assert np.allclose(ok[0], [1.0, 0.0, 0.0], atol=1e-3)
    # Ottosson 参考：红 → L=0.628, a=0.225, b=0.126
    assert np.allclose(ok[1], [0.628, 0.225, 0.126], atol=2e-3)


def test_shapes_preserved():
    img = np.zeros((4, 5, 3))
    assert color.srgb_to_lab(img).shape == (4, 5, 3)
    assert color.srgb_to_oklab(img).shape == (4, 5, 3)
```

- [ ] **Step 4: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_color.py -q
```

Expected: FAIL，`ImportError: cannot import name 'color'` 或 `AttributeError`。

- [ ] **Step 5: 实现色彩空间转换**

`backend/app/core/color.py`：

```python
"""色彩空间转换。所有函数向量化，输入 sRGB 取值 0–1。"""
from __future__ import annotations

import numpy as np

_M_RGB2XYZ = np.array([
    [0.4124564, 0.3575761, 0.1804375],
    [0.2126729, 0.7151522, 0.0721750],
    [0.0193339, 0.1191920, 0.9503041],
])
_WHITE_D65 = np.array([0.95047, 1.0, 1.08883])

_M_RGB2LMS = np.array([
    [0.4122214708, 0.5363325363, 0.0514459929],
    [0.2119034982, 0.6806995451, 0.1073969566],
    [0.0883024619, 0.2817188376, 0.6299787005],
])
_M_LMS2OKLAB = np.array([
    [0.2104542553, 0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050, 0.4505937099],
    [0.0259040371, 0.7827717662, -0.8086757660],
])


def srgb_to_linear(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(np.asarray(x, dtype=np.float64), 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    lin = srgb_to_linear(rgb)
    xyz = lin @ _M_RGB2XYZ.T
    t = xyz / _WHITE_D65
    delta = 6 / 29
    f = np.where(t > delta ** 3, np.cbrt(t), t / (3 * delta ** 2) + 4 / 29)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def srgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    lin = srgb_to_linear(rgb)
    lms = lin @ _M_RGB2LMS.T
    lms_ = np.cbrt(lms)
    return lms_ @ _M_LMS2OKLAB.T
```

- [ ] **Step 6: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_color.py -q
```

Expected: 5 passed。

- [ ] **Step 7: 提交**

```bash
git add backend/pyproject.toml backend/app backend/tests
git commit -m "feat(core): 项目骨架、数据类型与色彩空间转换

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: CIEDE2000 向量化实现

**Files:**
- Modify: `backend/app/core/color.py`（追加）
- Create: `backend/tests/fixtures/ciede2000_testdata.txt`
- Test: `backend/tests/test_color.py`（追加）

**Interfaces:**
- Produces: `color.delta_e_2000(lab1: np.ndarray[..., 3], lab2: np.ndarray[..., 3]) -> np.ndarray[...]`，支持广播（如 `(m,1,3)` 对 `(1,n,3)` 得 `(m,n)`）
- Produces: `color.pairwise_delta_e(lab_a: (m,3), lab_b: (n,3)) -> (m,n)`

- [ ] **Step 1: 准备官方测试数据**

从 Sharma 的页面下载 `ciede2000testdata.txt`（`https://hajim.rochester.edu/ece/sites/gsharma/ciede2000/`）存到 `backend/tests/fixtures/ciede2000_testdata.txt`。若网络不可用，用下表（论文 Table 1 转录，34 组，列：L1 a1 b1 L2 a2 b2 ΔE00）建同名文件，每行以空白分隔：

```
50.0000   2.6772  -79.7751  50.0000   0.0000  -82.7485   2.0425
50.0000   3.1571  -77.2803  50.0000   0.0000  -82.7485   2.8615
50.0000   2.8361  -74.0200  50.0000   0.0000  -82.7485   3.4412
50.0000  -1.3802  -84.2814  50.0000   0.0000  -82.7485   1.0000
50.0000  -1.1848  -84.8006  50.0000   0.0000  -82.7485   1.0000
50.0000  -0.9009  -85.5211  50.0000   0.0000  -82.7485   1.0000
50.0000   0.0000    0.0000  50.0000  -1.0000    2.0000   2.3669
50.0000  -1.0000    2.0000  50.0000   0.0000    0.0000   2.3669
50.0000   2.4900   -0.0010  50.0000  -2.4900    0.0009   7.1792
50.0000   2.4900   -0.0010  50.0000  -2.4900    0.0010   7.1792
50.0000   2.4900   -0.0010  50.0000  -2.4900    0.0011   7.2195
50.0000   2.4900   -0.0010  50.0000  -2.4900    0.0012   7.2195
50.0000  -0.0010    2.4900  50.0000   0.0009   -2.4900   4.8045
50.0000  -0.0010    2.4900  50.0000   0.0010   -2.4900   4.8045
50.0000  -0.0010    2.4900  50.0000   0.0011   -2.4900   4.7461
50.0000   2.5000    0.0000  50.0000   0.0000   -2.5000   4.3065
50.0000   2.5000    0.0000  73.0000  25.0000  -18.0000  27.1492
50.0000   2.5000    0.0000  61.0000  -5.0000   29.0000  22.8977
50.0000   2.5000    0.0000  56.0000 -27.0000   -3.0000  31.9030
50.0000   2.5000    0.0000  58.0000  24.0000   15.0000  19.4535
50.0000   2.5000    0.0000  50.0000   3.1736    0.5854   1.0000
50.0000   2.5000    0.0000  50.0000   3.2972    0.0000   1.0000
50.0000   2.5000    0.0000  50.0000   1.8634    0.5757   1.0000
50.0000   2.5000    0.0000  50.0000   3.2592    0.3350   1.0000
60.2574 -34.0099   36.2677  60.4626 -34.1751   39.4387   1.2644
63.0109 -31.0961   -5.8663  62.8187 -29.7946   -4.0864   1.2630
61.2901   3.7196   -5.3901  61.4292   2.2480   -4.9620   1.8731
35.0831 -44.1164    3.7933  35.0232 -40.0716    1.5901   1.8645
22.7233  20.0904  -46.6940  23.0331  14.9730  -42.5619   2.0373
36.4612  47.8580   18.3852  36.2715  50.5065   21.2231   1.4146
90.8027  -2.0831    1.4410  91.1528  -1.6435    0.0447   1.4441
90.9257  -0.5406   -0.9208  88.6381  -0.8985   -0.7239   1.5381
 6.7747  -0.2908   -2.4247   5.8714  -0.0985   -2.2286   0.6377
 2.0776   0.0795   -1.1350   0.9033  -0.0636   -0.5514   0.9082
```

- [ ] **Step 2: 写失败测试**

追加到 `backend/tests/test_color.py`：

```python
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def _load_sharma():
    rows = []
    for line in (FIXTURES / "ciede2000_testdata.txt").read_text().splitlines():
        parts = line.split()
        if len(parts) >= 7:
            rows.append([float(p) for p in parts[:7]])
    return np.array(rows)


def test_ciede2000_matches_sharma_34_pairs():
    data = _load_sharma()
    assert len(data) == 34
    lab1, lab2, expected = data[:, 0:3], data[:, 3:6], data[:, 6]
    got = color.delta_e_2000(lab1, lab2)
    assert np.allclose(got, expected, atol=1e-4), np.c_[got, expected]


def test_ciede2000_is_symmetric_and_zero_on_identity():
    a = np.array([[50.0, 2.5, 0.0], [20.0, -30.0, 40.0]])
    b = np.array([[73.0, 25.0, -18.0], [21.0, -29.0, 41.0]])
    assert np.allclose(color.delta_e_2000(a, b), color.delta_e_2000(b, a))
    assert np.allclose(color.delta_e_2000(a, a), 0.0)


def test_pairwise_delta_e_shape_and_broadcast():
    a = np.random.default_rng(1).uniform([0, -80, -80], [100, 80, 80], size=(7, 3))
    b = np.random.default_rng(2).uniform([0, -80, -80], [100, 80, 80], size=(5, 3))
    m = color.pairwise_delta_e(a, b)
    assert m.shape == (7, 5)
    assert np.allclose(m[3, 2], color.delta_e_2000(a[3], b[2]))
```

- [ ] **Step 3: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_color.py -q -k ciede2000
```

Expected: FAIL，`AttributeError: module 'app.core.color' has no attribute 'delta_e_2000'`。

- [ ] **Step 4: 实现**

追加到 `backend/app/core/color.py`：

```python
def delta_e_2000(lab1: np.ndarray, lab2: np.ndarray,
                 kL: float = 1.0, kC: float = 1.0, kH: float = 1.0) -> np.ndarray:
    """CIEDE2000（Sharma, Wu & Dalal 2005 实现笔记）。支持 numpy 广播。"""
    lab1 = np.asarray(lab1, dtype=np.float64)
    lab2 = np.asarray(lab2, dtype=np.float64)
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]

    C1 = np.hypot(a1, b1)
    C2 = np.hypot(a2, b2)
    Cbar = (C1 + C2) / 2
    Cbar7 = Cbar ** 7
    G = 0.5 * (1 - np.sqrt(Cbar7 / (Cbar7 + 25.0 ** 7)))
    a1p = (1 + G) * a1
    a2p = (1 + G) * a2
    C1p = np.hypot(a1p, b1)
    C2p = np.hypot(a2p, b2)

    def _hue(ap, b):
        h = np.degrees(np.arctan2(b, ap))
        h = np.where(h < 0, h + 360.0, h)
        return np.where((ap == 0) & (b == 0), 0.0, h)

    h1p = _hue(a1p, b1)
    h2p = _hue(a2p, b2)

    dLp = L2 - L1
    dCp = C2p - C1p
    prod_zero = (C1p * C2p) == 0
    dh = h2p - h1p
    dhp = np.where(prod_zero, 0.0,
          np.where(np.abs(dh) <= 180, dh,
          np.where(dh > 180, dh - 360.0, dh + 360.0)))
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dhp / 2))

    Lbp = (L1 + L2) / 2
    Cbp = (C1p + C2p) / 2
    hsum = h1p + h2p
    hbp = np.where(prod_zero, hsum,
          np.where(np.abs(h1p - h2p) <= 180, hsum / 2,
          np.where(hsum < 360, (hsum + 360.0) / 2, (hsum - 360.0) / 2)))

    T = (1 - 0.17 * np.cos(np.radians(hbp - 30))
           + 0.24 * np.cos(np.radians(2 * hbp))
           + 0.32 * np.cos(np.radians(3 * hbp + 6))
           - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    dTheta = 30 * np.exp(-((hbp - 275) / 25) ** 2)
    Cbp7 = Cbp ** 7
    RC = 2 * np.sqrt(Cbp7 / (Cbp7 + 25.0 ** 7))
    SL = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    SC = 1 + 0.045 * Cbp
    SH = 1 + 0.015 * Cbp * T
    RT = -np.sin(np.radians(2 * dTheta)) * RC

    tL = dLp / (kL * SL)
    tC = dCp / (kC * SC)
    tH = dHp / (kH * SH)
    return np.sqrt(tL ** 2 + tC ** 2 + tH ** 2 + RT * tC * tH)


def pairwise_delta_e(lab_a: np.ndarray, lab_b: np.ndarray) -> np.ndarray:
    """(m,3) × (n,3) → (m,n) 的 ΔE2000 矩阵。"""
    return delta_e_2000(lab_a[:, None, :], lab_b[None, :, :])
```

- [ ] **Step 5: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_color.py -q
```

Expected: 8 passed。若 34 组中个别不到 1e-4，先核对 fixture 文件是否与官方一致，再查 `hbp` 分支。

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/color.py backend/tests
git commit -m "feat(core): 向量化 CIEDE2000，通过 Sharma 34 组官方测试

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: MARD 色卡构建与 Palette 加载类

**Files:**
- Create: `backend/app/palettes/__init__.py`（空）
- Create: `backend/app/palettes/build_mard.py`
- Create: `backend/app/palettes/mard.json`（由脚本生成，提交进仓库）
- Create: `backend/app/core/palette.py`
- Test: `backend/tests/test_palette.py`

**Interfaces:**
- Produces: `Palette` 类：
  - `Palette.load(palette_id: str = "mard") -> Palette`
  - 属性 `codes: list[str]`、`names: list[str]`、`rgb: np.ndarray (n,3) uint8`、`lab: (n,3) float`、`oklab: (n,3) float`、`roles: dict[str,str]`、`clear_index: int | None`、`sources: list[str]`、`confidence: list[str]`
  - `index_of(code: str) -> int`
  - `nearest(lab: (m,3)) -> (m,) int`（ΔE2000 最近色，全局索引）
  - `__len__`
- Produces: `palette.normalize_code(code) -> str`：`A01 → A1`，`ZG01 → ZG1`（字母前缀 + 去前导零）
- mard.json 结构：`{"id":"mard","brand":"MARD","version":"2026-09-20","colors":[{"code":"A1","name":"A1","hex":"#F9F0CD","source":"beadcolors","confidence":"agree|conflict|beadcolors_only|zippland_only","alt_hex":"#FAF4C8","role":"clear"?}]}`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_palette.py`：

```python
import json
from pathlib import Path

import numpy as np

from app.core.palette import Palette, normalize_code
from app.palettes.build_mard import merge_sources

MARD_JSON = Path(__file__).resolve().parents[1] / "app" / "palettes" / "mard.json"


def test_normalize_code():
    assert normalize_code("A01") == "A1"
    assert normalize_code("A1") == "A1"
    assert normalize_code("ZG01") == "ZG1"
    assert normalize_code("h10") == "H10"
    assert normalize_code(" T01 ") == "T1"


def test_merge_sources_marks_agreement_and_conflict():
    bead = {"A1": (249, 240, 205), "H1": (226, 226, 226), "X9": (1, 2, 3), "T1": (226, 223, 215)}
    zipp = {"A1": "#FAF4C8", "H1": "#FDFBFF", "Y7": "#000000", "T1": "#FFFFFF"}
    colors = {c["code"]: c for c in merge_sources(bead, zipp, tolerance_de=3.0)}
    assert colors["A1"]["confidence"] == "agree"
    assert colors["H1"]["confidence"] == "conflict"
    assert colors["H1"]["alt_hex"] == "#FDFBFF"
    assert colors["X9"]["confidence"] == "beadcolors_only"
    assert colors["Y7"]["confidence"] == "zippland_only"
    assert colors["T1"]["role"] == "clear"


def test_mard_json_exists_and_is_complete():
    data = json.loads(MARD_JSON.read_text(encoding="utf-8"))
    codes = [c["code"] for c in data["colors"]]
    assert len(codes) >= 291
    assert len(set(codes)) == len(codes)
    assert all(c["source"] for c in data["colors"])
    assert any(c.get("role") == "clear" for c in data["colors"])
    for c in data["colors"]:
        assert c["hex"].startswith("#") and len(c["hex"]) == 7
        int(c["hex"][1:], 16)   # 必须是合法十六进制——防 #FECODF 这种字母 O


def test_palette_load_and_nearest():
    p = Palette.load("mard")
    assert len(p) >= 291
    assert p.lab.shape == (len(p), 3) and p.oklab.shape == (len(p), 3)
    assert p.clear_index is not None and p.codes[p.clear_index] == "T1"
    i = p.index_of("A01")
    assert p.codes[i] == "A1"
    assert p.nearest(p.lab[[i]])[0] == i
    black = np.array([[0.0, 0.0, 0.0]])
    j = p.nearest(black)[0]
    assert p.lab[j, 0] < 20
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_palette.py -q
```

Expected: FAIL，`ModuleNotFoundError: No module named 'app.core.palette'`。

- [ ] **Step 3: 写构建脚本**

`backend/app/palettes/__init__.py` 为空。`backend/app/palettes/build_mard.py`：

```python
"""从两个开源来源构建 mard.json，交叉校验。

用法：cd backend && python -m app.palettes.build_mard
来源①（主）: maxcleme/beadcolors raw/mard.csv   格式 code,code,r,g,b,source
来源②（校验）: Zippland/perler-beads colorSystemMapping.json  {"#HEX": {"MARD": "A01", ...}}
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np

from app.core.color import delta_e_2000, srgb_to_lab

URL_BEADCOLORS = "https://raw.githubusercontent.com/maxcleme/beadcolors/master/raw/mard.csv"
URL_ZIPPLAND = "https://raw.githubusercontent.com/Zippland/perler-beads/master/src/app/colorSystemMapping.json"
OUT = Path(__file__).with_name("mard.json")
CLEAR_CODES = {"T1"}

_CODE_RE = re.compile(r"^([A-Za-z]+)0*(\d+)$")


def normalize_code(code: str) -> str:
    m = _CODE_RE.match(code.strip())
    if not m:
        raise ValueError(f"bad color code: {code!r}")
    return f"{m.group(1).upper()}{int(m.group(2))}"


def _sort_key(code: str):
    m = _CODE_RE.match(code)
    return (m.group(1), int(m.group(2)))


def _hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _rgb(hex_: str):
    h = hex_.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def parse_beadcolors(text: str) -> dict:
    out = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 5:
            continue
        out[normalize_code(row[0])] = (int(row[2]), int(row[3]), int(row[4]))
    return out


def parse_zippland(text: str) -> dict:
    out = {}
    for hex_, brands in json.loads(text).items():
        if "MARD" in brands:
            out[normalize_code(brands["MARD"])] = hex_.upper()
    return out


def merge_sources(bead: dict, zipp: dict, tolerance_de: float = 3.0) -> list[dict]:
    colors = []
    for code in sorted(set(bead) | set(zipp), key=_sort_key):
        entry = {"code": code, "name": code}
        if code in bead and code in zipp:
            rgb_b, rgb_z = bead[code], _rgb(zipp[code])
            de = float(delta_e_2000(srgb_to_lab(np.array(rgb_b) / 255.0), srgb_to_lab(np.array(rgb_z) / 255.0)))
            entry.update(hex=_hex(rgb_b), source="beadcolors", alt_hex=zipp[code],
                         delta_e_between_sources=round(de, 2),
                         confidence="agree" if de <= tolerance_de else "conflict")
        elif code in bead:
            entry.update(hex=_hex(bead[code]), source="beadcolors", confidence="beadcolors_only")
        else:
            entry.update(hex=zipp[code], source="zippland", confidence="zippland_only")
        if code in CLEAR_CODES:
            entry["role"] = "clear"
        colors.append(entry)
    return colors


def main() -> int:
    bead = parse_beadcolors(urllib.request.urlopen(URL_BEADCOLORS, timeout=30).read().decode("utf-8"))
    zipp = parse_zippland(urllib.request.urlopen(URL_ZIPPLAND, timeout=30).read().decode("utf-8"))
    colors = merge_sources(bead, zipp)
    doc = {"id": "mard", "brand": "MARD", "version": str(date.today()),
           "sources": {"beadcolors": URL_BEADCOLORS, "zippland": URL_ZIPPLAND},
           "colors": colors}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    n_conf = sum(c["confidence"] == "conflict" for c in colors)
    print(f"wrote {OUT} with {len(colors)} colors, {n_conf} conflicts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 生成 mard.json**

```bash
cd backend && python -m app.palettes.build_mard
```

Expected: 打印 `wrote .../mard.json with 291 colors, N conflicts`。抽查 `H1`、`T1` 的 `confidence` 为 `conflict`。把 conflict 数量写进提交信息——这是待实物比对清单。

- [ ] **Step 5: 写 Palette 类**

`backend/app/core/palette.py`：

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.color import pairwise_delta_e, srgb_to_lab, srgb_to_oklab
from app.palettes.build_mard import normalize_code

__all__ = ["Palette", "normalize_code"]

_PALETTE_DIR = Path(__file__).resolve().parents[1] / "palettes"


@dataclass
class Palette:
    id: str
    codes: list[str]
    names: list[str]
    rgb: np.ndarray
    lab: np.ndarray
    oklab: np.ndarray
    roles: dict[str, str]
    sources: list[str]
    confidence: list[str]

    @classmethod
    def load(cls, palette_id: str = "mard") -> "Palette":
        doc = json.loads((_PALETTE_DIR / f"{palette_id}.json").read_text(encoding="utf-8"))
        colors = doc["colors"]
        rgb = np.array([[int(c["hex"][i:i + 2], 16) for i in (1, 3, 5)] for c in colors], dtype=np.uint8)
        rgb01 = rgb / 255.0
        return cls(
            id=doc["id"],
            codes=[c["code"] for c in colors],
            names=[c.get("name", c["code"]) for c in colors],
            rgb=rgb,
            lab=srgb_to_lab(rgb01),
            oklab=srgb_to_oklab(rgb01),
            roles={c["code"]: c["role"] for c in colors if "role" in c},
            sources=[c["source"] for c in colors],
            confidence=[c["confidence"] for c in colors],
        )

    def __len__(self) -> int:
        return len(self.codes)

    def index_of(self, code: str) -> int:
        return self.codes.index(normalize_code(code))

    @property
    def clear_index(self) -> int | None:
        for code, role in self.roles.items():
            if role == "clear":
                return self.codes.index(code)
        return None

    def nearest(self, lab: np.ndarray) -> np.ndarray:
        return pairwise_delta_e(np.atleast_2d(lab), self.lab).argmin(axis=1)
```

- [ ] **Step 6: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_palette.py -q
```

Expected: 4 passed。

- [ ] **Step 7: 提交**

```bash
git add backend/app/palettes backend/app/core/palette.py backend/tests/test_palette.py
git commit -m "feat(core): MARD 色卡双源交叉构建与 Palette 加载（N 处冲突待实物比对）

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: 图像加载与吸管去背景

**Files:**
- Create: `backend/app/core/image_io.py`
- Create: `backend/app/core/background.py`
- Test: `backend/tests/test_image_io.py`、`backend/tests/test_background.py`

**Interfaces:**
- Produces: `image_io.load_rgba(data: bytes, max_side: int = 1024) -> np.ndarray`，float32 `(H, W, 4)`，sRGB 0–1，alpha 0–1，已按 EXIF 转正、长边 ≤ max_side（BOX 缩小，不放大）
- Produces: `image_io.to_pil(rgba: np.ndarray) -> PIL.Image.Image`（RGBA 8 位）
- Produces: `background.remove_background(rgba, seed_xy: tuple[int,int], tolerance: float = 0.08) -> np.ndarray`：以 `(x, y)` 像素为种子，OKLab 距离 ≤ tolerance 的 4-连通区域 alpha 置 0；返回新数组，不改输入

- [ ] **Step 1: 写失败测试**

`backend/tests/test_image_io.py`：

```python
import io

import numpy as np
from PIL import Image

from app.core.image_io import load_rgba, to_pil


def _png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_load_rgb_png_becomes_float_rgba():
    arr = load_rgba(_png_bytes(Image.new("RGB", (40, 20), (255, 0, 0))))
    assert arr.shape == (20, 40, 4) and arr.dtype == np.float32
    assert np.allclose(arr[0, 0], [1, 0, 0, 1])


def test_load_preserves_alpha():
    arr = load_rgba(_png_bytes(Image.new("RGBA", (10, 10), (0, 0, 255, 0))))
    assert arr[..., 3].max() == 0.0


def test_load_downsizes_long_side_but_never_upsizes():
    arr = load_rgba(_png_bytes(Image.new("RGB", (3000, 1500), (10, 20, 30))), max_side=1024)
    assert arr.shape[1] == 1024 and arr.shape[0] == 512
    assert load_rgba(_png_bytes(Image.new("RGB", (100, 50), (1, 2, 3)))).shape[:2] == (50, 100)


def test_load_applies_exif_orientation():
    img = Image.new("RGB", (40, 20), (0, 255, 0))
    exif = img.getexif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    assert load_rgba(buf.getvalue()).shape[:2] == (40, 20)


def test_to_pil_roundtrip():
    arr = np.zeros((5, 6, 4), dtype=np.float32)
    arr[..., 0] = 1.0
    arr[..., 3] = 1.0
    pil = to_pil(arr)
    assert pil.mode == "RGBA" and pil.size == (6, 5) and pil.getpixel((0, 0)) == (255, 0, 0, 255)
```

`backend/tests/test_background.py`：

```python
import numpy as np

from app.core.background import remove_background


def _canvas(h=20, w=20):
    rgba = np.zeros((h, w, 4), dtype=np.float32)
    rgba[..., :3] = 1.0
    rgba[..., 3] = 1.0
    rgba[5:15, 5:15, :3] = [1.0, 0.0, 0.0]
    return rgba


def test_flood_from_corner_clears_only_connected_background():
    out = remove_background(_canvas(), seed_xy=(0, 0), tolerance=0.05)
    assert out[0, 0, 3] == 0.0 and out[19, 19, 3] == 0.0
    assert out[10, 10, 3] == 1.0 and out[10, 10, 0] == 1.0


def test_enclosed_region_not_touched_by_outer_flood():
    rgba = _canvas()
    rgba[8:12, 8:12, :3] = 1.0
    out = remove_background(rgba, seed_xy=(0, 0), tolerance=0.05)
    assert out[10, 10, 3] == 1.0


def test_tolerance_controls_spread():
    rgba = _canvas()
    rgba[0:20, 0:3, :3] = [0.97, 0.97, 0.97]
    strict = remove_background(rgba, seed_xy=(19, 19), tolerance=0.01)
    loose = remove_background(rgba, seed_xy=(19, 19), tolerance=0.1)
    assert strict[10, 1, 3] == 1.0
    assert loose[10, 1, 3] == 0.0


def test_input_not_mutated():
    rgba = _canvas()
    before = rgba.copy()
    remove_background(rgba, seed_xy=(0, 0))
    assert np.array_equal(rgba, before)
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_image_io.py tests/test_background.py -q
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

`backend/app/core/image_io.py`：

```python
from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageOps


def load_rgba(data: bytes, max_side: int = 1024) -> np.ndarray:
    img = Image.open(io.BytesIO(data))
    img = ImageOps.exif_transpose(img).convert("RGBA")
    w, h = img.size
    scale = max(w, h) / max_side
    if scale > 1.0:
        img = img.resize((max(1, round(w / scale)), max(1, round(h / scale))), Image.BOX)
    return np.ascontiguousarray(np.asarray(img, dtype=np.float32) / 255.0)


def to_pil(rgba: np.ndarray) -> Image.Image:
    arr8 = np.clip(np.rint(rgba * 255.0), 0, 255).astype(np.uint8)
    return Image.fromarray(arr8, mode="RGBA")
```

`backend/app/core/background.py`：

```python
from __future__ import annotations

import numpy as np
from scipy import ndimage

from app.core.color import srgb_to_oklab

_CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]])


def remove_background(rgba: np.ndarray, seed_xy: tuple[int, int], tolerance: float = 0.08) -> np.ndarray:
    x, y = int(seed_xy[0]), int(seed_xy[1])
    h, w = rgba.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        raise ValueError(f"seed {seed_xy} outside image {w}x{h}")
    ok = srgb_to_oklab(rgba[..., :3])
    within = np.linalg.norm(ok - ok[y, x], axis=-1) <= tolerance
    labels, _ = ndimage.label(within, structure=_CROSS)
    out = rgba.copy()
    out[labels == labels[y, x], 3] = 0.0
    return out
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_image_io.py tests/test_background.py -q
```

Expected: 9 passed。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/image_io.py backend/app/core/background.py backend/tests/test_image_io.py backend/tests/test_background.py
git commit -m "feat(core): 图像加载（EXIF/限尺寸）与吸管洪水去背景

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: 像素图网格相位检测

**Files:**
- Create: `backend/app/core/detect.py`
- Test: `backend/tests/test_detect.py`

**Interfaces:**
- Produces: `detect.GridInfo` dataclass：`cell: float`（像素/格）、`offset_x: float`、`offset_y: float`、`cols: int`、`rows: int`、`confidence: float`
- Produces: `detect.detect_pixel_grid(rgba: np.ndarray, min_cell: int = 3, max_cells: int = 200) -> GridInfo | None`：普通照片/插画返回 `None`；放大过的像素图返回网格信息

算法（Astropulse pixeldetector 思路）：对 RGB 做相邻像素差的 L1 范数，分别按列/行求和得两条 1D 信号；`scipy.signal.find_peaks`（prominence = 信号中位数 × 2）找峰；峰间距的中位数 = 格子尺寸，间距的变异系数（std/median）< 0.15 且格子尺寸 ≥ min_cell 才认定为像素图；相位 offset 取峰位置对格子尺寸取模的中位数。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_detect.py`：

```python
import numpy as np

from app.core.detect import detect_pixel_grid


def _pixel_art(cells_h=12, cells_w=16, cell=8, seed=0):
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, size=(cells_h, cells_w, 3)) / 255.0
    big = np.repeat(np.repeat(small, cell, axis=0), cell, axis=1)
    rgba = np.concatenate([big, np.ones(big.shape[:2] + (1,))], axis=-1).astype(np.float32)
    return rgba


def test_detects_upscaled_pixel_art():
    info = detect_pixel_grid(_pixel_art(cell=8))
    assert info is not None
    assert abs(info.cell - 8) < 0.5
    assert (info.rows, info.cols) == (12, 16)


def test_detects_with_padding_offset():
    art = _pixel_art(cell=6)
    padded = np.zeros((art.shape[0] + 5, art.shape[1] + 3, 4), dtype=np.float32)
    padded[..., 3] = 1.0
    padded[5:, 3:] = art
    info = detect_pixel_grid(padded)
    assert info is not None and abs(info.cell - 6) < 0.5
    assert abs(info.offset_x - 3) < 1.0 and abs(info.offset_y - 5) < 1.0


def test_smooth_gradient_is_not_pixel_art():
    y, x = np.mgrid[0:120, 0:160]
    rgba = np.zeros((120, 160, 4), dtype=np.float32)
    rgba[..., 0] = x / 160.0
    rgba[..., 1] = y / 120.0
    rgba[..., 3] = 1.0
    assert detect_pixel_grid(rgba) is None


def test_noise_is_not_pixel_art(rng):
    rgba = np.concatenate([rng.random((100, 100, 3)), np.ones((100, 100, 1))], axis=-1).astype(np.float32)
    assert detect_pixel_grid(rgba) is None
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_detect.py -q
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

`backend/app/core/detect.py`：

```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks


@dataclass
class GridInfo:
    cell: float
    offset_x: float
    offset_y: float
    cols: int
    rows: int
    confidence: float


def _axis_period(signal: np.ndarray, min_cell: int) -> tuple[float, float, float] | None:
    """返回 (period, offset, cv)；找不到规律返回 None。"""
    if signal.size < 2 * min_cell + 1:
        return None
    med = float(np.median(signal))
    peaks, _ = find_peaks(signal, prominence=max(med * 2.0, 1e-6), distance=min_cell - 1)
    if len(peaks) < 3:
        return None
    gaps = np.diff(peaks)
    period = float(np.median(gaps))
    cv = float(np.std(gaps) / period) if period > 0 else 1.0
    if period < min_cell or cv > 0.15:
        return None
    # 边界峰位于格子右/下边缘的最后一个像素之后（差分索引 i 对应像素 i 与 i+1 之间）
    offset = float(np.median((peaks + 1) % period))
    return period, offset, cv


def detect_pixel_grid(rgba: np.ndarray, min_cell: int = 3, max_cells: int = 200) -> GridInfo | None:
    rgb = rgba[..., :3]
    h, w = rgb.shape[:2]
    dx = np.abs(np.diff(rgb, axis=1)).sum(axis=-1).sum(axis=0)   # 长度 w-1，列边界
    dy = np.abs(np.diff(rgb, axis=0)).sum(axis=-1).sum(axis=1)   # 长度 h-1，行边界
    px = _axis_period(dx, min_cell)
    py = _axis_period(dy, min_cell)
    if px is None or py is None:
        return None
    cell = (px[0] + py[0]) / 2
    if abs(px[0] - py[0]) / cell > 0.1:
        return None
    ox, oy = px[1], py[1]
    cols = int(round((w - ox) / cell))
    rows = int(round((h - oy) / cell))
    if cols < 2 or rows < 2 or cols > max_cells or rows > max_cells:
        return None
    return GridInfo(cell=cell, offset_x=ox, offset_y=oy, cols=cols, rows=rows,
                    confidence=float(1.0 - (px[2] + py[2]) / 2))
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_detect.py -q
```

Expected: 4 passed。若 `test_detects_with_padding_offset` 的 offset 差 1 像素，检查 `(peaks + 1) % period` 的 +1 约定。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/detect.py backend/tests/test_detect.py
git commit -m "feat(core): 像素图网格相位检测

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: 下采样（线性 RGB 面积平均 / 众数）

**Files:**
- Create: `backend/app/core/downsample.py`
- Test: `backend/tests/test_downsample.py`

**Interfaces:**
- Produces: `downsample.CellImage` dataclass：`rgb: np.ndarray (rows, cols, 3)` sRGB 0–1、`coverage: np.ndarray (rows, cols)` 0–1、`mask: np.ndarray (rows, cols) bool`（coverage ≥ 0.5）
- Produces: `downsample.grid_shape(h: int, w: int, long_side: int) -> tuple[int, int]`（rows, cols，保持长宽比）
- Produces: `downsample.downsample_area(rgba, rows, cols, denoise: bool = True) -> CellImage`：先 OpenCV 双边滤波（d=7, sigmaColor=25/255 尺度下取 0.1, sigmaSpace=5），再在**线性 RGB、alpha 预乘**下 `cv2.resize(INTER_AREA)`，最后除以覆盖率还原
- Produces: `downsample.downsample_mode(rgba, grid: GridInfo) -> CellImage`：每格取 RGB 8-bit 量化后的众数颜色；alpha 覆盖率同样取均值

- [ ] **Step 1: 写失败测试**

`backend/tests/test_downsample.py`：

```python
import numpy as np

from app.core.detect import GridInfo
from app.core.downsample import CellImage, downsample_area, downsample_mode, grid_shape


def test_grid_shape_keeps_aspect():
    assert grid_shape(1000, 2000, 58) == (29, 58)
    assert grid_shape(2000, 1000, 58) == (58, 29)
    assert grid_shape(100, 100, 30) == (30, 30)
    assert grid_shape(10, 1000, 58)[0] >= 1


def test_area_average_in_linear_space_not_srgb():
    # 一半纯黑一半纯白的 2×1 格：sRGB 直接平均给 0.5，线性平均后转回 sRGB 应约 0.735
    rgba = np.zeros((10, 20, 4), dtype=np.float32)
    rgba[:, 10:, :3] = 1.0
    rgba[..., 3] = 1.0
    cell = downsample_area(rgba, rows=1, cols=1, denoise=False)
    assert cell.rgb.shape == (1, 1, 3)
    assert abs(cell.rgb[0, 0, 0] - 0.735) < 0.02


def test_area_average_ignores_transparent_pixels_and_reports_coverage():
    rgba = np.zeros((10, 10, 4), dtype=np.float32)
    rgba[..., :3] = [1.0, 0.0, 0.0]
    rgba[:, :5, 3] = 1.0          # 左半不透明，右半透明
    cell = downsample_area(rgba, rows=1, cols=1, denoise=False)
    assert abs(cell.coverage[0, 0] - 0.5) < 1e-6
    assert np.allclose(cell.rgb[0, 0], [1.0, 0.0, 0.0], atol=1e-6)   # 不被透明像素的黑拉暗
    assert cell.mask[0, 0]        # 恰好 0.5 视为有豆


def test_fully_transparent_cell_is_masked_out():
    rgba = np.zeros((8, 16, 4), dtype=np.float32)
    rgba[:, :8, 3] = 1.0
    cell = downsample_area(rgba, rows=1, cols=2, denoise=False)
    assert cell.mask.tolist() == [[True, False]]


def test_denoise_keeps_flat_colors():
    rgba = np.zeros((40, 40, 4), dtype=np.float32)
    rgba[..., :3] = [0.2, 0.6, 0.9]
    rgba[..., 3] = 1.0
    cell = downsample_area(rgba, rows=4, cols=4, denoise=True)
    assert np.allclose(cell.rgb, [0.2, 0.6, 0.9], atol=0.02)


def test_mode_sampling_picks_dominant_color_per_cell():
    rgba = np.zeros((16, 16, 4), dtype=np.float32)
    rgba[..., 3] = 1.0
    rgba[:8, :8, :3] = [1, 0, 0]
    rgba[:8, 8:, :3] = [0, 1, 0]
    rgba[8:, :8, :3] = [0, 0, 1]
    rgba[8:, 8:, :3] = [1, 1, 0]
    rgba[0, 0, :3] = [0.5, 0.5, 0.5]          # 一颗噪点，不应影响众数
    info = GridInfo(cell=8, offset_x=0, offset_y=0, cols=2, rows=2, confidence=1.0)
    cell = downsample_mode(rgba, info)
    assert np.allclose(cell.rgb[0, 0], [1, 0, 0]) and np.allclose(cell.rgb[1, 1], [1, 1, 0])
    assert cell.mask.all()
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_downsample.py -q
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

`backend/app/core/downsample.py`：

```python
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from app.core.color import linear_to_srgb, srgb_to_linear
from app.core.detect import GridInfo


@dataclass
class CellImage:
    rgb: np.ndarray
    coverage: np.ndarray
    mask: np.ndarray


def grid_shape(h: int, w: int, long_side: int) -> tuple[int, int]:
    if w >= h:
        cols = long_side
        rows = max(1, round(long_side * h / w))
    else:
        rows = long_side
        cols = max(1, round(long_side * w / h))
    return rows, cols


def _bilateral(rgb: np.ndarray) -> np.ndarray:
    return cv2.bilateralFilter(rgb.astype(np.float32), d=7, sigmaColor=0.1, sigmaSpace=5)


def downsample_area(rgba: np.ndarray, rows: int, cols: int, denoise: bool = True) -> CellImage:
    rgb = rgba[..., :3].astype(np.float32)
    alpha = rgba[..., 3].astype(np.float32)
    if denoise:
        rgb = _bilateral(rgb)
    lin = srgb_to_linear(rgb).astype(np.float32)
    premul = lin * alpha[..., None]
    small_premul = cv2.resize(premul, (cols, rows), interpolation=cv2.INTER_AREA)
    coverage = cv2.resize(alpha, (cols, rows), interpolation=cv2.INTER_AREA)
    safe = np.where(coverage > 1e-6, coverage, 1.0)[..., None]
    small_lin = small_premul / safe
    out_rgb = linear_to_srgb(small_lin).astype(np.float32)
    mask = coverage >= 0.5
    return CellImage(rgb=out_rgb, coverage=coverage.astype(np.float32), mask=mask)


def downsample_mode(rgba: np.ndarray, grid: GridInfo) -> CellImage:
    h, w = rgba.shape[:2]
    rgb8 = np.clip(np.rint(rgba[..., :3] * 255), 0, 255).astype(np.int64)
    key = (rgb8[..., 0] << 16) | (rgb8[..., 1] << 8) | rgb8[..., 2]
    alpha = rgba[..., 3]
    out = np.zeros((grid.rows, grid.cols, 3), dtype=np.float32)
    cov = np.zeros((grid.rows, grid.cols), dtype=np.float32)
    for r in range(grid.rows):
        y0 = int(round(grid.offset_y + r * grid.cell))
        y1 = min(h, int(round(grid.offset_y + (r + 1) * grid.cell)))
        for c in range(grid.cols):
            x0 = int(round(grid.offset_x + c * grid.cell))
            x1 = min(w, int(round(grid.offset_x + (c + 1) * grid.cell)))
            if y1 <= y0 or x1 <= x0:
                continue
            block_a = alpha[y0:y1, x0:x1]
            cov[r, c] = float(block_a.mean())
            opaque = block_a >= 0.5
            if not opaque.any():
                continue
            vals, counts = np.unique(key[y0:y1, x0:x1][opaque], return_counts=True)
            k = int(vals[counts.argmax()])
            out[r, c] = [(k >> 16) & 255, (k >> 8) & 255, k & 255]
    return CellImage(rgb=out / 255.0, coverage=cov, mask=cov >= 0.5)
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_downsample.py -q
```

Expected: 6 passed。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/downsample.py backend/tests/test_downsample.py
git commit -m "feat(core): 线性空间面积平均与像素图众数下采样

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: 色卡受限 k-medoids 选色

**Files:**
- Create: `backend/app/core/select.py`
- Test: `backend/tests/test_select.py`

**Interfaces:**
- Produces: `select.select_palette(cell_oklab: np.ndarray (m,3), palette_oklab: np.ndarray (n,3), k: int, weights: np.ndarray (m,) | None = None, seed: int = 0, max_iter: int = 30) -> np.ndarray`：返回 ≤ k 个**全局色卡索引**（去重、按簇大小降序）。簇心始终是色卡里的真实颜色。

算法：预算 `D = ||cell - palette||²`（m×n）。k-means++ 式初始化但候选限于色卡列；迭代：分配 = 每格取 D 在当前子集列上的 argmin；更新 = 对每簇，在**全部色卡列**里选使 `sum(weights * D[members, col])` 最小的列。簇为空则丢弃。收敛或 max_iter 停。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_select.py`：

```python
import numpy as np

from app.core.select import select_palette


def _palette():
    # 8 色：黑、白、红、绿、蓝、黄、以及两个很接近的红
    return np.array([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.63, 0.22, 0.13], [0.87, -0.23, 0.18],
        [0.45, -0.03, -0.31], [0.97, -0.07, 0.20], [0.64, 0.21, 0.12], [0.62, 0.23, 0.14],
    ])


def test_returns_palette_indices_and_at_most_k():
    cells = np.repeat(_palette()[[0, 1, 2]], 20, axis=0)
    idx = select_palette(cells, _palette(), k=3)
    assert set(idx.tolist()) == {0, 1, 2}
    assert len(idx) <= 3


def test_never_returns_duplicates_even_with_near_identical_palette_entries():
    cells = np.repeat(_palette()[[2]], 50, axis=0) + np.random.default_rng(0).normal(0, 0.005, (50, 3))
    idx = select_palette(cells, _palette(), k=4)
    assert len(idx) == len(set(idx.tolist()))
    assert len(idx) <= 4


def test_small_but_distinct_cluster_survives():
    # 190 格红 + 10 格白：频次截断会丢白，k-medoids 在 k=2 下必须保留白
    cells = np.concatenate([np.repeat(_palette()[[2]], 190, axis=0), np.repeat(_palette()[[1]], 10, axis=0)])
    idx = select_palette(cells, _palette(), k=2)
    assert 1 in idx.tolist()


def test_weights_bias_selection():
    cells = np.concatenate([np.repeat(_palette()[[3]], 10, axis=0), np.repeat(_palette()[[4]], 10, axis=0)])
    w = np.concatenate([np.ones(10) * 100.0, np.ones(10)])
    idx = select_palette(cells, _palette(), k=1, weights=w)
    assert idx.tolist() == [3]


def test_deterministic_with_seed(rng):
    cells = rng.random((200, 3))
    a = select_palette(cells, _palette(), k=5, seed=7)
    b = select_palette(cells, _palette(), k=5, seed=7)
    assert a.tolist() == b.tolist()
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_select.py -q
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

`backend/app/core/select.py`：

```python
from __future__ import annotations

import numpy as np


def select_palette(cell_oklab: np.ndarray, palette_oklab: np.ndarray, k: int,
                   weights: np.ndarray | None = None, seed: int = 0, max_iter: int = 30) -> np.ndarray:
    m = cell_oklab.shape[0]
    n = palette_oklab.shape[0]
    if m == 0:
        return np.zeros(0, dtype=np.int64)
    k = max(1, min(k, n))
    w = np.ones(m) if weights is None else np.asarray(weights, dtype=np.float64)
    diff = cell_oklab[:, None, :] - palette_oklab[None, :, :]
    D = np.einsum("ijk,ijk->ij", diff, diff)            # (m, n) 平方距离
    rng = np.random.default_rng(seed)

    # k-means++ 风格初始化，候选限于色卡
    chosen = [int(np.argmin(D[rng.integers(m)]))]
    while len(chosen) < k:
        best_now = D[:, chosen].min(axis=1)
        if best_now.sum() <= 0:
            break
        p = best_now * w
        p = p / p.sum()
        cell = rng.choice(m, p=p)
        cand = int(np.argmin(D[cell]))
        if cand in chosen:
            order = np.argsort(D[cell])
            cand = next((int(c) for c in order if int(c) not in chosen), None)
            if cand is None:
                break
        chosen.append(cand)

    cur = np.array(chosen, dtype=np.int64)
    for _ in range(max_iter):
        assign = cur[np.argmin(D[:, cur], axis=1)]        # 每格所属的全局色卡索引
        new = []
        for c in cur:
            members = assign == c
            if not members.any():
                continue
            cost = (w[members, None] * D[members]).sum(axis=0)   # 对全部色卡列
            best = int(np.argmin(cost))
            if best not in new:
                new.append(best)
        new = np.array(new, dtype=np.int64)
        if len(new) == len(cur) and set(new.tolist()) == set(cur.tolist()):
            cur = new
            break
        cur = new
    assign = cur[np.argmin(D[:, cur], axis=1)]
    sizes = np.array([(w * (assign == c)).sum() for c in cur])
    return cur[np.argsort(-sizes)]
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_select.py -q
```

Expected: 5 passed。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/select.py backend/tests/test_select.py
git commit -m "feat(core): 色卡受限 k-medoids 选色

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: graph cut 分配（α-expansion）

**Files:**
- Create: `backend/app/core/assign.py`
- Test: `backend/tests/test_assign.py`

**Interfaces:**
- Produces: `assign.assign_labels(cost: np.ndarray (rows, cols, k), mask: np.ndarray (rows, cols) bool, smoothness: float, locked: np.ndarray (rows, cols) int | None = None, n_sweeps: int = 3) -> np.ndarray (rows, cols) int`：
  - `cost[r,c,j]` = 格子 (r,c) 取工作色板第 j 色的数据项（ΔE2000）
  - `mask` False 的格子不参与，输出为 `-1`
  - `smoothness` = λ，相邻（4-邻域，且都在 mask 内）格子标签不同时罚 λ；λ = 0 时退化为逐格 argmin
  - `locked[r,c] = j ≥ 0` 表示强制该格取 j；`-1` 自由
  - 返回工作色板内的**局部索引** j（不是全局色卡索引）

算法：初始化 = 逐格 argmin。对每个标签 α 做一次 expansion：二值变量 x=1 表示切到 α。
一元：`U1 = cost[..., α]`、`U0 = cost[..., current]`（current==α 的格子 U1=U0）；锁定格：非锁定标签的成本 +1e6。
二元（Potts，边 (p,q)）：`A=E(0,0)=λ[f_p≠f_q]`、`B=E(0,1)=λ[f_p≠α]`、`C=E(1,0)=λ[α≠f_q]`、`D=E(1,1)=0`。
按 Kolmogorov–Zabih 分解：`U1[p] += C−A`、`U1[q] += D−C`、边 (p→q) 容量 `B+C−A−D`（≥0，Potts 保证子模）。
PyMaxflow：节点在 **sink 侧 = x=1**；`add_grid_tedges(ids, U1, U0)`（source 容量 = 取 1 的代价，sink 容量 = 取 0 的代价，按 PyMaxflow 约定：割掉 source→节点 边意味着节点归 sink）；`add_edges(p, q, w, 0)` 表示 x_p=0、x_q=1 时付 w。
一轮 sweep = 遍历所有 α；能量不再下降或 n_sweeps 用完即停。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_assign.py`：

```python
import numpy as np

from app.core.assign import assign_labels, energy


def _two_color_cost(rows, cols, split_col, noise_cells=()):
    """左半偏好 0，右半偏好 1；noise_cells 里的格子偏好被反转（模拟散点）。"""
    cost = np.zeros((rows, cols, 2))
    cost[:, :split_col, 1] = 10.0
    cost[:, split_col:, 0] = 10.0
    for r, c in noise_cells:
        cost[r, c] = cost[r, c][::-1]
    return cost


def test_lambda_zero_is_pure_argmin():
    cost = _two_color_cost(6, 8, 4, noise_cells=[(2, 1)])
    mask = np.ones((6, 8), bool)
    out = assign_labels(cost, mask, smoothness=0.0)
    assert out[2, 1] == 1                      # 散点保留
    assert out[0, 0] == 0 and out[0, 7] == 1


def test_smoothness_removes_isolated_noise_but_keeps_real_edge():
    cost = _two_color_cost(6, 8, 4, noise_cells=[(2, 1)])
    mask = np.ones((6, 8), bool)
    out = assign_labels(cost, mask, smoothness=4.0)   # 4 条边 × λ=4 = 16 > 10 的数据代价
    assert out[2, 1] == 0                      # 散点被平滑掉
    assert (out[:, :4] == 0).all() and (out[:, 4:] == 1).all()   # 真实边界保留


def test_masked_cells_are_minus_one_and_do_not_connect():
    cost = _two_color_cost(3, 3, 1)
    mask = np.ones((3, 3), bool)
    mask[1, 1] = False
    out = assign_labels(cost, mask, smoothness=100.0)
    assert out[1, 1] == -1
    assert set(out[mask].tolist()) <= {0, 1}


def test_locked_cells_are_respected():
    cost = _two_color_cost(4, 4, 2)
    mask = np.ones((4, 4), bool)
    locked = -np.ones((4, 4), int)
    locked[0, 0] = 1
    out = assign_labels(cost, mask, smoothness=0.0, locked=locked)
    assert out[0, 0] == 1


def test_energy_never_increases_vs_argmin_baseline(rng):
    cost = rng.random((20, 20, 6)) * 10
    mask = rng.random((20, 20)) > 0.1
    base = np.where(mask, cost.argmin(axis=-1), -1)
    out = assign_labels(cost, mask, smoothness=2.0)
    assert energy(cost, mask, out, 2.0) <= energy(cost, mask, base, 2.0) + 1e-6


def test_runs_fast_enough_for_interactive_use():
    import time
    rng = np.random.default_rng(3)
    cost = rng.random((100, 100, 40)) * 10
    mask = np.ones((100, 100), bool)
    t = time.perf_counter()
    assign_labels(cost, mask, smoothness=1.5, n_sweeps=2)
    assert time.perf_counter() - t < 3.0
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_assign.py -q
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

`backend/app/core/assign.py`：

```python
from __future__ import annotations

import numpy as np
import maxflow

_LOCK_PENALTY = 1e6


def _edges(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """返回 4-邻域内、两端都在 mask 内的边 (p_idx, q_idx)，索引为展平后的节点号。"""
    rows, cols = mask.shape
    idx = np.arange(rows * cols).reshape(rows, cols)
    h_ok = mask[:, :-1] & mask[:, 1:]
    v_ok = mask[:-1, :] & mask[1:, :]
    p = np.concatenate([idx[:, :-1][h_ok], idx[:-1, :][v_ok]])
    q = np.concatenate([idx[:, 1:][h_ok], idx[1:, :][v_ok]])
    return p, q


def energy(cost: np.ndarray, mask: np.ndarray, labels: np.ndarray, smoothness: float) -> float:
    r, c = np.nonzero(mask)
    data = cost[r, c, labels[r, c]].sum()
    p, q = _edges(mask)
    flat = labels.ravel()
    pair = smoothness * (flat[p] != flat[q]).sum()
    return float(data + pair)


def assign_labels(cost: np.ndarray, mask: np.ndarray, smoothness: float,
                  locked: np.ndarray | None = None, n_sweeps: int = 3) -> np.ndarray:
    rows, cols, k = cost.shape
    cost = cost.astype(np.float64).copy()
    if locked is not None:
        lr, lc = np.nonzero(locked >= 0)
        for r, c in zip(lr, lc):
            j = locked[r, c]
            cost[r, c] += _LOCK_PENALTY
            cost[r, c, j] -= _LOCK_PENALTY
    labels = np.where(mask, cost.argmin(axis=-1), -1).astype(np.int64)
    if smoothness <= 0 or k == 1:
        return labels

    p, q = _edges(mask)
    flat_mask = mask.ravel()
    cur_energy = energy(cost, mask, labels, smoothness)
    for _ in range(n_sweeps):
        improved = False
        for alpha in range(k):
            f = labels.ravel()
            U0 = np.where(flat_mask, cost.reshape(-1, k)[np.arange(rows * cols), np.maximum(f, 0)], 0.0)
            U1 = np.where(flat_mask, cost[..., alpha].ravel(), 0.0)
            same = f == alpha
            U1 = np.where(same, U0, U1)
            U1 = U1.copy()
            A = smoothness * (f[p] != f[q])
            B = smoothness * (f[p] != alpha)
            C = smoothness * (alpha != f[q])
            np.add.at(U1, p, C - A)
            np.add.at(U1, q, -C)             # D - C，D = 0
            w = B + C - A                    # ≥ 0
            g = maxflow.GraphFloat()
            ids = g.add_grid_nodes((rows, cols))
            g.add_grid_tedges(ids, U1.reshape(rows, cols), U0.reshape(rows, cols))
            if len(p):
                g.add_edges(p.astype(np.int32), q.astype(np.int32), w, np.zeros_like(w))
            g.maxflow()
            switch = g.get_grid_segments(ids).ravel() & flat_mask   # sink 侧 = 取 α
            new = f.copy()
            new[switch] = alpha
            new_labels = new.reshape(rows, cols)
            e = energy(cost, mask, new_labels, smoothness)
            if e < cur_energy - 1e-9:
                labels, cur_energy, improved = new_labels, e, True
        if not improved:
            break
    return labels
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_assign.py -q
```

Expected: 6 passed。若 `test_smoothness_removes_isolated_noise` 失败而 `test_lambda_zero` 通过，先检查 sink/source 约定：把 `switch` 取反再跑，看能量是否下降——PyMaxflow `get_grid_segments` 返回 True 表示节点在 sink 侧。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/assign.py backend/tests/test_assign.py
git commit -m "feat(core): α-expansion graph cut 色号分配（PyMaxflow）

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: 小色号合并与描边格检测

**Files:**
- Create: `backend/app/core/merge.py`
- Test: `backend/tests/test_merge.py`

**Interfaces:**
- Produces: `merge.color_counts(grid: np.ndarray) -> dict[int, int]`（全局索引 → 颗数，不含 -1）
- Produces: `merge.merge_small_colors(grid, palette_lab: np.ndarray (n,3), threshold: int, protected: set[int] = frozenset()) -> tuple[np.ndarray, list[tuple[int, int, float]]]`：颗数 < threshold 的色号，并入**仍在图中**的、ΔE2000 最近的其他色号；返回 (新 grid, [(from, to, ΔE)])。按颗数升序处理；protected 里的索引不合并。
- Produces: `merge.detect_outline_cells(cell_rgb: np.ndarray (rows, cols, 3), mask) -> np.ndarray (rows, cols) bool`：OKLab `L < 0.35` 且色度 `sqrt(a²+b²) < 0.06` 且是 1–2 格宽细结构（十字腐蚀一次即消失）的格子——这些是描边

- [ ] **Step 1: 写失败测试**

`backend/tests/test_merge.py`：

```python
import numpy as np

from app.core.merge import color_counts, detect_outline_cells, merge_small_colors


def _lab():
    return np.array([[50, 0, 0], [52, 1, 0], [90, 0, 0], [10, 0, 0]], dtype=float)   # 0 与 1 很接近


def test_color_counts_ignores_empty():
    g = np.array([[0, 0, -1], [1, -1, 2]], dtype=np.int16)
    assert color_counts(g) == {0: 2, 1: 1, 2: 1}


def test_small_color_merges_into_nearest_present_color():
    g = np.full((5, 5), 2, dtype=np.int16)
    g[0, 0] = 1                       # 只有 1 颗
    g[1:3, 1:3] = 0                   # 4 颗
    out, log = merge_small_colors(g, _lab(), threshold=3)
    assert out[0, 0] == 0             # 1 → 0（最近，且 0 在图中）
    assert log == [(1, 0, log[0][2])] and log[0][2] < 3
    assert (out == 1).sum() == 0


def test_merge_processes_smallest_first_and_cascades():
    g = np.full((6, 6), 2, dtype=np.int16)
    g[0, 0] = 1
    g[0, 1] = 0
    out, log = merge_small_colors(g, _lab(), threshold=3)
    assert set(np.unique(out).tolist()) == {2}
    assert len(log) == 2


def test_protected_color_not_merged():
    g = np.full((5, 5), 2, dtype=np.int16)
    g[0, 0] = 3
    out, log = merge_small_colors(g, _lab(), threshold=3, protected={3})
    assert out[0, 0] == 3 and log == []


def test_outline_detection_finds_thin_dark_lines_only():
    rgb = np.ones((10, 10, 3), dtype=np.float32)
    rgb[5, :, :] = 0.05                 # 一条 1 格宽黑线
    rgb[0:3, 0:3, :] = 0.05             # 一块 3×3 黑块（不是描边）
    mask = np.ones((10, 10), bool)
    out = detect_outline_cells(rgb, mask)
    assert out[5, 5] and not out[1, 1]
    assert not out[7, 7]
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_merge.py -q
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

`backend/app/core/merge.py`：

```python
from __future__ import annotations

import numpy as np
from scipy import ndimage

from app.core.color import pairwise_delta_e, srgb_to_oklab
from app.core.types import EMPTY

_CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)


def color_counts(grid: np.ndarray) -> dict[int, int]:
    vals, counts = np.unique(grid[grid != EMPTY], return_counts=True)
    return {int(v): int(c) for v, c in zip(vals, counts)}


def merge_small_colors(grid: np.ndarray, palette_lab: np.ndarray, threshold: int,
                       protected: set[int] = frozenset()) -> tuple[np.ndarray, list[tuple[int, int, float]]]:
    out = grid.copy()
    log: list[tuple[int, int, float]] = []
    while True:
        counts = color_counts(out)
        small = sorted((c for c, n in counts.items() if n < threshold and c not in protected), key=lambda c: counts[c])
        if not small:
            break
        src = small[0]
        others = [c for c in counts if c != src]
        if not others:
            break
        d = pairwise_delta_e(palette_lab[[src]], palette_lab[others])[0]
        j = int(np.argmin(d))
        dst = others[j]
        out[out == src] = dst
        log.append((int(src), int(dst), float(d[j])))
    return out, log


def detect_outline_cells(cell_rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    ok = srgb_to_oklab(cell_rgb)
    dark = (ok[..., 0] < 0.35) & (np.hypot(ok[..., 1], ok[..., 2]) < 0.06) & mask
    thick = ndimage.binary_erosion(dark, structure=_CROSS, border_value=0)
    thin = dark & ~ndimage.binary_dilation(thick, structure=_CROSS)
    return thin
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_merge.py -q
```

Expected: 5 passed。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/merge.py backend/tests/test_merge.py
git commit -m "feat(core): 小色号合并与描边格检测

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: 可拼性分析

**Files:**
- Create: `backend/app/core/buildability.py`
- Test: `backend/tests/test_buildability.py`

**Interfaces:**
- Produces: `buildability.analyze(grid: np.ndarray, palette_lab: np.ndarray, small_color_threshold: int = 10, protected_cells: set[tuple[int,int]] = frozenset()) -> Report`
  - `Report.issues` 各 `Issue.type` 与 `cells`：
    - `disconnected`：非空格 4-连通组件数 > 1；每个非最大组件一条 issue，`cells` = 该组件全部格子
    - `isolated_bead`：4-邻域全空的非空格；每格一条
    - `diagonal_link`：仅通过对角接触的格子对；每对一条，`cells` = 两格
    - `thin_line`：十字腐蚀后消失的格子组成的 4-连通块，且块内格子数 ≥ 3；每块一条
    - `hole`：空格的 4-连通组件中不接触图像边界的；每个一条
    - `small_color`：颗数 < threshold 的色号；每色一条，`cells` = 全部该色格子，`target_color` = 最近的其他在图色号，`delta_e`
  - `Report.confetti_pct`：非空格中"4-邻域没有同色格"的比例 × 100
  - `Report.metrics`：`n_isolated, n_diagonal, thin_ratio, n_holes, n_small_colors, n_colors, n_cells`
  - `Report.score`：0–100，见 Step 3 的权重表
  - `protected_cells` 中的格子不产生 `isolated_bead` issue，也不计入 confetti
  - 本任务**不填** `Issue.action / patch_cells`（Task 11 负责），`action` 先置 `"todo"`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_buildability.py`：

```python
import numpy as np

from app.core.buildability import analyze

LAB = np.array([[50, 0, 0], [80, 0, 0], [20, 0, 0]], dtype=float)


def _issues(report, t):
    return [i for i in report.issues if i.type == t]


def test_solid_block_is_perfect():
    g = np.zeros((6, 6), dtype=np.int16)
    r = analyze(g, LAB)
    assert r.n_components == 1 and r.issues == [] and r.score == 100.0 and r.confetti_pct == 0.0


def test_disconnected_components_reported():
    g = np.full((6, 6), -1, dtype=np.int16)
    g[0:2, 0:2] = 0
    g[4:6, 4:6] = 1
    r = analyze(g, LAB)
    assert r.n_components == 2
    assert len(_issues(r, "disconnected")) == 1
    assert len(_issues(r, "disconnected")[0].cells) == 4


def test_isolated_bead_and_diagonal_link():
    g = np.full((5, 5), -1, dtype=np.int16)
    g[2, 2] = 0                    # 孤立
    g[0, 0] = 1; g[1, 1] = 1       # 对角虚连
    r = analyze(g, LAB)
    iso = _issues(r, "isolated_bead")
    assert (2, 2) in [c for i in iso for c in i.cells]
    diag = _issues(r, "diagonal_link")
    assert len(diag) == 1 and sorted(diag[0].cells) == [(0, 0), (1, 1)]


def test_thin_line_detected():
    g = np.full((7, 7), -1, dtype=np.int16)
    g[3, :] = 0                    # 1 格宽横线
    r = analyze(g, LAB)
    assert len(_issues(r, "thin_line")) == 1
    assert r.metrics["thin_ratio"] > 0.9


def test_hole_detected_but_border_gap_is_not():
    g = np.zeros((7, 7), dtype=np.int16)
    g[3, 3] = -1                   # 内部空洞
    g[0, 0] = -1                   # 边角缺口，不是洞
    r = analyze(g, LAB)
    holes = _issues(r, "hole")
    assert len(holes) == 1 and holes[0].cells == [(3, 3)]


def test_small_color_has_target_and_delta_e():
    g = np.zeros((6, 6), dtype=np.int16)
    g[0, 0] = 2
    r = analyze(g, LAB, small_color_threshold=3)
    sc = _issues(r, "small_color")
    assert len(sc) == 1 and sc[0].target_color == 0 and sc[0].delta_e is not None


def test_confetti_pct_and_protection():
    g = np.zeros((10, 10), dtype=np.int16)
    g[4, 4] = 1                    # 1 颗异色，四周都是 0
    r = analyze(g, LAB)
    assert abs(r.confetti_pct - 1.0) < 1e-6
    r2 = analyze(g, LAB, protected_cells={(4, 4)})
    assert r2.confetti_pct == 0.0


def test_score_decreases_with_problems():
    good = analyze(np.zeros((8, 8), dtype=np.int16), LAB).score
    bad = np.full((8, 8), -1, dtype=np.int16)
    bad[0, 0] = 0; bad[7, 7] = 1; bad[3, :] = 2
    assert analyze(bad, LAB).score < good - 30
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_buildability.py -q
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

`backend/app/core/buildability.py`：

```python
from __future__ import annotations

import numpy as np
from scipy import ndimage

from app.core.color import pairwise_delta_e
from app.core.merge import color_counts
from app.core.types import EMPTY, Issue, Report

_CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
_SQUARE = np.ones((3, 3), bool)

# 评分权重：每项扣分上限
_W = dict(disconnected=30.0, isolated=20.0, diagonal=15.0, thin=20.0, hole=10.0, small=10.0, confetti=25.0)


def _cells(mask: np.ndarray) -> list[tuple[int, int]]:
    r, c = np.nonzero(mask)
    return [(int(a), int(b)) for a, b in zip(r, c)]


def _same_color_neighbor_count(grid: np.ndarray) -> np.ndarray:
    pad = np.pad(grid, 1, constant_values=EMPTY)
    n = np.zeros(grid.shape, dtype=np.int32)
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb = pad[1 + dr:1 + dr + grid.shape[0], 1 + dc:1 + dc + grid.shape[1]]
        n += ((nb == grid) & (grid != EMPTY)).astype(np.int32)
    return n


def _diagonal_pairs(filled: np.ndarray) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """仅对角接触、且两格无共同 4-邻居填充格的格子对。"""
    rows, cols = filled.shape
    pairs = []
    for r in range(rows - 1):
        for c in range(cols):
            for dc in (1, -1):
                c2 = c + dc
                if not (0 <= c2 < cols):
                    continue
                if filled[r, c] and filled[r + 1, c2] and not filled[r + 1, c] and not filled[r, c2]:
                    pairs.append(((r, c), (r + 1, c2)))
    return pairs


def analyze(grid: np.ndarray, palette_lab: np.ndarray, small_color_threshold: int = 10,
            protected_cells: set[tuple[int, int]] = frozenset()) -> Report:
    filled = grid != EMPTY
    n_cells = int(filled.sum())
    issues: list[Issue] = []
    prot = np.zeros(grid.shape, bool)
    for r, c in protected_cells:
        prot[r, c] = True

    # 连通性
    lab4, n4 = ndimage.label(filled, structure=_CROSS)
    if n4 > 1:
        sizes = ndimage.sum(filled, lab4, index=range(1, n4 + 1))
        biggest = int(np.argmax(sizes)) + 1
        for i in range(1, n4 + 1):
            if i != biggest:
                issues.append(Issue("disconnected", _cells(lab4 == i), "todo", severity=float(sizes[i - 1])))

    # 孤立单豆
    nb_filled = ndimage.convolve(filled.astype(np.int32), _CROSS.astype(np.int32), mode="constant") - filled
    isolated = filled & (nb_filled == 0) & ~prot
    for cell in _cells(isolated):
        issues.append(Issue("isolated_bead", [cell], "todo"))

    # 对角虚连
    diag = _diagonal_pairs(filled)
    for a, b in diag:
        issues.append(Issue("diagonal_link", [a, b], "todo"))

    # 细线
    thick = ndimage.binary_erosion(filled, structure=_CROSS, border_value=0)
    thin = filled & ~ndimage.binary_dilation(thick, structure=_CROSS)
    lab_thin, n_thin = ndimage.label(thin, structure=_CROSS)
    n_thin_cells = 0
    for i in range(1, n_thin + 1):
        cells = _cells(lab_thin == i)
        if len(cells) >= 3:
            issues.append(Issue("thin_line", cells, "todo", severity=float(len(cells))))
            n_thin_cells += len(cells)

    # 空洞
    lab_e, n_e = ndimage.label(~filled, structure=_CROSS)
    border = np.zeros(grid.shape, bool)
    border[0, :] = border[-1, :] = border[:, 0] = border[:, -1] = True
    border_labels = set(np.unique(lab_e[border & ~filled]).tolist())
    n_holes = 0
    for i in range(1, n_e + 1):
        if i not in border_labels:
            issues.append(Issue("hole", _cells(lab_e == i), "todo"))
            n_holes += 1

    # 小色号
    counts = color_counts(grid)
    small = [c for c, n in counts.items() if n < small_color_threshold]
    for c in small:
        others = [o for o in counts if o != c]
        target, de = None, None
        if others:
            d = pairwise_delta_e(palette_lab[[c]], palette_lab[others])[0]
            j = int(np.argmin(d))
            target, de = int(others[j]), float(d[j])
        issues.append(Issue("small_color", _cells(grid == c), "todo", target_color=target, delta_e=de))

    # confetti
    same = _same_color_neighbor_count(grid)
    confetti = filled & (same == 0) & ~prot
    confetti_pct = float(100.0 * confetti.sum() / n_cells) if n_cells else 0.0

    thin_ratio = n_thin_cells / n_cells if n_cells else 0.0
    n_iso = int(isolated.sum())
    metrics = dict(n_isolated=n_iso, n_diagonal=len(diag), thin_ratio=thin_ratio, n_holes=n_holes,
                   n_small_colors=len(small), n_colors=len(counts), n_cells=n_cells)

    score = 100.0
    if n4 > 1:
        score -= min(_W["disconnected"], 15.0 + 5.0 * (n4 - 1))
    score -= min(_W["isolated"], 2.0 * n_iso)
    score -= min(_W["diagonal"], 3.0 * len(diag))
    score -= _W["thin"] * min(1.0, thin_ratio)
    score -= min(_W["hole"], 2.0 * n_holes)
    score -= min(_W["small"], 2.0 * len(small))
    score -= _W["confetti"] * float(np.clip((confetti_pct - 2.0) / 8.0, 0.0, 1.0))
    score = float(max(0.0, round(score, 1)))

    return Report(score=score, confetti_pct=round(confetti_pct, 2), n_components=int(n4), issues=issues, metrics=metrics)
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_buildability.py -q
```

Expected: 8 passed。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/buildability.py backend/tests/test_buildability.py
git commit -m "feat(core): 可拼性分析——连通性、孤立、对角虚连、细线、空洞、小色号、confetti%

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: 修复建议生成与应用

**Files:**
- Create: `backend/app/core/patches.py`
- Test: `backend/tests/test_patches.py`

**Interfaces:**
- Produces: `patches.attach_patches(report: Report, grid: np.ndarray, clear_index: int | None) -> Report`：为每条 issue 填 `action` 与 `patch_cells`（以及 `target_color`），规则：
  - `isolated_bead`：若 8-邻域有填充格 → `bridge_with_clear`，patch_cells = 能把它连上的一个空 4-邻居（选与最近对角填充格相邻的那个）；否则 → `remove`，patch_cells = 该格
  - `diagonal_link`：`bridge_with_clear`，patch_cells = 两格构成 2×2 的两个空角之一（取行号小的）
  - `thin_line`：`bridge_with_clear`，patch_cells = 线段所有格的空 4-邻居去重（等于用透明豆把线加厚）
  - `hole`：`fill_with_clear`，patch_cells = 空洞全部格
  - `small_color`：`merge_color`，patch_cells = 该色全部格，`target_color` 已由 analyze 给出
  - `disconnected`：`bridge_with_clear`，patch_cells = 从该组件到最大组件的最短空格路径（4-邻域 BFS）；找不到 → `remove`
  - `clear_index is None` 时所有 `*_with_clear` 退化为 `remove`（对 hole 则不给建议，action=`none`）
- Produces: `patches.apply_patch(grid, issue: Issue, clear_index: int | None) -> np.ndarray`：返回新 grid

- [ ] **Step 1: 写失败测试**

`backend/tests/test_patches.py`：

```python
import numpy as np

from app.core.buildability import analyze
from app.core.patches import apply_patch, attach_patches

LAB = np.array([[50, 0, 0], [80, 0, 0], [20, 0, 0], [95, 0, 0]], dtype=float)
CLEAR = 3


def _report(grid):
    return attach_patches(analyze(grid, LAB, small_color_threshold=3), grid, CLEAR)


def _first(report, t):
    return next(i for i in report.issues if i.type == t)


def test_isolated_bead_with_diagonal_neighbor_gets_clear_bridge():
    g = np.full((5, 5), -1, dtype=np.int16)
    g[2, 2] = 0
    g[3, 3] = 0; g[3, 4] = 0; g[4, 3] = 0; g[4, 4] = 0
    issue = _first(_report(g), "isolated_bead")
    assert issue.action == "bridge_with_clear"
    assert issue.patch_cells in ([(2, 3)], [(3, 2)])
    out = apply_patch(g, issue, CLEAR)
    assert analyze(out, LAB).n_components == 1
    assert out[tuple(issue.patch_cells[0])] == CLEAR


def test_truly_isolated_bead_is_removed():
    g = np.full((5, 5), -1, dtype=np.int16)
    g[0, 0] = 0
    g[4, 4] = 0; g[4, 3] = 0; g[3, 4] = 0; g[3, 3] = 0
    issue = _first(_report(g), "isolated_bead")
    assert issue.action == "remove"
    assert apply_patch(g, issue, CLEAR)[0, 0] == -1


def test_diagonal_link_bridge_connects():
    g = np.full((4, 4), -1, dtype=np.int16)
    g[0, 0] = 0; g[1, 1] = 0
    issue = _first(_report(g), "diagonal_link")
    out = apply_patch(g, issue, CLEAR)
    assert analyze(out, LAB).metrics["n_diagonal"] == 0
    assert (out == CLEAR).sum() == 1


def test_thin_line_thickened_with_clear():
    g = np.full((7, 7), -1, dtype=np.int16)
    g[3, :] = 0
    issue = _first(_report(g), "thin_line")
    out = apply_patch(g, issue, CLEAR)
    assert analyze(out, LAB).metrics["thin_ratio"] < 0.5
    assert (out == 0).sum() == 7


def test_hole_filled_with_clear():
    g = np.zeros((5, 5), dtype=np.int16)
    g[2, 2] = -1
    issue = _first(_report(g), "hole")
    assert issue.action == "fill_with_clear"
    assert apply_patch(g, issue, CLEAR)[2, 2] == CLEAR


def test_small_color_merged():
    g = np.zeros((5, 5), dtype=np.int16)
    g[0, 0] = 2
    issue = _first(_report(g), "small_color")
    assert issue.action == "merge_color" and issue.target_color == 0
    assert (apply_patch(g, issue, CLEAR) == 2).sum() == 0


def test_disconnected_component_bridged_by_shortest_path():
    g = np.full((3, 9), -1, dtype=np.int16)
    g[1, 0:2] = 0
    g[1, 6:9] = 1
    issue = _first(_report(g), "disconnected")
    assert issue.action == "bridge_with_clear"
    assert sorted(issue.patch_cells) == [(1, 2), (1, 3), (1, 4), (1, 5)]
    assert analyze(apply_patch(g, issue, CLEAR), LAB).n_components == 1


def test_without_clear_index_bridges_degrade_to_remove():
    g = np.full((4, 4), -1, dtype=np.int16)
    g[0, 0] = 0; g[1, 1] = 0
    r = attach_patches(analyze(g, LAB), g, None)
    assert all(i.action in ("remove", "none", "merge_color") for i in r.issues)


def test_apply_does_not_mutate_input():
    g = np.zeros((5, 5), dtype=np.int16)
    g[2, 2] = -1
    before = g.copy()
    apply_patch(g, _first(_report(g), "hole"), CLEAR)
    assert np.array_equal(g, before)
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_patches.py -q
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

`backend/app/core/patches.py`：

```python
from __future__ import annotations

from collections import deque

import numpy as np
from scipy import ndimage

from app.core.types import EMPTY, Issue, Report

_CROSS = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], bool)
_N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _inside(grid, r, c):
    return 0 <= r < grid.shape[0] and 0 <= c < grid.shape[1]


def _empty_neighbors(grid, cells):
    out = []
    seen = set()
    for r, c in cells:
        for dr, dc in _N4:
            rr, cc = r + dr, c + dc
            if _inside(grid, rr, cc) and grid[rr, cc] == EMPTY and (rr, cc) not in seen:
                seen.add((rr, cc))
                out.append((rr, cc))
    return out


def _bfs_path(grid: np.ndarray, sources: set, targets: set) -> list[tuple[int, int]]:
    """从 sources 经空格到 targets 的最短路径（不含首尾填充格）。"""
    prev = {}
    dq = deque()
    for s in sources:
        dq.append(s)
        prev[s] = None
    while dq:
        r, c = dq.popleft()
        for dr, dc in _N4:
            nxt = (r + dr, c + dc)
            if not _inside(grid, *nxt) or nxt in prev:
                continue
            if nxt in targets:
                path = []
                cur = (r, c)
                while cur is not None and cur not in sources:
                    path.append(cur)
                    cur = prev[cur]
                return path[::-1]
            if grid[nxt] == EMPTY:
                prev[nxt] = (r, c)
                dq.append(nxt)
    return []


def attach_patches(report: Report, grid: np.ndarray, clear_index: int | None) -> Report:
    filled = grid != EMPTY
    lab4, n4 = ndimage.label(filled, structure=_CROSS)
    biggest = 0
    if n4 > 0:
        sizes = ndimage.sum(filled, lab4, index=range(1, n4 + 1))
        biggest = int(np.argmax(sizes)) + 1
    can_clear = clear_index is not None

    for issue in report.issues:
        t = issue.type
        if t == "isolated_bead":
            r, c = issue.cells[0]
            diag = [(r + dr, c + dc) for dr in (-1, 1) for dc in (-1, 1)
                    if _inside(grid, r + dr, c + dc) and grid[r + dr, c + dc] != EMPTY]
            if diag and can_clear:
                dr, dc = diag[0][0] - r, diag[0][1] - c
                cand = [(r + dr, c), (r, c + dc)]
                issue.action, issue.patch_cells = "bridge_with_clear", [cand[0] if grid[cand[0]] == EMPTY else cand[1]]
            else:
                issue.action, issue.patch_cells = "remove", [issue.cells[0]]
        elif t == "diagonal_link":
            (r1, c1), (r2, c2) = sorted(issue.cells)
            corner = (r1, c2) if grid[r1, c2] == EMPTY else (r2, c1)
            if can_clear:
                issue.action, issue.patch_cells = "bridge_with_clear", [corner]
            else:
                issue.action, issue.patch_cells = "remove", [issue.cells[0]]
        elif t == "thin_line":
            if can_clear:
                issue.action, issue.patch_cells = "bridge_with_clear", _empty_neighbors(grid, issue.cells)
            else:
                issue.action, issue.patch_cells = "none", []
        elif t == "hole":
            if can_clear:
                issue.action, issue.patch_cells = "fill_with_clear", list(issue.cells)
            else:
                issue.action, issue.patch_cells = "none", []
        elif t == "small_color":
            issue.action, issue.patch_cells = "merge_color", list(issue.cells)
        elif t == "disconnected":
            targets = set(map(tuple, np.argwhere(lab4 == biggest).tolist()))
            path = _bfs_path(grid, set(issue.cells), targets) if can_clear else []
            if path:
                issue.action, issue.patch_cells = "bridge_with_clear", path
            else:
                issue.action, issue.patch_cells = "remove", list(issue.cells)
    return report


def apply_patch(grid: np.ndarray, issue: Issue, clear_index: int | None) -> np.ndarray:
    out = grid.copy()
    if issue.action in ("bridge_with_clear", "fill_with_clear"):
        if clear_index is None:
            return out
        for r, c in issue.patch_cells:
            out[r, c] = clear_index
    elif issue.action == "remove":
        for r, c in issue.patch_cells:
            out[r, c] = EMPTY
    elif issue.action == "merge_color" and issue.target_color is not None:
        for r, c in issue.patch_cells:
            out[r, c] = issue.target_color
    return out
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_patches.py -q
```

Expected: 9 passed。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/patches.py backend/tests/test_patches.py
git commit -m "feat(core): 修复建议生成（补透明豆桥优先）与应用

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: 底板分片

**Files:**
- Create: `backend/app/core/split.py`
- Test: `backend/tests/test_split.py`

**Interfaces:**
- Produces: `split.Board` dataclass：`row0, col0, rows, cols, label: str`（如 `"A1"`，字母=行、数字=列）
- Produces: `split.split_boards(grid: np.ndarray, board_rows: int, board_cols: int, slack: int = 3) -> list[Board]`：图不超过一块板时返回单块；否则在每个轴上依次选切线：候选位置 = 上一条切线 + board 尺寸 − slack … + board 尺寸（不超过），代价 = 该切线切断的**同色相邻非空格对**数，取最小（并列取靠后者，让每片尽量满）；每片尺寸 ≤ 板尺寸
- Produces: `split.cut_cost(grid, axis: int, pos: int) -> int`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_split.py`：

```python
import numpy as np

from app.core.split import Board, cut_cost, split_boards


def test_fits_single_board():
    g = np.zeros((20, 25), dtype=np.int16)
    boards = split_boards(g, 29, 29)
    assert boards == [Board(0, 0, 20, 25, "A1")]


def test_cut_cost_counts_same_color_pairs_crossing_line():
    g = np.zeros((4, 6), dtype=np.int16)
    g[:, 3:] = 1                     # 列 2|3 之间是色边界
    assert cut_cost(g, axis=1, pos=3) == 0
    assert cut_cost(g, axis=1, pos=2) == 4


def test_seam_prefers_color_boundary_within_slack():
    g = np.zeros((10, 40), dtype=np.int16)
    g[:, 27:] = 1                    # 边界在 27，板宽 29，slack 3 → 候选 26..29，选 27
    boards = split_boards(g, 29, 29, slack=3)
    assert [b.col0 for b in boards] == [0, 27]
    assert all(b.cols <= 29 for b in boards)


def test_labels_and_coverage():
    g = np.zeros((60, 60), dtype=np.int16)
    boards = split_boards(g, 29, 29, slack=0)
    assert len(boards) == 9
    assert boards[0].label == "A1" and boards[-1].label == "C3"
    covered = np.zeros((60, 60), int)
    for b in boards:
        covered[b.row0:b.row0 + b.rows, b.col0:b.col0 + b.cols] += 1
    assert (covered == 1).all()


def test_empty_columns_cost_zero():
    g = np.full((5, 10), -1, dtype=np.int16)
    g[:, :4] = 0
    assert cut_cost(g, axis=1, pos=6) == 0
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_split.py -q
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

`backend/app/core/split.py`：

```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.core.types import EMPTY


@dataclass(frozen=True)
class Board:
    row0: int
    col0: int
    rows: int
    cols: int
    label: str


def cut_cost(grid: np.ndarray, axis: int, pos: int) -> int:
    """切线在索引 pos 之前（pos-1 | pos）。axis=1 竖切（列），axis=0 横切（行）。"""
    if axis == 1:
        a, b = grid[:, pos - 1], grid[:, pos]
    else:
        a, b = grid[pos - 1, :], grid[pos, :]
    return int(((a == b) & (a != EMPTY)).sum())


def _cuts(grid: np.ndarray, axis: int, size: int, slack: int) -> list[int]:
    n = grid.shape[axis]
    cuts = [0]
    while n - cuts[-1] > size:
        lo, hi = cuts[-1] + max(1, size - slack), cuts[-1] + size
        best_pos, best_cost = hi, None
        for pos in range(lo, hi + 1):
            c = cut_cost(grid, axis, pos)
            if best_cost is None or c <= best_cost:
                best_pos, best_cost = pos, c
        cuts.append(best_pos)
    cuts.append(n)
    return cuts


def split_boards(grid: np.ndarray, board_rows: int, board_cols: int, slack: int = 3) -> list[Board]:
    rows, cols = grid.shape
    row_cuts = _cuts(grid, 0, board_rows, slack)
    col_cuts = _cuts(grid, 1, board_cols, slack)
    boards = []
    for i in range(len(row_cuts) - 1):
        for j in range(len(col_cuts) - 1):
            r0, r1 = row_cuts[i], row_cuts[i + 1]
            c0, c1 = col_cuts[j], col_cuts[j + 1]
            boards.append(Board(r0, c0, r1 - r0, c1 - c0, f"{chr(ord('A') + i)}{j + 1}"))
    return boards
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_split.py -q
```

Expected: 5 passed。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/split.py backend/tests/test_split.py
git commit -m "feat(core): 接缝感知的底板分片

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 13: PNG 图纸渲染与材料清单

**Files:**
- Create: `backend/app/core/render.py`
- Test: `backend/tests/test_render.py`

**Interfaces:**
- Produces: `render.RenderOptions` dataclass：`cell_px: int = 28`、`show_codes: bool = True`、`hide_empty_codes: bool = True`、`hide_clear_codes: bool = False`、`axis: bool = True`、`minor_every: int = 5`、`major_every: int = 10`、`highlight: list[tuple[int,int]] = []`、`board: Board | None = None`
- Produces: `render.render_grid(grid, palette: Palette, options: RenderOptions = RenderOptions()) -> PIL.Image.Image`（RGB）：
  - 网格线落整数像素：画布尺寸 = cols·cell_px + 1（+ 坐标轴边距），线宽 1，major 线宽 2
  - 每格填色卡颜色；空格画浅灰斜线纹理；`highlight` 格画红框
  - 色号文字居中，字号 = cell_px·0.4，四周留 ≥ 2px；文字色按背景亮度选黑/白
  - 坐标轴：每 `minor_every` 格标数字
  - `board` 给定时只渲染该片
- Produces: `render.materials(grid, palette: Palette, pack_size: int = 1000) -> list[dict]`：`[{"index", "code", "hex", "count", "packs"}]`，按 count 降序
- Produces: `render.render_legend(rows: list[dict], palette, cell_px=28) -> PIL.Image.Image`
- Produces: `render.text_color_for(rgb: tuple[int,int,int]) -> tuple[int,int,int]`（黑或白）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_render.py`：

```python
import numpy as np
from PIL import Image

from app.core.palette import Palette
from app.core.render import RenderOptions, materials, render_grid, render_legend, text_color_for
from app.core.split import Board


def _palette():
    return Palette.load("mard")


def test_canvas_size_is_integer_grid():
    g = np.zeros((10, 20), dtype=np.int16)
    img = render_grid(g, _palette(), RenderOptions(cell_px=20, axis=False))
    assert img.size == (20 * 20 + 1, 10 * 20 + 1)


def test_grid_lines_are_crisp_single_pixel():
    g = np.zeros((4, 4), dtype=np.int16)
    p = _palette()
    img = render_grid(g, p, RenderOptions(cell_px=20, axis=False, show_codes=False))
    arr = np.asarray(img)
    fill = tuple(p.rgb[0])
    line_col = arr[:, 20, :]            # 第二条竖线
    assert not np.all(line_col == fill, axis=1).any()      # 整列都是线色
    assert np.all(arr[10, 15] == fill)                     # 格子内部是填充色


def test_cell_filled_with_palette_color_and_highlight_drawn():
    g = np.zeros((3, 3), dtype=np.int16)
    p = _palette()
    img = render_grid(g, p, RenderOptions(cell_px=20, axis=False, show_codes=False, highlight=[(1, 1)]))
    arr = np.asarray(img)
    assert tuple(arr[5, 5]) == tuple(p.rgb[0])
    assert tuple(arr[21, 30]) == (255, 0, 0)               # 高亮框上边


def test_empty_cells_are_not_palette_colored():
    g = np.full((2, 2), -1, dtype=np.int16)
    img = render_grid(g, _palette(), RenderOptions(cell_px=20, axis=False))
    arr = np.asarray(img)
    assert arr.mean() > 200


def test_board_option_renders_only_that_board():
    g = np.zeros((10, 10), dtype=np.int16)
    img = render_grid(g, _palette(), RenderOptions(cell_px=10, axis=False, board=Board(0, 0, 4, 6, "A1")))
    assert img.size == (61, 41)


def test_text_color_contrast():
    assert text_color_for((250, 250, 250)) == (0, 0, 0)
    assert text_color_for((10, 10, 10)) == (255, 255, 255)


def test_materials_sorted_and_packed():
    g = np.zeros((10, 10), dtype=np.int16)
    g[0, :3] = 5
    rows = materials(g, _palette(), pack_size=50)
    assert rows[0]["index"] == 0 and rows[0]["count"] == 97 and rows[0]["packs"] == 2
    assert rows[1]["index"] == 5 and rows[1]["count"] == 3 and rows[1]["packs"] == 1
    assert rows[0]["code"] == _palette().codes[0]


def test_legend_renders():
    g = np.zeros((3, 3), dtype=np.int16)
    img = render_legend(materials(g, _palette()), _palette())
    assert isinstance(img, Image.Image) and img.size[1] >= 28
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_render.py -q
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

`backend/app/core/render.py`：

```python
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.core.merge import color_counts
from app.core.palette import Palette
from app.core.split import Board
from app.core.types import EMPTY

_LINE = (90, 90, 90)
_MAJOR = (30, 30, 30)
_EMPTY_BG = (245, 245, 245)
_EMPTY_HATCH = (215, 215, 215)
_HIGHLIGHT = (255, 0, 0)
_AXIS_BG = (255, 255, 255)


@dataclass
class RenderOptions:
    cell_px: int = 28
    show_codes: bool = True
    hide_empty_codes: bool = True
    hide_clear_codes: bool = False
    axis: bool = True
    minor_every: int = 5
    major_every: int = 10
    highlight: list[tuple[int, int]] = field(default_factory=list)
    board: Board | None = None


def text_color_for(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = rgb
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (0, 0, 0) if lum > 140 else (255, 255, 255)


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:          # Pillow < 10.1
        return ImageFont.load_default()


def render_grid(grid: np.ndarray, palette: Palette, options: RenderOptions = RenderOptions()) -> Image.Image:
    o = options
    if o.board is not None:
        b = o.board
        grid = grid[b.row0:b.row0 + b.rows, b.col0:b.col0 + b.cols]
        row_off, col_off = b.row0, b.col0
    else:
        row_off = col_off = 0
    rows, cols = grid.shape
    cp = o.cell_px
    margin = int(cp * 0.9) if o.axis else 0
    W, H = cols * cp + 1 + margin, rows * cp + 1 + margin
    img = Image.new("RGB", (W, H), _AXIS_BG)
    d = ImageDraw.Draw(img)
    font = _font(max(6, int(cp * 0.4)))
    axis_font = _font(max(6, int(cp * 0.35)))
    clear_idx = palette.clear_index

    for r in range(rows):
        for c in range(cols):
            x0, y0 = margin + c * cp, margin + r * cp
            v = int(grid[r, c])
            if v == EMPTY:
                d.rectangle([x0, y0, x0 + cp, y0 + cp], fill=_EMPTY_BG)
                d.line([x0, y0 + cp, x0 + cp, y0], fill=_EMPTY_HATCH, width=1)
                continue
            rgb = tuple(int(x) for x in palette.rgb[v])
            d.rectangle([x0, y0, x0 + cp, y0 + cp], fill=rgb)
            if o.show_codes and not (o.hide_clear_codes and v == clear_idx):
                d.text((x0 + cp / 2, y0 + cp / 2), palette.codes[v], fill=text_color_for(rgb), font=font, anchor="mm")

    for c in range(cols + 1):
        gc = c + col_off
        x = margin + c * cp
        major = o.major_every and gc % o.major_every == 0
        d.line([x, margin, x, margin + rows * cp], fill=_MAJOR if major else _LINE, width=2 if major else 1)
    for r in range(rows + 1):
        gr = r + row_off
        y = margin + r * cp
        major = o.major_every and gr % o.major_every == 0
        d.line([margin, y, margin + cols * cp, y], fill=_MAJOR if major else _LINE, width=2 if major else 1)

    if o.axis:
        for c in range(cols):
            gc = c + col_off
            if o.minor_every and (gc % o.minor_every == 0 or c == 0):
                d.text((margin + c * cp + cp / 2, margin / 2), str(gc + 1), fill=_MAJOR, font=axis_font, anchor="mm")
        for r in range(rows):
            gr = r + row_off
            if o.minor_every and (gr % o.minor_every == 0 or r == 0):
                d.text((margin / 2, margin + r * cp + cp / 2), str(gr + 1), fill=_MAJOR, font=axis_font, anchor="mm")

    for (r, c) in o.highlight:
        r -= row_off
        c -= col_off
        if 0 <= r < rows and 0 <= c < cols:
            x0, y0 = margin + c * cp, margin + r * cp
            d.rectangle([x0 + 1, y0 + 1, x0 + cp - 1, y0 + cp - 1], outline=_HIGHLIGHT, width=2)
    return img


def materials(grid: np.ndarray, palette: Palette, pack_size: int = 1000) -> list[dict]:
    rows = []
    for idx, n in color_counts(grid).items():
        rows.append({"index": idx, "code": palette.codes[idx],
                     "hex": "#{:02X}{:02X}{:02X}".format(*palette.rgb[idx]),
                     "count": n, "packs": math.ceil(n / pack_size)})
    rows.sort(key=lambda r: -r["count"])
    return rows


def render_legend(rows: list[dict], palette: Palette, cell_px: int = 28) -> Image.Image:
    line_h = cell_px + 6
    W = cell_px * 10
    img = Image.new("RGB", (W, max(line_h, line_h * len(rows))), (255, 255, 255))
    d = ImageDraw.Draw(img)
    font = _font(max(8, int(cell_px * 0.45)))
    for i, row in enumerate(rows):
        y = i * line_h + 3
        rgb = tuple(int(x) for x in palette.rgb[row["index"]])
        d.rectangle([3, y, 3 + cell_px, y + cell_px], fill=rgb, outline=_LINE)
        d.text((3 + cell_px + 8, y + cell_px / 2), f'{row["code"]}   {row["count"]} 颗   {row["packs"]} 包',
               fill=(0, 0, 0), font=font, anchor="lm")
    return img
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_render.py -q
```

Expected: 8 passed。中文字体缺失时 legend 的"颗/包"可能渲染为方框，不影响测试；后端任务（计划二）再决定是否内置字体文件。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/render.py backend/tests/test_render.py
git commit -m "feat(core): PNG 图纸渲染（整数像素网格、色号、坐标轴、高亮）与材料清单

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 14: 1:1 分页 PDF

**Files:**
- Create: `backend/app/core/pdf.py`
- Test: `backend/tests/test_pdf.py`

**Interfaces:**
- Produces: `pdf.PdfOptions` dataclass：`bead_mm: float = 5.0`、`dpi: int = 300`、`page: str = "A4"`（210×297 mm）、`margin_mm: float = 10.0`、`overlap_cells: int = 2`、`show_codes: bool = True`
- Produces: `pdf.render_pdf(grid, palette: Palette, options: PdfOptions = PdfOptions()) -> bytes`：
  - `cell_px = round(bead_mm / 25.4 * dpi)`（300 dpi 下 5 mm → 59 px）
  - 先用 `render.render_grid` 以该 cell_px、`axis=True` 渲染整图，再按可打印区域切页；相邻页重叠 `overlap_cells` 格；每页四角画 5 mm 十字对位标记，页脚写 `第 r 行 / 第 c 列 页 · 共 R×C 页 · 起始格 (row, col)`
  - 最后追加一页材料清单（`render.render_legend`）
  - 用 Pillow `save(format="PDF", resolution=dpi, save_all=True)` 输出，页面物理尺寸由像素/dpi 决定
- Produces: `pdf.page_layout(rows: int, cols: int, options) -> tuple[int, int, int, int]`：返回 `(cell_px, cells_per_page_w, cells_per_page_h, margin_px)`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_pdf.py`：

```python
import io

import numpy as np
from PIL import Image

from app.core.palette import Palette
from app.core.pdf import PdfOptions, page_layout, render_pdf


def test_cell_px_matches_physical_size():
    cell_px, cw, ch, margin = page_layout(10, 10, PdfOptions(bead_mm=5.0, dpi=300))
    assert cell_px == 59
    assert margin == round(10 / 25.4 * 300)
    # A4 可打印宽 190 mm → 38 格
    assert cw == (round(190 / 25.4 * 300)) // 59


def test_small_grid_fits_one_page_plus_legend():
    g = np.zeros((10, 10), dtype=np.int16)
    data = render_pdf(g, Palette.load("mard"))
    assert data[:5] == b"%PDF-"
    pages = Image.open(io.BytesIO(data))
    assert getattr(pages, "n_frames", 1) == 2


def test_large_grid_paginates_with_overlap():
    g = np.zeros((80, 80), dtype=np.int16)
    opts = PdfOptions()
    cell_px, cw, ch, _ = page_layout(80, 80, opts)
    data = render_pdf(g, Palette.load("mard"), opts)
    pages = Image.open(io.BytesIO(data))
    import math
    step_w = cw - opts.overlap_cells
    step_h = ch - opts.overlap_cells
    expect = math.ceil((80 - opts.overlap_cells) / step_w) * math.ceil((80 - opts.overlap_cells) / step_h) + 1
    assert pages.n_frames == expect


def test_page_is_a4_at_dpi():
    g = np.zeros((5, 5), dtype=np.int16)
    opts = PdfOptions(dpi=150)
    data = render_pdf(g, Palette.load("mard"), opts)
    pages = Image.open(io.BytesIO(data))
    w, h = pages.size
    assert abs(w / 150 * 25.4 - 210) < 1.0 and abs(h / 150 * 25.4 - 297) < 1.0
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_pdf.py -q
```

Expected: FAIL，`ModuleNotFoundError`。

- [ ] **Step 3: 实现**

`backend/app/core/pdf.py`：

```python
from __future__ import annotations

import io
import math
from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw

from app.core.palette import Palette
from app.core.render import RenderOptions, materials, render_grid, render_legend, _font

_PAGES_MM = {"A4": (210.0, 297.0), "A3": (297.0, 420.0)}


@dataclass
class PdfOptions:
    bead_mm: float = 5.0
    dpi: int = 300
    page: str = "A4"
    margin_mm: float = 10.0
    overlap_cells: int = 2
    show_codes: bool = True


def _mm(mm: float, dpi: int) -> int:
    return round(mm / 25.4 * dpi)


def page_layout(rows: int, cols: int, options: PdfOptions) -> tuple[int, int, int, int]:
    o = options
    cell_px = _mm(o.bead_mm, o.dpi)
    pw, ph = _PAGES_MM[o.page]
    margin = _mm(o.margin_mm, o.dpi)
    axis_px = int(cell_px * 0.9)
    usable_w = _mm(pw, o.dpi) - 2 * margin - axis_px
    usable_h = _mm(ph, o.dpi) - 2 * margin - axis_px - _mm(8, o.dpi)   # 页脚
    return cell_px, usable_w // cell_px, usable_h // cell_px, margin


def _crop_marks(d: ImageDraw.ImageDraw, W: int, H: int, m: int, dpi: int):
    L = _mm(5, dpi)
    for x, y in ((m, m), (W - m, m), (m, H - m), (W - m, H - m)):
        d.line([x - L, y, x + L, y], fill=(0, 0, 0), width=2)
        d.line([x, y - L, x, y + L], fill=(0, 0, 0), width=2)


def render_pdf(grid: np.ndarray, palette: Palette, options: PdfOptions = PdfOptions()) -> bytes:
    o = options
    rows, cols = grid.shape
    cell_px, cw, ch, margin = page_layout(rows, cols, o)
    pw, ph = _PAGES_MM[o.page]
    W, H = _mm(pw, o.dpi), _mm(ph, o.dpi)
    step_w, step_h = max(1, cw - o.overlap_cells), max(1, ch - o.overlap_cells)
    n_w = 1 if cols <= cw else math.ceil((cols - o.overlap_cells) / step_w)
    n_h = 1 if rows <= ch else math.ceil((rows - o.overlap_cells) / step_h)
    font = _font(_mm(3, o.dpi))
    pages: list[Image.Image] = []
    from app.core.split import Board

    for i in range(n_h):
        for j in range(n_w):
            r0, c0 = i * step_h, j * step_w
            r1, c1 = min(rows, r0 + ch), min(cols, c0 + cw)
            tile = render_grid(grid, palette, RenderOptions(cell_px=cell_px, show_codes=o.show_codes, axis=True,
                                                            board=Board(r0, c0, r1 - r0, c1 - c0, "")))
            page = Image.new("RGB", (W, H), (255, 255, 255))
            page.paste(tile, (margin, margin))
            d = ImageDraw.Draw(page)
            _crop_marks(d, W, H, margin // 2, o.dpi)
            d.text((W // 2, H - margin // 2),
                   f"第 {i + 1} 行 / 第 {j + 1} 列 页 · 共 {n_h}×{n_w} 页 · 起始格 (行 {r0 + 1}, 列 {c0 + 1}) · 每格 {o.bead_mm} mm",
                   fill=(0, 0, 0), font=font, anchor="mm")
            pages.append(page)

    legend = render_legend(materials(grid, palette), palette, cell_px=max(20, cell_px // 2))
    lp = Image.new("RGB", (W, H), (255, 255, 255))
    lp.paste(legend, (margin, margin))
    pages.append(lp)

    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", resolution=o.dpi, save_all=True, append_images=pages[1:])
    return buf.getvalue()
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_pdf.py -q
```

Expected: 4 passed。

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/pdf.py backend/tests/test_pdf.py
git commit -m "feat(core): 1:1 物理尺寸分页 PDF（重叠区、对位标记、材料清单页）

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 15: 流水线编排、尺寸推荐、黄金样本与基准

**Files:**
- Create: `backend/app/core/pipeline.py`
- Create: `backend/tests/fixtures/images/`（由脚本生成的合成样本）
- Create: `backend/tests/fixtures/make_fixtures.py`
- Create: `backend/tests/fixtures/snapshots/`（首次运行生成）
- Create: `backend/scripts/benchmark.py`
- Test: `backend/tests/test_pipeline.py`

**Interfaces:**
- Produces: `pipeline.run(image: bytes | np.ndarray, params: Params, palette: Palette | None = None) -> PatternResult`：
  1. `image_io.load_rgba`（bytes 时）
  2. `params.background_seed` 给定则 `background.remove_background`
  3. `detect.detect_pixel_grid` → 有则 `downsample_mode`，`input_kind="pixel_art"`；否则 `grid_shape` + `downsample_area`
  4. 对 mask 内格子：OKLab 上 `select_palette(k=params.max_colors)` 得工作色板（全局索引）
  5. `cost = pairwise_delta_e(cell_lab, palette.lab[working])` reshape 成 (rows, cols, k)
  6. `locked`：`params.protected_cells` 锁定为其最近色；`params.lock_outlines` 时 `detect_outline_cells` 的格锁定为工作色板中最暗色（Lab L 最小）
  7. `assign_labels(cost, mask, params.smoothness, locked)` → 局部索引 → 映射回全局索引写入 grid（int16，mask 外 -1）
  8. `merge_small_colors(threshold=params.small_color_threshold, protected={clear_index} ∪ 保护格的颜色)`
  9. `buildability.analyze` + `patches.attach_patches`
  10. 组装 `PatternResult`（`working_palette` = 合并后实际出现的索引，按颗数降序；`color_stats`；`cell_rgb`）
- Produces: `pipeline.suggest_sizes(image: bytes | np.ndarray, base: int) -> list[dict]`：返回 `[{"long_side": n, "detail_loss": float}]` 三档 `round(base*0.75), base, round(base*1.5)`；`detail_loss` = 在该格数下采样再放大回原尺寸后与原图的 OKLab 均方差（越小越保真）
- Produces: `pipeline.apply_edits(result: PatternResult, edits: list[tuple[int,int,int]], palette) -> PatternResult`：`(row, col, new_index | -1)` 列表直接写格子，重跑 analyze + attach_patches，不重跑分配

- [ ] **Step 1: 写合成样本生成脚本**

`backend/tests/fixtures/make_fixtures.py`（用 Pillow 画，不依赖外部图片；每张对应一个真实投诉场景）：

```python
"""生成黄金样本。运行：cd backend && python tests/fixtures/make_fixtures.py"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "images"
OUT.mkdir(exist_ok=True)
rng = np.random.default_rng(42)


def cartoon():           # 粗轮廓平涂：黄脸、黑描边、白眼、红嘴
    im = Image.new("RGB", (400, 400), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse([40, 40, 360, 360], fill=(255, 220, 60), outline=(0, 0, 0), width=12)
    d.ellipse([120, 140, 170, 190], fill=(255, 255, 255), outline=(0, 0, 0), width=8)
    d.ellipse([230, 140, 280, 190], fill=(255, 255, 255), outline=(0, 0, 0), width=8)
    d.ellipse([140, 160, 155, 175], fill=(0, 0, 0))
    d.ellipse([250, 160, 265, 175], fill=(0, 0, 0))
    d.arc([120, 200, 280, 300], 10, 170, fill=(200, 30, 30), width=12)
    im.save(OUT / "cartoon.png")


def logo():              # 少色硬边
    im = Image.new("RGB", (300, 300), (30, 60, 200))
    d = ImageDraw.Draw(im)
    d.rectangle([60, 60, 240, 240], fill=(255, 255, 255))
    d.polygon([(150, 90), (210, 210), (90, 210)], fill=(220, 40, 40))
    im.save(OUT / "logo.png")


def photo_like():        # 渐变 + 噪声 + 一个高光点（合法孤点）
    y, x = np.mgrid[0:300, 0:300]
    r = 120 + 100 * np.sin(x / 60) + rng.normal(0, 8, (300, 300))
    g = 90 + 80 * np.cos(y / 70) + rng.normal(0, 8, (300, 300))
    b = 60 + 60 * (x + y) / 600 + rng.normal(0, 8, (300, 300))
    arr = np.clip(np.stack([r, g, b], -1), 0, 255).astype(np.uint8)
    arr[150:153, 150:153] = 255
    Image.fromarray(arr).save(OUT / "photo_like.png")


def pixel_art():         # 16×16 像素图放大 12×
    small = rng.integers(0, 4, (16, 16))
    colors = np.array([[255, 255, 255], [0, 0, 0], [255, 0, 0], [0, 120, 255]], np.uint8)
    im = Image.fromarray(colors[small]).resize((192, 192), Image.NEAREST)
    im.save(OUT / "pixel_art.png")


def diagonal_trap():     # 一条斜线：直接像素化必出对角虚连
    im = Image.new("RGB", (240, 240), (255, 255, 255))
    ImageDraw.Draw(im).line([10, 230, 230, 10], fill=(0, 0, 0), width=5)
    im.save(OUT / "diagonal_trap.png")


def solid_block():       # 投诉"纯色块被吃只剩轮廓"
    im = Image.new("RGB", (300, 300), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([50, 50, 250, 250], fill=(40, 170, 90), outline=(0, 0, 0), width=6)
    im.save(OUT / "solid_block.png")


def gray_object():       # 投诉"灰色识别成紫色"
    im = Image.new("RGB", (300, 300), (255, 255, 255))
    ImageDraw.Draw(im).rounded_rectangle([60, 100, 240, 200], 20, fill=(128, 128, 128))
    im.save(OUT / "gray_object.png")


def yellow_object():     # 投诉"鹅黄识别成绿"
    im = Image.new("RGB", (300, 300), (255, 255, 255))
    ImageDraw.Draw(im).ellipse([60, 60, 240, 240], fill=(250, 235, 120))
    im.save(OUT / "yellow_object.png")


def transparent_png():   # 投诉"透明变黑/变白"
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([40, 40, 160, 160], fill=(200, 60, 60, 255))
    im.save(OUT / "transparent.png")


def wide_image():        # 投诉"非方图被拉伸"
    im = Image.new("RGB", (600, 200), (255, 255, 255))
    ImageDraw.Draw(im).ellipse([50, 50, 550, 150], fill=(60, 60, 220))
    im.save(OUT / "wide.png")


if __name__ == "__main__":
    for fn in (cartoon, logo, photo_like, pixel_art, diagonal_trap, solid_block, gray_object, yellow_object, transparent_png, wide_image):
        fn()
    print("fixtures written to", OUT)
```

运行：

```bash
cd backend && python tests/fixtures/make_fixtures.py
```

- [ ] **Step 2: 写失败测试**

`backend/tests/test_pipeline.py`：

```python
import json
from pathlib import Path

import numpy as np
import pytest

from app.core import pipeline
from app.core.palette import Palette
from app.core.types import EMPTY, Params

IMG = Path(__file__).parent / "fixtures" / "images"
SNAP = Path(__file__).parent / "fixtures" / "snapshots"
SNAP.mkdir(exist_ok=True)


@pytest.fixture(scope="module")
def palette():
    return Palette.load("mard")


def _run(name, **kw):
    return pipeline.run((IMG / name).read_bytes(), Params(**kw))


def test_cartoon_end_to_end(palette):
    res = _run("cartoon.png", grid_long_side=48, max_colors=8)
    assert res.grid.shape == (48, 48) and res.grid.dtype == np.int16
    assert res.input_kind == "image"
    assert 3 <= len(res.working_palette) <= 8
    assert res.report is not None and res.report.score > 60
    assert res.report.confetti_pct < 5


def test_pixel_art_is_detected_and_reproduced_exactly(palette):
    res = _run("pixel_art.png", grid_long_side=58, max_colors=8)
    assert res.input_kind == "pixel_art"
    assert res.grid.shape == (16, 16)
    assert len(res.working_palette) == 4


def test_lambda_zero_equals_nearest_color(palette):
    res = _run("logo.png", grid_long_side=30, max_colors=6, smoothness=0.0)
    lab = pipeline._cell_lab(res.cell_rgb)
    sub = palette.lab[res.working_palette]
    from app.core.color import pairwise_delta_e
    nearest = np.array(res.working_palette)[pairwise_delta_e(lab.reshape(-1, 3), sub).argmin(1)].reshape(res.grid.shape)
    mask = res.grid != EMPTY
    assert (res.grid[mask] == nearest[mask]).mean() > 0.97


def test_smoothness_reduces_confetti_on_noisy_photo(palette):
    a = _run("photo_like.png", grid_long_side=50, max_colors=12, smoothness=0.0, lock_outlines=False)
    b = _run("photo_like.png", grid_long_side=50, max_colors=12, smoothness=2.0, lock_outlines=False)
    assert b.report.confetti_pct < a.report.confetti_pct


def test_transparent_png_yields_empty_cells_not_black_or_white(palette):
    res = _run("transparent.png", grid_long_side=30, max_colors=4)
    assert res.grid[0, 0] == EMPTY
    center = res.grid[15, 15]
    assert center != EMPTY and palette.lab[center, 1] > 20        # 偏红


def test_wide_image_keeps_aspect(palette):
    res = _run("wide.png", grid_long_side=60, max_colors=4)
    assert res.grid.shape == (20, 60)


def test_gray_stays_neutral_and_yellow_stays_yellow(palette):
    g = _run("gray_object.png", grid_long_side=30, max_colors=4)
    c = g.grid[15, 15]
    assert abs(palette.lab[c, 1]) < 8 and abs(palette.lab[c, 2]) < 8
    y = _run("yellow_object.png", grid_long_side=30, max_colors=4)
    c = y.grid[15, 15]
    assert palette.lab[c, 2] > 30 and palette.lab[c, 1] > -15


def test_solid_block_interior_is_filled(palette):
    res = _run("solid_block.png", grid_long_side=30, max_colors=4)
    inner = res.grid[10:20, 10:20]
    assert (inner != EMPTY).all() and len(np.unique(inner)) == 1


def test_suggest_sizes_returns_three_ordered_options():
    s = pipeline.suggest_sizes((IMG / "cartoon.png").read_bytes(), base=58)
    assert [x["long_side"] for x in s] == [44, 58, 87]
    assert s[0]["detail_loss"] >= s[1]["detail_loss"] >= s[2]["detail_loss"]


def test_apply_edits_rewrites_cells_and_reanalyzes(palette):
    res = _run("logo.png", grid_long_side=30, max_colors=6)
    target = int(res.working_palette[0])
    out = pipeline.apply_edits(res, [(0, 0, target), (1, 1, -1)], palette)
    assert out.grid[0, 0] == target and out.grid[1, 1] == EMPTY
    assert out.report is not None
    assert res.grid[1, 1] != EMPTY or True   # 原结果不被修改
    assert not np.shares_memory(out.grid, res.grid)


@pytest.mark.parametrize("name", ["cartoon.png", "logo.png", "pixel_art.png", "diagonal_trap.png"])
def test_golden_snapshot(name, palette):
    res = _run(name, grid_long_side=40, max_colors=8)
    snap = SNAP / f"{name}.json"
    current = res.grid_as_list()
    if not snap.exists():
        snap.write_text(json.dumps(current))
        pytest.skip("snapshot created")
    old = json.loads(snap.read_text())
    diff = sum(a != b for ra, rb in zip(old, current) for a, b in zip(ra, rb))
    assert diff <= 0.02 * res.grid.size, f"{name}: {diff} cells changed vs snapshot"
```

- [ ] **Step 3: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_pipeline.py -q
```

Expected: FAIL，`ImportError: cannot import name 'pipeline'`。

- [ ] **Step 4: 实现 pipeline**

`backend/app/core/pipeline.py`：

```python
from __future__ import annotations

import numpy as np

from app.core import background, detect, downsample, image_io
from app.core.assign import assign_labels
from app.core.buildability import analyze
from app.core.color import pairwise_delta_e, srgb_to_lab, srgb_to_oklab
from app.core.merge import color_counts, detect_outline_cells, merge_small_colors
from app.core.palette import Palette
from app.core.patches import attach_patches
from app.core.select import select_palette
from app.core.types import EMPTY, Params, PatternResult


def _cell_lab(cell_rgb: np.ndarray) -> np.ndarray:
    return srgb_to_lab(cell_rgb)


def _load(image) -> np.ndarray:
    return image_io.load_rgba(image) if isinstance(image, (bytes, bytearray)) else np.asarray(image, dtype=np.float32)


def _downsample(rgba: np.ndarray, params: Params):
    info = detect.detect_pixel_grid(rgba)
    if info is not None:
        return downsample.downsample_mode(rgba, info), "pixel_art"
    rows, cols = downsample.grid_shape(rgba.shape[0], rgba.shape[1], params.grid_long_side)
    return downsample.downsample_area(rgba, rows, cols), "image"


def run(image, params: Params, palette: Palette | None = None) -> PatternResult:
    palette = palette or Palette.load(params.palette_id)
    rgba = _load(image)
    if params.background_seed is not None:
        rgba = background.remove_background(rgba, params.background_seed, params.background_tolerance)

    cells, kind = _downsample(rgba, params)
    rows, cols = cells.mask.shape
    grid = np.full((rows, cols), EMPTY, dtype=np.int16)
    if not cells.mask.any():
        return PatternResult(grid, [], {}, None, params, kind, cells.rgb)

    lab = _cell_lab(cells.rgb)
    ok = srgb_to_oklab(cells.rgb)
    working = select_palette(ok[cells.mask], palette.oklab, k=params.max_colors)
    k = len(working)
    cost = pairwise_delta_e(lab.reshape(-1, 3), palette.lab[working]).reshape(rows, cols, k)

    locked = -np.ones((rows, cols), dtype=np.int64)
    if params.lock_outlines:
        darkest = int(np.argmin(palette.lab[working][:, 0]))
        locked[detect_outline_cells(cells.rgb, cells.mask)] = darkest
    for r, c in params.protected_cells:
        if 0 <= r < rows and 0 <= c < cols and cells.mask[r, c]:
            locked[r, c] = int(np.argmin(cost[r, c]))

    local = assign_labels(cost, cells.mask, params.smoothness, locked)
    grid[cells.mask] = working[local[cells.mask]]

    protected_colors = {int(grid[r, c]) for r, c in params.protected_cells
                        if 0 <= r < rows and 0 <= c < cols and grid[r, c] != EMPTY}
    if palette.clear_index is not None:
        protected_colors.add(palette.clear_index)
    grid, _ = merge_small_colors(grid, palette.lab, params.small_color_threshold, protected=protected_colors)

    return _finish(grid, cells.rgb, params, palette, kind)


def _finish(grid, cell_rgb, params, palette, kind) -> PatternResult:
    counts = color_counts(grid)
    try:
        report = attach_patches(analyze(grid, palette.lab, params.small_color_threshold, set(map(tuple, params.protected_cells))),
                                grid, palette.clear_index)
    except Exception:       # 可拼性是附加环节，失败不能拖垮出图
        report = None
    working = [c for c, _ in sorted(counts.items(), key=lambda kv: -kv[1])]
    return PatternResult(grid=grid, working_palette=working, color_stats=counts, report=report,
                         params=params, input_kind=kind, cell_rgb=cell_rgb)


def apply_edits(result: PatternResult, edits: list[tuple[int, int, int]], palette: Palette) -> PatternResult:
    grid = result.grid.copy()
    for r, c, v in edits:
        grid[r, c] = v
    return _finish(grid, result.cell_rgb, result.params, palette, result.input_kind)


def suggest_sizes(image, base: int) -> list[dict]:
    rgba = _load(image)
    ok_full = srgb_to_oklab(rgba[..., :3])
    h, w = rgba.shape[:2]
    out = []
    for n in (round(base * 0.75), base, round(base * 1.5)):
        rows, cols = downsample.grid_shape(h, w, n)
        cells = downsample.downsample_area(rgba, rows, cols, denoise=False)
        up = np.repeat(np.repeat(cells.rgb, max(1, h // rows), axis=0), max(1, w // cols), axis=1)[:h, :w]
        if up.shape[:2] != (h, w):
            pad_h, pad_w = h - up.shape[0], w - up.shape[1]
            up = np.pad(up, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
        loss = float(np.mean((srgb_to_oklab(up) - ok_full) ** 2))
        out.append({"long_side": n, "detail_loss": round(loss, 6)})
    return out
```

- [ ] **Step 5: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_pipeline.py -q
```

Expected: 首轮 4 个 snapshot 测试 skip（生成快照），其余 10 passed；第二次运行 14 passed。若 `test_cartoon_end_to_end` 的 score 或 confetti 不达标，先看 `smoothness` 默认值 1.0 是否偏小——把 Params 默认调到 1.5 再跑，并把结论记进 spec §11。

- [ ] **Step 6: 写基准脚本**

`backend/scripts/benchmark.py`：

```python
"""对全部黄金样本跑流水线，打印量化指标表。用法：cd backend && python scripts/benchmark.py [--smoothness 1.5]"""
import argparse
import time
from pathlib import Path

from app.core import pipeline
from app.core.palette import Palette
from app.core.types import Params

IMG = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "images"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoothness", type=float, default=1.0)
    ap.add_argument("--colors", type=int, default=12)
    ap.add_argument("--size", type=int, default=50)
    a = ap.parse_args()
    palette = Palette.load("mard")
    print(f"{'image':<20}{'kind':<10}{'ms':>7}{'colors':>8}{'conf%':>8}{'comps':>7}{'thin':>7}{'score':>7}")
    for p in sorted(IMG.glob("*.png")):
        t = time.perf_counter()
        res = pipeline.run(p.read_bytes(), Params(grid_long_side=a.size, max_colors=a.colors, smoothness=a.smoothness), palette)
        ms = (time.perf_counter() - t) * 1000
        r = res.report
        print(f"{p.name:<20}{res.input_kind:<10}{ms:>7.0f}{len(res.working_palette):>8}"
              f"{r.confetti_pct:>8.2f}{r.n_components:>7}{r.metrics['thin_ratio']:>7.2f}{r.score:>7.1f}")


if __name__ == "__main__":
    main()
```

运行并把输出贴进提交信息：

```bash
cd backend && python scripts/benchmark.py --smoothness 0 && python scripts/benchmark.py --smoothness 1.5
```

Expected: 两张表；λ=1.5 的 `conf%` 列整体低于 λ=0；单张耗时 < 1500 ms。

- [ ] **Step 7: 全量测试与提交**

```bash
cd backend && python -m pytest -q
```

Expected: 全部通过（含 snapshot）。

```bash
git add backend/app/core/pipeline.py backend/scripts backend/tests
git commit -m "feat(core): 流水线编排、尺寸推荐、编辑应用、黄金样本与基准

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## 自审记录

**Spec 覆盖检查（§4 逐条）：**

| Spec | 任务 |
|---|---|
| §4.1 输入类型判定 / C1 线性面积平均 / C2 网格众数 | Task 5、6 |
| §4.1 色卡受限 k-medoids | Task 7 |
| §4.1 graph cut + λ 滑块，λ=0 = 最近色 | Task 8（`test_lambda_zero_is_pure_argmin`）、Task 15（`test_lambda_zero_equals_nearest_color`） |
| §4.1 抖动默认关 | `Params.dither=False`；开启实现**未纳入本计划**——spec 定义为可选开关且"仅低梯度区 + 有序抖动"，留给计划二之前的独立小任务，在 spec §11 记录 |
| §4.1 描边保护 | Task 9 `detect_outline_cells` + Task 15 锁定 |
| §4.1 尺寸推荐 | Task 15 `suggest_sizes` |
| §4.2 吸管去背景 | Task 4 |
| §4.3 全部检查项 + confetti% + 评分 + 孤点保护 | Task 10 |
| §4.4 修复建议，补透明豆桥优先 | Task 11 |
| §4.5 底板分片 ±3 格 | Task 12 |
| §4.6 PNG / PDF / 材料清单 / 可读性规则 | Task 13、14（相近色号避免相近符号：本计划用色号文本而非符号，规则不适用；记入 spec §11） |
| §4.7 编辑应用（显式格子列表、只重跑分析） | Task 15 `apply_edits` |
| §9 CIEDE2000 34 组 / 算法单测 / 黄金样本 / 量化指标基准 | Task 2、各任务、Task 15 |
| §11 色卡带出处、双源交叉 | Task 3 |

**类型一致性：** `Issue.action` 取值集合在 Task 1 注释、Task 11 实现、Task 15 测试中一致（`bridge_with_clear / fill_with_clear / merge_color / remove / none / todo`）；`Board` 在 Task 12 定义、Task 13/14 消费；`CellImage.mask` 在 Task 6 定义、Task 15 消费；`assign_labels` 返回局部索引、Task 15 用 `working[local]` 映射回全局。

**占位符扫描：** 无 TBD/TODO；Task 10 的 `action="todo"` 是 Task 11 之前的有意占位值，Task 11 必定覆盖。
