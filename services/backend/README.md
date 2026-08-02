# JobLens Backend

JobLens Agent 的 Python Backend，采用 **模块化单体（Modular Monolith）**。

当前已完成：HTTP 运行时、配置、数据库基础设施、Alembic 迁移、P0-1 数据模型、Collector Adapter / Normalizer / Canonical Key、Repository + Unit of Work、`ImportJobsUseCase`、`POST /api/v1/job-imports`、Job Pool 列表/详情查询、导入批次审计详情，以及 candidates 完整持久化。P0-1 主要剩余最小 Web E2E。

## Prerequisites

- Python >= 3.12（推荐用 [uv](https://docs.astral.sh/uv/) 管理）
- [uv](https://docs.astral.sh/uv/)（包管理 / 虚拟环境 / lockfile）

## Install

```bash
cd services/backend
uv sync
```

`uv sync` 会创建虚拟环境、按 `pyproject.toml` 安装依赖，并生成 `uv.lock`。

## Run

```bash
uv run fastapi dev
```

启动后访问：

- Health：`http://127.0.0.1:8000/api/v1/health`
- 交互式文档：`http://127.0.0.1:8000/docs`
- OpenAPI：`http://127.0.0.1:8000/openapi.json`

### Import Collector report

```bash
curl -i \
  -X POST http://127.0.0.1:8000/api/v1/job-imports \
  -H 'Content-Type: application/json' \
  --data @../../data/samples/collector-report-minimal.json
```

成功返回 `201 Created`：

```json
{
  "importId": "imp_...",
  "sourceVersion": "1.3.1",
  "received": 1,
  "created": 1,
  "updated": 0,
  "skipped": 0,
  "errors": []
}
```

重复导入同一岗位时会创建新的 `JobImport` 审计记录，但不会重复创建 `Job`，响应通常为 `created=0 / updated=1`。

查询某次导入审计：

```bash
curl http://127.0.0.1:8000/api/v1/job-imports/imp_xxx
```

返回批次统计、快照、candidateSummary 和按 `inputIndex` 排序的逐条 outcome；数据库中保存的错误 raw 与 candidateRaw 都不进入普通 API。

### Query Job Pool

```bash
curl 'http://127.0.0.1:8000/api/v1/jobs?city=武汉&minSalaryK=20&remoteStatus=unknown&sort=latest&limit=20&offset=0'
```

详情：

```bash
curl http://127.0.0.1:8000/api/v1/jobs/job_xxx
```

列表支持：`q / city / minSalaryK / remoteStatus / source / sort / limit / offset`。普通查询响应不会返回 `sourceRaw`、`canonicalKey` 或 `normalizedSourceUrl`。

## Test

```bash
uv run pytest
```

## Migration commands

Alembic 已指向 `Base.metadata`：

- `20260801_0001_create_job_data_foundation.py` 创建 `jobs / job_sources / job_imports / job_import_items`；
- `20260802_0002_create_job_import_candidates.py` 创建 `job_import_candidates`。

```bash
# 查看当前迁移版本
uv run alembic current

# 查看迁移历史
uv run alembic history

# 应用全部迁移
uv run alembic upgrade head

# 回退一版
uv run alembic downgrade -1

# 检查 ORM metadata 与数据库迁移是否漂移
uv run alembic check
```

## Configuration

配置通过 `.env` + `pydantic-settings` 加载（参考 `.env.example`）：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `APP_ENV` | 运行环境 | `local` |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///./data/joblens.db` |

生产 Secret 不要写死在代码里。

## Project structure

```text
services/backend/
├── pyproject.toml
├── uv.lock
├── .python-version
├── README.md
├── alembic.ini
├── alembic/            # 数据库迁移
├── app/
│   ├── main.py         # Composition Root（创建 App、注册 Router）
│   ├── core/config.py  # 配置（pydantic-settings）
│   ├── api/            # HTTP Router / DTO / DI / Error Mapping
│   ├── domain/
│   │   └── jobs/       # RemoteStatus / RemoteConfidence / ImportOutcome
│   ├── application/
│   │   ├── job_imports/ # Adapter / Normalizer / Canonical Key / ImportJobsUseCase
│   │   ├── job_queries/ # Job Read Models / ListJobs / GetJob
│   │   ├── job_import_queries/ # Import Audit Read Model / Get Detail
│   │   └── ports/       # Write Repository / Query Repository / Unit of Work
│   ├── repositories/    # SQLAlchemy write/query repositories + Unit of Work
│   └── db/
│       ├── session.py  # Engine / Session / SQLite FK enforcement
│       └── models/     # Job / Source / Import / Item / Candidate ORM
└── tests/              # health / ORM / migration / import / query / architecture / HTTP integration tests
```

分层调用方向：`API → Application → Domain → Repository → Database`。
