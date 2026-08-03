# JobLens Agent

> 基于真实招聘岗位数据的个人求职与职业转型 Agent。

JobLens Agent 不是一个只会“帮你改简历”的聊天机器人。它把 **个人经历、求职目标与真实岗位市场** 连接起来，帮助用户完成：

```text
MVP v0.1
Profile
→ SearchIntent
→ Job Pool
→ JobRequirement
→ Eligibility
→ Match
→ Ranking
→ UserFeedback

MVP v0.2
Target Cohort
→ Skill Gap
→ Action Plan
→ Resume / Interview

P1
Career Agent
→ 调用成熟 Workflow
```

v0.1 的核心价值很窄但很硬：

> **基于我的真实经历和一批真实目标岗位，告诉我哪些岗位最值得优先投，以及为什么。**

## MVP v0.1 目标（首个可运行闭环）

只打通一个高价值问题：

> 在我导入的这批真实岗位里，哪些最值得我优先投？理由能不能引用我的真实经历或真实 JD？

v0.2 再回答“缺什么、怎么补、怎么改简历、怎么面试”。P1 才让 Career Agent 成为面向用户的统一入口。

## 项目结构

```text
JobLens-Agent/
├── apps/
│   ├── web/                    # 求职 Agent Web UI
│   └── collector-extension/    # 已有“岗位筛选”Chrome 插件（Job Collector）
├── services/
│   └── backend/                # 后端基线（FastAPI 单体分层，见 services/backend/README.md）
├── packages/
│   └── contracts/              # 跨端契约（JSON Schema + examples）
├── docs/
│   ├── product/                # MVP PRD / 阶段需求（P0-1 ...）
│   ├── roadmap/                # 实施路线图
│   ├── architecture/           # 系统架构 / 领域模型 / 评估与追踪
│   ├── implementation/         # 每个阶段落地计划（P0-1 ...）
│   ├── integration/            # Collector 接入协议
│   └── decisions/              # ADR / 关键决策（0001..0007）
├── data/
│   ├── samples/                # 示例数据
│   └── evals/                  # 评测数据集（ADR-0005：Eval 从第一天）
└── scripts/                    # 开发与验证脚本
```

> 仓库策略：**Polyglot Monorepo + Modular Monolith**。MVP 不把 `services/api` 与 `services/agent` 拆成独立微服务；二者已合并为 **一个 FastAPI 进程** `services/backend`（内部分层 `api / domain / application / repositories / llm / workflows / agent / evals / tracing`）。Agent 当前是 Backend 内部能力，仅在出现独立生命周期 / 扩容需求时才拆出。详见 `docs/decisions/0006-repository-strategy.md` 与 `docs/architecture/SYSTEM-ARCHITECTURE.md`。

## 仓库架构策略

- **一个 Git 仓库**，多语言、多可运行应用：Web（TypeScript）、Collector Extension（JS）、Backend（Python）、Contracts（JSON Schema）。
- 三类内容：`apps`（用户入口）/ `services`（后台服务）/ `packages`（共享资产）。
- Backend 是 **Modular Monolith**：一个进程、一个数据库、逻辑分层；不拆微服务。
- 工具链：JS/TS 用 `pnpm workspace`，Python 用 `uv`；暂不引入 Turborepo / Nx。

## 现有资产

`apps/collector-extension` 已包含岗位筛选插件 v1.3.1，当前负责：

- BOSS 岗位搜索与采集
- 多城市与全国远程
- 薪资过滤与 BOSS 字体混淆解码
- 岗位去重
- 详情补采
- 基础技能标签
- CSV / JSON / diagnostics 导出

在新系统中，它被定位为 **Job Collector**，只负责获取真实岗位数据，不承担职业判断与 LLM 分析。

## 推荐技术栈

第一阶段（已冻结，见 ADR-0002 / ADR-0003）：

- Web：Next.js + TypeScript
- 后端：FastAPI + Pydantic（单体进程，不拆微服务）
- ORM / 迁移：SQLAlchemy + Alembic
- Database：SQLite（MVP）→ PostgreSQL（Production / P1）
- LLM 结构化输出：Pydantic / JSON Schema
- Eval：pytest + 固定评测数据集（从第一个 LLM Pipeline 开始，见 ADR-0005）

## 文档入口

- [MVP 产品需求](docs/product/PRD-MVP.md)
- [阶段需求：P0-1 Job Data Foundation](docs/product/P0-1-job-data-foundation.md)
- [阶段实施计划：P0-1 Job Data Foundation](docs/implementation/P0-1-Job-Data-Foundation-Implementation-Plan.md)
- [产品与工程路线图](docs/roadmap/ROADMAP.md)
- [系统架构](docs/architecture/SYSTEM-ARCHITECTURE.md)
- [领域模型](docs/architecture/DOMAIN-MODEL.md)
- [评估与追踪](docs/architecture/EVAL-AND-TRACE.md)
- [Collector 接入契约](docs/integration/COLLECTOR-CONTRACT.md)
- [MVP 范围决策](docs/decisions/0001-mvp-scope.md)
- [后端技术栈 ADR](docs/decisions/0002-backend-stack.md)
- [数据库策略 ADR](docs/decisions/0003-database-strategy.md)
- [LLM / Workflow / Agent 边界 ADR](docs/decisions/0004-llm-workflow-agent-boundary.md)
- [Eval 从第一天开始 ADR](docs/decisions/0005-eval-from-day-one.md)
- [仓库策略 ADR（Monorepo + Modular Monolith）](docs/decisions/0006-repository-strategy.md)
- [Job 身份、来源与远程状态 ADR](docs/decisions/0007-job-identity-source-and-remote-model.md)
- [Profile + SearchIntent 实施计划](docs/implementation/P0-2-Profile-SearchIntent-Implementation-Plan.md)
- [版本化 Profile / Evidence / SearchIntent ADR](docs/decisions/0015-versioned-profile-evidence-and-search-intent.md)
- [Profile Extraction Proposal / Eval / Trace ADR](docs/decisions/0016-profile-extraction-proposal-eval-and-trace.md)

## 当前阶段

Phase 0.5 已完成（产品与领域模型冻结）。当前主线（详见 [路线图](docs/roadmap/ROADMAP.md)）：

```text
Phase 0.5：产品与领域模型冻结 ✅
Phase 1：Job Data Foundation   ✅ Backend + Minimal Web E2E
Phase 2A：Confirmed Profile + SearchIntent ✅ 手工确认、版本化、Web 闭环
Phase 2B-1：Resume Text Proposal + Eval + Trace ✅
Phase 2B-2：PDF/DOCX Resume Input ✅
Phase 2B-3：Live Provider Quality ← 下一阶段
Phase 3：Requirement Intelligence
Phase 4：Single Job Match
Phase 5：Batch Ranking + UserFeedback
Phase 6：Target Cohort + Skill Gap
Phase 7：Job Preparation
Phase 8：Career Agent
```

Phase 9（P1/P2：Growth Loop / Collector API 同步）见路线图。

> 开发原则：不要先做漂亮 Dashboard，也不要先做 Multi-Agent。先把 Phase 1–5（MVP v0.1）跑通，且每个 LLM Pipeline 从第一天接 Eval。
