# 拼豆图纸生成

把图片变成**能拼**的拼豆图纸：不只是像素化，还要保证熨完不散、不断、不掉豆。

与市面工具的核心差异在算法层——色卡受限 k-medoids 选色 + graph cut 分配抑制散点，
外加一套可拼性体检（孤立豆、对角虚连、细线、空洞、confetti%）和"补透明豆桥"修复建议。
依据见 [算法分析与优化](docs/research/2026-09-20-algorithm-analysis.md)。

## 文档

| 文档 | 内容 |
|---|---|
| [设计 spec](docs/superpowers/specs/2026-09-20-pindou-pattern-generator-design.md) | 架构、数据模型、API、待定项 |
| [算法分析与优化](docs/research/2026-09-20-algorithm-analysis.md) | 市面工具缺陷、用户痛点、方法选型与依据 |
| [原始调研报告](docs/research/raw/) | 六份：开源实现横评、用户痛点、像素化、量化/色差、AI 后处理、邻近领域 |
| [实现计划](docs/superpowers/plans/) | 算法核心（已完成）、后端服务（已完成） |

## 本地运行（开发）

前置：Python 3.11+、PostgreSQL 16。

```bash
# 1. 建库（只做一次）
psql -U postgres -h 127.0.0.1 -c "CREATE DATABASE pindou;" -c "CREATE DATABASE pindou_test;"

# 2. 配置
cd backend && cp .env.example .env    # 填入连接串与 SESSION_SECRET

# 3. 安装与建表
python -m venv .venv
./.venv/Scripts/python -m pip install -e ".[dev]"      # Linux/macOS: .venv/bin/python
./.venv/Scripts/python -m alembic upgrade head
./.venv/Scripts/python -m app.cli seed-palettes
./.venv/Scripts/python -m app.cli invite --count 1 --uses 5

# 4. 起服务
./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

接口文档：<http://127.0.0.1:8000/docs>

### AI 重绘

不配置 `backend/providers.yaml` 时自动回退到本地假 provider（posterize，不联网不花钱），
**整条链路照样跑通**。要接真实模型，复制 `providers.yaml.example` 并设置对应的 API key
环境变量；已内置两种适配器：`openai_compatible`（火山方舟 / 百炼兼容模式 / 任意中转网关）
与 `dashscope_native`（通义万相原生异步接口）。

AI 额度按用户计，先扣后跑、失败退回、命中缓存不扣：

```bash
./.venv/Scripts/python -m app.cli quota --user <用户名> --add 20
```

## 测试

```bash
cd backend && ./.venv/Scripts/python -m pytest -q
```

## 算法基准

对全部黄金样本跑流水线并输出量化指标（confetti%、色数、连通块、评分）。
`--smoothness 0` 等价于市面工具的"逐格最近色"行为，是天然对照组：

```bash
cd backend && ./.venv/Scripts/python scripts/benchmark.py --smoothness 2.0
```

## 部署

```bash
cp .env.example .env     # 仓库根，填 POSTGRES_PASSWORD 与 SESSION_SECRET
docker compose up -d --build
```

`db` / `api` / `web`（nginx 托管前端 + 反代 `/api`）。备份 = `pg_dump` + `appdata` 卷。

## 目录

```
backend/app/core/        纯 numpy 算法流水线，不依赖数据库和 FastAPI，可单独 import 进 notebook
backend/app/services/    业务逻辑，纯 SQLAlchemy + core，不 import fastapi
backend/app/api/         路由，只做校验与序列化
backend/app/providers/   AI provider 抽象与适配器
backend/scripts/         算法基准
docs/                    spec、调研、实现计划
```
