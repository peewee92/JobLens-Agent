# ADR-0006 · 仓库策略：Polyglot Monorepo + Modular Monolith

- **Status:** Accepted
- **Date:** 2026-07-22
- **Deciders:** willi（单人开发 / Owner）
- **Related:** ADR-0002（后端技术栈）、ADR-0003（数据库策略）、ADR-0004（LLM/Workflow/Agent 边界）、ADR-0005（Eval 从第一天）

---

## 1. Context（背景）

JobLens 由多个技术栈不同的可运行部分组成：

- `apps/web`：求职 Agent Web UI（Next.js + TypeScript，规划中）
- `apps/collector-extension`：已有 Chrome 插件，负责采集真实岗位（JavaScript，无构建系统）
- `services/backend`：FastAPI + SQLAlchemy 单体分层（Step 1 已搭基线，Python）
- `packages/contracts`：跨端领域模型（JSON Schema / OpenAPI）
- `docs / data / scripts`：文档、示例与评测数据、脚本

它们共同服务 **JobLens 这一个产品**，且会频繁联动修改（例如一次 `job-imports` 改动同时触碰契约、后端、前端、集成文档）。

历史上仓库曾存在 `services/api` 与 `services/agent` 两个目录，容易让人误以为要拆成两个独立微服务。Step 1 已将其合并为 `services/backend`（一个 FastAPI 进程内分层）。本 ADR 把「仓库层面如何组织」这一决策正式冻结。

---

## 2. Decision（决策）

### 2.1 采用 Polyglot Monorepo

整个产品放在 **一个 Git 仓库** `JobLens-Agent/` 中，但各应用/服务可独立选语言与部署生命周期：

- Web / Extension：TypeScript / JavaScript
- Backend / Agent：Python
- Contracts：JSON Schema / OpenAPI

> 一个 Repo ≠ 一个应用 ≠ 一个进程 ≠ 一种语言。

### 2.2 Backend 采用 Modular Monolith

`services/backend` 是 **一个 FastAPI 进程 + 一个数据库**，代码内部分层：

```text
app/
├── api          # HTTP 边界
├── application  # Use Case / 业务流程
├── domain       # 业务概念与规则
├── repositories # 数据访问
├── db           # Engine / Session / ORM
├── llm          # LLM 能力封装
├── workflows    # 领域 Workflow
├── agent        # Agent Runtime（Backend 内部模块）
├── evals        # 评测
└── tracing      # 统一追踪
```

不拆分 API Service / Agent Service / Profile Service 等微服务。

### 2.3 Agent 先作为 Backend 内部能力

Career Agent 是 Backend 的一种 Application Capability，位于 `services/backend/app/agent/`，复用同一套 Repository / Domain / Application / Trace / Eval。

**仅当**出现以下信号之一，才将 Agent 拆为独立服务（`services/agent-runtime`）：

1. 单次运行时间极长（分钟级），需要独立 Worker / 异步队列；
2. 扩容模型与 API 显著不同（如 API 高 QPS、Agent 少量长任务并发）；
3. 依赖独立基础设施（Sandbox / Browser / GPU / Queue）；
4. 多个产品共用同一 Agent Platform。

### 2.4 三类内容划分

```text
apps       = 用户入口（Web / Extension）
services   = 后台服务（Backend）
packages   = 共享资产（Contracts）
```

Backend 归入 `services/`（而非 `apps/`），以强调「用户客户端 vs 后台服务」的边界。

### 2.5 工具链策略

- JS/TS 应用：未来使用 `pnpm workspace`；
- Python 服务：`uv`（项目级 `pyproject.toml` + `uv.lock`）；
- 根目录提供统一入口（`make dev / make test / make verify` 或 `scripts/*.sh`）。

**暂不引入 Turborepo / Nx 等 Monorepo 框架。**

> 暂缓项：`pnpm-workspace.yaml` 暂不创建。当前 `apps/web` 仅为占位 README、`apps/collector-extension` 仍为纯 JS 无 `package.json`；待任一应用真正初始化（拥有 `package.json`）后再补，避免引用空目录。

### 2.6 `packages/contracts` 的定位

共享 **契约（JSON Schema / OpenAPI / Protocol / Examples）**，而非共享代码。未来理想链路：`Backend Pydantic → OpenAPI → 生成 TS Client → Frontend`。本次新增 `packages/contracts/examples/` 作为示例 payload 的归属目录（初始为空，待出现真实样例时填充）。

### 2.7 `data/` 划分

- `data/samples/`：示例 / 样本数据（已存在，如 `collector-report-minimal.json`）；
- `data/evals/`：固定评测数据集（本次新增，服务于 ADR-0005「Eval 从第一天」）。

---

## 3. Consequences（后果）

### 正向

- 一次 Feature 在一个 Branch 内同时改 Extension / Backend / Contracts / Web / Tests / Docs，无需跨仓库版本杂技；
- 跨层契约（MatchReport 等）的字段改动会在同一次 commit 暴露所有消费方，减少 `matchReason / reason / explanation` 这类漂移；
- Agent 与业务逻辑共用基础设施，避免早期微服务复杂度（鉴权、网络、跨服务 Trace、独立部署）；
- 单人开发下，仓库组织成本极低、收益极高。

### 负向 / 风险

- Monorepo 规模变大后可能出现 CI 变慢、权限隔离难等问题——但 JobLens 当前规模（1 开发者、1 产品、2~3 应用、1 Backend）远未触及；
- 若未来误把 `services/backend/app/agent/` 当成「独立服务」提前做远程调用，会引入无谓复杂度——以本 ADR 第 2.3 节的拆服务信号为闸门。

### 必须遵守的纪律

- 不在 MVP 阶段为「架构好看」提前空建目录或服务；
- `pnpm-workspace.yaml` 等治理文件，仅在对应应用真正初始化后再落地；
- Agent 是否拆服务，以 2.3 节信号为唯一判据，不在 MVP 预判。

---

## 4. 本次具体落地（Step 2）

- 新增 `data/evals/`；
- 新增 `packages/contracts/examples/`；
- 本文档 ADR-0006 冻结仓库策略；
- `README.md` 结构块补充 `data/evals` 与 contracts `examples`，并增加仓库策略说明与链接；
- `AGENTS.md` 架构边界补充本 ADR 引用；
- `packages/contracts/README.md` 标注 `examples/` 位置。

> `services/api` 与 `services/agent` 的合并已在 Step 1（`services/backend`）完成，本 ADR 仅将其确立为长期规则。
