# 拼豆图纸生成工具 · 设计 Spec

日期：2026-09-20
状态：已与需求方逐节确认，待写实现计划

## 0. 一句话

上传一张图 → （可选）AI 重绘成适合拼豆的风格 → 生成带 MARD 色号的网格图纸 → 分析可拼性并给修复建议 → 导出 PNG / PDF + 材料清单。先给自己和朋友用，架构按"将来可能成为产品"来搭。

## 1. 目标与非目标

### 目标

- 出的图纸**能拼**：不只是像素化，要保证熨完不散、不断、不掉豆。这是与市面工具的核心差异。
- AI 重绘作为可选前置步骤，把照片变成粗轮廓、纯色平涂、无渐变的风格后再像素化。
- 每次生成的参数、结果、可拼性评分、实拼反馈全部落库，供后续校准算法。
- 多用户（账号密码 + 邀请码），每人独立的 AI 额度。
- 一条命令部署。

### 非目标（v1 明确不做）

- 微信登录、邮箱验证、找回密码、权限角色。
- 管理后台界面（管理员操作走命令行脚本）。
- 图纸社区、分享、点赞。
- 前端本地计算任何图像处理。
- rembg 自动抠图。
- 独立 worker 进程（表建好，进程以后拆）。
- 前端单元测试。

## 2. 技术选型

| 层 | 选择 | 关键理由 |
|---|---|---|
| 后端 | Python 3.12 + FastAPI + Pydantic v2 | 可拼性优化是算法活，numpy/scipy 生态 |
| 图像处理 | numpy + Pillow + scipy.ndimage | 连通域、形态学都是现成的 |
| 色差 | 自写向量化 CIEDE2000 | `colormath` 已停维护且逐点循环，14400 格慢到不能用 |
| ORM | SQLAlchemy 2.0 + Alembic | 抽象数据库，迁移可追溯 |
| 数据库 | PostgreSQL 16 | 多用户并发写；JSONB 存网格和报告；开发/生产同构 |
| 队列 | `jobs` 表 + `SELECT … FOR UPDATE SKIP LOCKED` | 不引入 Redis，几个人的量级够用 |
| 前端 | Vite + React + TypeScript | 纯 UI，所有计算在后端 |
| 认证 | bcrypt + HttpOnly session cookie | 比 JWT 简单，能真正登出 |
| 部署 | Docker Compose：db / api / web(nginx) | 一条命令 |

### 两条硬约束

1. **流水线只实现一次，在 Python 里。** 前端不缓存、不推算，后端返回什么画什么。避免两套实现结果对不上。
2. **AI 是可选环节，可拼性是附加环节。** 二者任一失败都不能让"出一张图纸"这件核心事失败。

## 3. 整体链路

```
上传原图
  └─> [AI 重绘·可选] ──> 入 jobs 表 ──> API 进程内后台任务调 provider ──> 结果落 ai_renders（按输入哈希缓存）
        └─> 预处理（吸管抠背景、裁剪、格数下采样）
              └─> 色彩量化 + CIEDE2000 匹配 MARD 色号
                    └─> 可拼性分析（连通域一次分解，导出全部指标）
                          ├─> 体检报告 + 修复建议（用户逐条 apply / reject）
                          ├─> 超尺寸时底板分片（接缝落在低细节区）
                          └─> 渲染导出：PNG / PDF + 材料清单
                                └─> 参数、结果、评分、反馈全部落库
```

**用户视角只有一次等待**：上传 → 点一下 → 进度条 → 直接看到图纸。后端一个 job 把"AI 重绘 → 默认参数出图纸 → 可拼性分析"一口气跑完。之后调参数在已缓存的 AI 结果上重算，百毫秒级同步返回。不勾 AI 则跳过第一步，几乎不用等。

## 4. 图纸生成流水线

### 4.1 下采样与色彩量化

全程在 **CIELAB** 空间计算距离。

```
原图 → 双边滤波去噪（保边）→ 区域平均下采样到目标格数
     → Lab 空间 k-means 聚到 N 色 → 每个簇心匹配最近 MARD 色号
```

顺序不可颠倒的两处：

- **下采样用区域平均，不用最近邻。** 最近邻随机丢细节，换个格数结果面目全非；区域平均会在色边界造中间色，所以前面先双边滤波压噪。
- **先聚类、再匹配色号。** 反过来做会因为 MARD 色卡密集产出一堆肉眼分不出的近似色。

**抖动（Floyd-Steinberg）默认关闭**，作为开关提供，UI 标注"会显著降低可拼性"。抖动产生的散点正是可拼性的头号敌人。

用户参数：长边格数、最多色数、抖动开关。

> 注：算法调研（见 `docs/research/`）可能建议替换为 Gerstner 2012 类的联合优化方案；本 spec 定义的是接口与默认行为，具体算法在实现计划中按调研结论定。

### 4.2 背景处理

吸管点选 + 容差洪水填充 → 透明（空格）。不上 rembg：AI 重绘那一步的提示词本来就要求纯色背景，用上百兆模型解决一个上游已解决的问题不划算。

### 4.3 可拼性分析

**一次 4-连通域分解，派生全部指标。**

| 检查项 | 算法 | 为什么要管 |
|---|---|---|
| 整图连通性 | 非空格做 4-连通标记，组件数 > 1 报警 | 成品会散成几块 |
| 孤立单豆 | 四邻域全空的格子 | 熨完粘不住 |
| 对角虚连 | 8-连通组件数 < 4-连通组件数 ⇒ 存在只靠对角"看起来连着"的部分，定位接触点 | 拼豆靠**边**相邻熔合，对角等于没连 |
| 单格宽细线 / 悬臂 | 十字结构元腐蚀一次，消失的格子即宽度 ≤ 1 的区域 | 熨完一掰就断 |
| 内部空洞 | 对空格做连通域，不与图像边界连通的即空洞 | 成品中间有洞 |
| 小色号 | 每色统计颗数，低于阈值（默认 10 颗，可配置）标记，算出并入最近色的 ΔE | 为几颗豆单独买一包不值 |

**评分**：各项加权成 0–100。权重 v1 先给经验值，等实拼反馈攒够后回头校准。

### 4.4 修复建议

每条问题产出一个可执行 patch：

```json
{ "type": "isolated_bead", "cells": [[34,17]], "action": "merge_to_neighbor", "target_color": "B12", "delta_e": 3.2 }
```

前端逐条 apply / reject，**不自动改**。修复本质是拿视觉保真度换结构强度，只有用户看着图才能定。apply 后生成新版本 pattern（见 §5），增量重跑分析。

### 4.5 底板分片

底板尺寸为可配置参数，默认值在实现时确认国内常见规格后填入。

算法：在网格上找横竖切割线，候选线代价 = 它切断的同色连通边数，选代价最小者，允许在目标尺寸附近 ±3 格浮动（可配置）。输出每片独立图纸 + 一张总装配图。无解（图比板小、无合理切线）时退化为不分片 / 均匀切分，并在报告中注明。

### 4.6 渲染导出

- **PNG**：网格线 + 每格印色号 + 边缘坐标轴，每 5 格加粗。
- **PDF**：1:1 实际尺寸（5mm 豆 = 每格 5mm），超 A4 自动分页并打拼接标记。
- **材料清单**：色号、色名、颗数、预估包数。

## 5. 数据模型

原则：**凡是将来校准可拼性权重要用到的，现在就落库。**

```
users             id, username, password_hash, ai_quota, ai_used, created_at
invite_codes      code, created_by, max_uses, used_count, expires_at

projects          id, user_id, name, source_image_path, created_at
  ai_renders      id, project_id, provider, model, style_preset_id, prompt, params(JSONB),
                  input_hash, output_path, status, cost, error, created_at
                  —— 按 input_hash + style_preset 命中缓存，不重复扣额度
  patterns        id, project_id, ai_render_id(nullable), parent_id(nullable),
                  params(JSONB)        格数 / 色数 / 抖动 / 色卡 / 背景处理
                  grid(JSONB)          二维数组，值为 palette_colors 索引或 null
                  color_stats(JSONB)   每色号颗数
                  buildability(JSONB)  {score, issues:[{type, cells, action, target_color, delta_e}]} 或 null
                  applied_patch(JSONB) 本版本应用了哪条建议
                  created_at
    feedback      id, pattern_id, user_id, kind(断裂/掉豆/色差/难数格), cells(JSONB), note, created_at

palettes          id, brand, name, version
  palette_colors  id, palette_id, code, name, rgb, lab（预算好）, in_sets(JSONB)

style_presets     id, name, prompt, params(JSONB), version, is_active
                  —— AI 重绘的提示词资产，存库可版本化，不硬编码

jobs              id, type, payload(JSONB), status(pending/running/done/failed),
                  attempts, locked_at, result(JSONB), error, created_at
```

决策记录：

- `grid` 用 JSONB 不用 bytea：120×120 才几十 KB，可查可索引。
- 修复用 `parent_id` 链成版本树，不原地改：`applied_patch` 攒起来就是"哪类修复用户真的认"的数据。UI 上按 project 折叠版本。
- `palette_colors.lab` 预算存储：匹配是热路径。
- `feedback.cells` 精确到格子：反推规则漏洞要靠坐标。
- 导出文件不建表，磁盘按 `pattern_id` 存。
- 大文件（原图、AI 图、PDF）走磁盘，库存路径。存储层抽接口，将来换 OSS 只改实现。

## 6. AI 重绘层

### 6.1 Provider 抽象

```python
class ImageProvider(Protocol):
    name: str
    def redraw(self, image: bytes, style: StylePreset, extra: dict) -> RedrawResult: ...
    def estimate_cost(self, style: StylePreset) -> Decimal: ...
```

- `providers.yaml` 配置每家的 base_url / api_key 环境变量名 / model / 适配器类型。
- v1 两个适配器：`openai_compatible`（火山方舟、百炼兼容模式、任何中转网关）和 `dashscope_native`（通义万相原生异步任务接口：提交 → 轮询）。加一家 = 加一个几十行文件。
- 风格预设的提示词目标：粗轮廓、纯色平涂、无渐变、无抗锯齿、简化细节、纯色背景。存 `style_presets` 表，随调研和反馈迭代。

### 6.2 额度

- 提交 AI 任务时**先扣后跑**，失败退回，防并发刷穿。
- 命中 `ai_renders` 缓存不扣。
- 管理员加额度 = 命令行脚本。

### 6.3 失败处理

- provider 超时 / 报错重试 2 次；仍失败 job 标 failed、退额度、前端提示"可跳过 AI 直接出图"。
- 返回图无法解析：同上，原始响应存 `job.error`。
- 服务启动钩子：把 running 的 job 标 failed 并退额度。

## 7. API

REST，前缀 `/api`，session cookie 鉴权。

```
POST /auth/register   {username, password, invite_code}
POST /auth/login · POST /auth/logout · GET /auth/me

POST /projects                          上传原图
GET  /projects · GET /projects/{id}     列表按 project 折叠版本

POST /projects/{id}/generate            {use_ai: bool, style_preset_id?, params?}
                                        入 jobs 表，返回 job_id；job 完成后 result 含 pattern_id
GET  /jobs/{id}                         轮询状态

POST /projects/{id}/patterns            {source: original | ai_render_id, params}
                                        同步重算，返回完整 pattern
GET  /patterns/{id}
POST /patterns/{id}/apply-patch         {issue_index} → 新版本 pattern
POST /patterns/{id}/feedback            {kind, cells, note}
GET  /patterns/{id}/export              ?format=png|pdf&board=WxH

GET  /palettes · GET /palettes/{id}/colors
GET  /style-presets
```

**首次生成走 job（含 AI 时要等十几秒），调参走同步接口（百毫秒级）。** 两种耗时特征不同，不强行统一。

参数校验上限：上传 ≤ 20MB，仅 jpg/png/webp；长边 ≤ 200 格；色数 ≤ 64。

## 8. 前端

四个页面一条主线：

```
登录/注册
  └─> 我的项目（列表，按项目折叠版本）
        └─> 项目工作台
              ├─ 左：原图 / AI 结果切换，风格预设，"生成"按钮（含 use_ai 勾选）
              ├─ 中：图纸 canvas（纯展示），问题格子高亮，点击看问题类型
              ├─ 右：参数面板（格数、色数、抖动、吸管抠背景）
              │      可拼性评分 + 问题列表（逐条 apply / reject）
              │      材料清单
              └─ 底：导出（PNG / PDF，选底板尺寸）、实拼反馈入口
```

- 参数改动防抖 300ms 后打 `POST /patterns`，整份 pattern 重画。
- canvas 用 OffscreenCanvas。
- 实拼反馈 = 同一 canvas 框选格子 + 选问题类型 + 备注。

## 9. 测试

- **CIEDE2000**：用 Sharma 2005 附带的 34 组标准测试对验证到小数点后 4 位。
- **算法单元测试**：量化、连通域、对角虚连、腐蚀细线，各用手工构造的 5×5 / 8×8 网格覆盖边界。
- **黄金样本回归**：`tests/fixtures/` 放 5–6 张代表性输入（卡通、Logo、照片、像素图、构造的对角虚连图），固定参数下的 grid 存快照，diff 超阈值报警。
- **API 测试**：TestClient 覆盖注册 / 登录 / 额度扣退 / job 状态流转，provider 用 fake。
- 前端不写单测。

## 10. 部署与项目结构

```
docker-compose.yml
  ├─ db    postgres:16，数据卷持久化
  ├─ api   uvicorn，挂载 ./data，启动时 alembic upgrade head + 灌色卡 seed
  └─ web   nginx 托管前端静态文件 + 反代 /api
```

```
pindou/
├─ backend/
│  ├─ app/
│  │  ├─ core/        纯 numpy 流水线：downsample / quantize / match / buildability / split / render
│  │  ├─ providers/   ImageProvider + openai_compatible + dashscope_native
│  │  ├─ api/         路由
│  │  ├─ models/      SQLAlchemy
│  │  ├─ jobs/        任务表消费（v1 在 API 进程内）
│  │  └─ palettes/    色卡 seed
│  ├─ tests/
│  └─ alembic/
├─ frontend/          Vite + React + TS
├─ docs/
│  ├─ superpowers/specs/
│  └─ research/       算法优化分析
└─ docker-compose.yml
```

`core/` 不依赖数据库和 FastAPI，可单独 import 进 notebook 调算法。

备份：`data/` 目录 + `pg_dump`，cron 脚本。

## 11. 待定项

- 底板尺寸默认值：实现时确认国内常见规格。
- 可拼性评分权重：v1 经验值，攒反馈后校准。
- 下采样 / 量化的具体算法：等 `docs/research/` 调研结论，可能从 k-means 换成 Gerstner 2012 联合优化。接口不变。
- MARD 色卡数据来源与套装划分（144 / 221 / 291）：实现时核实。
