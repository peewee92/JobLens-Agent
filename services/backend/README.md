# JobLens Backend

JobLens Agent 的后端基线（Step 1）：**模块化单体（Modular Monolith）**。

本阶段只建立运行基座，不实现任何业务：HTTP 运行时、配置、数据库基础设施、迁移基础设施、测试基础设施。业务（Job Import / Profile / Match ...）在后续 Vertical Slice 中逐步加入。

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

- API 根：`http://127.0.0.1:8000/api/v1/health`
- 交互式文档：`http://127.0.0.1:8000/docs`

## Test

```bash
uv run pytest
```

## Migration commands

本阶段 Alembic 已初始化并指向 `Base.metadata`，但**尚未创建业务表**。后续 Step 2 才生成第一条迁移。

```bash
# 查看当前迁移版本
uv run alembic current

# 查看迁移历史
uv run alembic history

# （Step 2 起）生成并应用迁移
uv run alembic revision --autogenerate -m "create jobs"
uv run alembic upgrade head
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
│   ├── api/            # HTTP 层（Router / DI）
│   ├── domain/         # 业务概念与规则（本阶段空）
│   ├── application/    # Use Case（本阶段空）
│   ├── repositories/   # 数据访问（本阶段空）
│   └── db/             # Engine / Session / ORM Base
└── tests/              # pytest（test_health / test_db）
```

分层调用方向：`API → Application → Domain → Repository → Database`。
