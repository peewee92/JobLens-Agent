# JobLens Backend

JobLens Agent 的 Python Backend，采用 **模块化单体（Modular Monolith）**。

当前已完成：HTTP 运行时、配置、数据库基础设施、Alembic 迁移、P0-1 数据模型、Collector Adapter / Normalizer / Canonical Key、Repository + Unit of Work、`ImportJobsUseCase`，以及 `POST /api/v1/job-imports`。尚未实现 Job Pool Query API 和 Web 页面。

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

## Test

```bash
uv run pytest
```

## Migration commands

Alembic 已指向 `Base.metadata`，第一条业务迁移为 `20260801_0001_create_job_data_foundation.py`，创建：

- `jobs`
- `job_sources`
- `job_imports`
- `job_import_items`

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
│   │   └── ports/       # Repository / Unit of Work 接口
│   ├── repositories/    # SQLAlchemy Repository + Unit of Work
│   └── db/
│       ├── session.py  # Engine / Session / SQLite FK enforcement
│       └── models/     # Job / JobSource / JobImport / JobImportItem ORM
└── tests/              # health / ORM / migration / adapter / repository / use-case / HTTP integration tests
```

分层调用方向：`API → Application → Domain → Repository → Database`。
