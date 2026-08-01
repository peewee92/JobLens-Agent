# ADR-0002：后端技术栈

## 状态

Accepted

## 决策

MVP 与可预见的 P1 阶段，后端技术栈冻结为：

- **FastAPI**：HTTP 框架（单一进程，不拆 API / Agent 两个服务）；
- **Pydantic**：请求/响应校验与 Structured Output 约束；
- **SQLAlchemy**：ORM 与 Repository 层；
- **Alembic**：数据库迁移。

前端保持原计划：Next.js + TypeScript（Web UI）。LLM 侧用 Pydantic / JSON Schema 约束结构化输出。

## 约束

- MVP 不引入额外 Web 框架或 GraphQL；
- 不使用独立 Agent 服务进程，Agent 作为后端应用内的一个模块（见 SYSTEM-ARCHITECTURE 与 ADR-0004）；
- 迁移工具只用 Alembic，不手写 SQL 迁移脚本。

## 原因

- FastAPI + Pydantic 与 Structured Output 天然契合，降低 LLM Artifact 校验成本；
- SQLAlchemy 同时支持 SQLite（MVP）与 PostgreSQL（P1），模型层零切换；
- 单体分层即可满足 MVP，过早微服务只增加部署与追踪复杂度。

## 影响

- `services/backend/app` 按 `api / domain / application / repositories / llm / workflows / agent / evals / tracing` 分层（重构与 Phase 1 一起做）；
- 所有对外契约以 `packages/contracts/schemas/` 为准。
