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

`apps/collector-extension` 已包含岗位筛选插件 v1.4.6，当前负责：

- BOSS 岗位搜索与采集
- 多城市与全国远程
- 薪资过滤与 BOSS 字体混淆解码
- 岗位去重
- 详情补采与 JD 多行结构保真
- `full_jd / partial_jd / card_only / unavailable` 质量分级
- Requirement 验收资格、岗位职责/任职条件内容门禁、详情预取缓冲、近重复 JD 去重与 20 条独立样本门禁
- 基础技能标签
- CSV / JSON / diagnostics / Requirement review dataset 导出

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
- [Collector v1.4.0 真实数据验收与 v1.4.1 修复记录](docs/implementation/Collector-v1.4.0-Real-Data-Acceptance-2026-08-04.md)
- [Collector v1.4.1 真实数据验收与 v1.4.2 修复记录](docs/implementation/Collector-v1.4.1-Real-Data-Acceptance-2026-08-04.md)
- [Collector v1.4.2 真实数据验收与 v1.4.3 修复记录](docs/implementation/Collector-v1.4.2-Real-Data-Acceptance-2026-08-04.md)
- [Collector v1.4.3 真实数据验收与 v1.4.4 修复记录](docs/implementation/Collector-v1.4.3-Real-Data-Acceptance-2026-08-04.md)
- [Collector v1.4.4 真实数据验收与 v1.4.5 修复记录](docs/implementation/Collector-v1.4.4-Real-Data-Acceptance-2026-08-04.md)
- [Collector v1.4.5 真实数据验收与 v1.4.6 修复记录](docs/implementation/Collector-v1.4.5-Real-Data-Acceptance-2026-08-04.md)
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
- [Resume Document Parsing / Privacy ADR](docs/decisions/0017-resume-document-parsing-and-privacy-boundary.md)
- [Profile Eval Run / Gate / Live Eligibility ADR](docs/decisions/0018-profile-eval-runs-gates-and-live-eligibility.md)
- [Profile Eval Human Review / Accepted Baseline ADR](docs/decisions/0019-profile-eval-human-review-and-accepted-baseline.md)
- [Profile Eval Review Web Boundary ADR](docs/decisions/0020-profile-eval-review-web-boundary.md)
- [Versioned JobRequirement Fact Base ADR](docs/decisions/0021-versioned-job-requirement-fact-base.md)
- [Requirement Eval Run / Live Eligibility ADR](docs/decisions/0022-requirement-eval-runs-and-live-release-eligibility.md)
- [Requirement Eval Governance API Contract](docs/integration/REQUIREMENT-EVAL-API-CONTRACT.md)
- [Requirement Eval Human Review ADR](docs/decisions/0023-requirement-eval-human-review-and-accepted-baseline.md)
- [Requirement Eval Human Review 实施计划](docs/implementation/P0-3B2-Requirement-Eval-Human-Review-Implementation-Plan.md)
- [Requirement Manual Quality Review 实施计划](docs/implementation/P0-3B3A-Requirement-Manual-Quality-Review-Implementation-Plan.md)
- [真实 Requirement 验收准备实施计划](docs/implementation/P0-3B3B-Requirement-Acceptance-Preparation-Implementation-Plan.md)
- [Requirement 验收准备 CLI 契约](docs/integration/REQUIREMENT-ACCEPTANCE-PREPARATION-CLI.md)
- [可恢复 Requirement 验收准备 ADR](docs/decisions/0024-resumable-requirement-acceptance-preparation.md)
- [Requirement Acceptance Run Control 实施计划](docs/implementation/P0-3B3C-Requirement-Acceptance-Run-Control-Implementation-Plan.md)
- [Requirement Acceptance Run / Canary Review API](docs/integration/REQUIREMENT-ACCEPTANCE-RUN-API.md)
- [Persistent Acceptance Run / Canary Control ADR](docs/decisions/0025-persistent-requirement-acceptance-runs-and-canary-control.md)
- [Requirement Canary Human Gate 实施计划](docs/implementation/P0-3B3D-Requirement-Canary-Human-Gate-Implementation-Plan.md)
- [Immutable Requirement Canary Human Gate ADR](docs/decisions/0026-immutable-requirement-canary-human-gate.md)
- [Requirement Canary Review Workbench 实施计划](docs/implementation/P0-3B3E-Requirement-Canary-Review-Workbench-Implementation-Plan.md)
- [Requirement Canary Review Workbench ADR](docs/decisions/0027-requirement-canary-review-workbench.md)
- [Requirement Live Readiness Gate 实施计划](docs/implementation/P0-3B3F-Requirement-Live-Readiness-Gate-Implementation-Plan.md)
- [Requirement Live Readiness CLI](docs/integration/REQUIREMENT-ACCEPTANCE-READINESS-CLI.md)
- [Requirement Live Readiness Gate ADR](docs/decisions/0028-requirement-live-readiness-gate.md)
- [Requirement Live Session Manifest 实施计划](docs/implementation/P0-3B3G-Requirement-Live-Session-Manifest-Implementation-Plan.md)
- [Requirement Acceptance Session Manifest 契约](docs/integration/REQUIREMENT-ACCEPTANCE-SESSION-MANIFEST.md)
- [Requirement Live Session Manifest ADR](docs/decisions/0029-requirement-live-session-manifest.md)
- [Requirement Local Live Bootstrap 实施计划](docs/implementation/P0-3B3H-Requirement-Local-Live-Bootstrap-Implementation-Plan.md)
- [Requirement Local Live Bootstrap CLI](docs/integration/REQUIREMENT-ACCEPTANCE-LOCAL-BOOTSTRAP.md)
- [Requirement Local Live Bootstrap ADR](docs/decisions/0030-requirement-local-live-bootstrap.md)
- [Requirement Database Checkpoint 实施计划](docs/implementation/P0-3B3I-Requirement-Database-Checkpoint-Implementation-Plan.md)
- [Requirement Database Checkpoint CLI](docs/integration/REQUIREMENT-ACCEPTANCE-DATABASE-CHECKPOINT.md)
- [Requirement Database Checkpoint ADR](docs/decisions/0031-requirement-database-preparation-checkpoint.md)
- [Explicit Live Canary Operator 实施计划](docs/implementation/P0-3B3J-Requirement-Explicit-Live-Canary-Operator-Implementation-Plan.md)
- [Live Canary Operator CLI](docs/integration/REQUIREMENT-ACCEPTANCE-LIVE-CANARY-OPERATOR.md)
- [Explicit Live Canary Operator ADR](docs/decisions/0032-explicit-live-requirement-canary-operator.md)

## 当前阶段

Phase 0.5 已完成（产品与领域模型冻结）。当前主线（详见 [路线图](docs/roadmap/ROADMAP.md)）：

```text
Phase 0.5：产品与领域模型冻结 ✅
Phase 1：Job Data Foundation   ✅ Backend + Minimal Web E2E
Phase 2A：Confirmed Profile + SearchIntent ✅ 手工确认、版本化、Web 闭环
Phase 2B-1：Resume Text Proposal + Eval + Trace ✅
Phase 2B-2：PDF/DOCX Resume Input ✅
Phase 2B-3：Eval Run + Gate + Baseline ✅
Phase 2B-4：Human Review + Accepted Baseline ✅
Phase 2B-5：Eval Review Web ✅
Phase 2B-6：Credential-backed Live Provider Quality ⏳ 等待运行凭据
Phase 3A：JobRequirement Fact Base + Fixture Eval + Web ✅
Phase 3B-1：Requirement Eval Run + Baseline Comparison + Read API ✅
Phase 3B-2：Human Review + Accepted Baseline + Web ✅
Phase 3B-3A：20 Real Jobs Review Batch + Web ✅
Phase 3B-3B：Resumable Real Acceptance Preparation CLI ✅
Phase 3B-3C：Persistent Run + Preflight + Canary Control + Read API ✅
Phase 3B-3D：Immutable Human Canary Gate ✅
Phase 3B-3E：Canary Review Web Workbench ✅
Phase 3B-3F：Live Acceptance Readiness Gate ✅
Phase 3B-3G：Live Canary Session Manifest + Evidence Pack ✅
Phase 3B-3H：Guarded Local Live Bootstrap ✅
Phase 3B-3I：Resumable Database Preparation Checkpoint ✅
Phase 3B-3J：Explicit Live Canary Operator ✅
Phase 3B-3K：Formal Dataset Handoff + Credential-backed Canary + Human Decision ⏸ BLOCKED_BY_HUMAN_GATE
Phase 4：Single Job Match ✅ ENGINEERING_COMPLETE / REAL_MATCH_VALIDATION_BLOCKED（真实 20 岗位中 8 个已有 current MatchReport）
Phase 5：Batch Ranking + UserFeedback ✅ ENGINEERING_COMPLETE / REAL_FEEDBACK_VALIDATION_ACTIVE（真实 20 岗位已全部有 current v42.95 Requirement Extraction；8 个已有 current MatchReport，current-report Feedback 仍需用户重新确认）
Phase 6：Target Cohort + Skill Gap ✅ ENGINEERING_COMPLETE / REAL_REQUIREMENT_REVIEW_ACTIVE（已出现真实 interested / maybe 岗位；20 个 current v42.95 Requirement 已统一为同一 Cohort，并已创建正式 20-case Review Batch，当前等待用户逐 Case 人工验收与最终 accept_for_match / reject_for_match）
Phase 7：Job Preparation ✅ ENGINEERING_COMPLETE / REAL_JOB_VALIDATION_BLOCKED
Phase 8：Career Agent ✅ ENGINEERING_COMPLETE（governed Context Builder + read-only Tool Registry + structured unified turn entrypoint + deterministic Agent Eval 已完成；自由文本路由未作为当前工程完成条件）
Phase 9：Growth Loop / Collector Sync ✅ ENGINEERING_COMPLETE / REAL_LOOP_VALIDATION_BLOCKED
```

截至 2026-09-03 的真实主循环进度由 `cd services/backend && .venv/bin/python -m scripts.check_mvp_progress --json` 复核：离线 MVP gate 已通过，20 个真实岗位已经全部有 current v42.95 Requirement Extraction；8 个已有 current MatchReport，另外 12 个是 `match-ready-without-report`，`requirement-analysis-needed=0`。由于 current MatchReport 更新后旧 Feedback 不再计入 current-report coverage，当前进度检查仍以 `complete_current_user_feedback` 为 Match 主线提示；用户历史真实判断已经出现 `interested / maybe`，因此 Phase 6 同时推进 Requirement accepted baseline。4 个旧 `deepseek-v4-pro` outlier 已由用户逐次确认真实 Provider 成本并重新分析完成，当前 20 个 Requirement Review candidates 已全部统一为 `openai / deepseek-v4-flash / requirement-extractor-v42.95 / requirement-extraction-v7`。随后已创建正式 `Requirement 真实岗位人工验收 · v42.95` 20-case Review Batch；创建批次没有 Provider 调用，当前进度 `0/20 reviewed`。下一 HUMAN_GATE 是用户本人逐 Case 对照完整 JD、Requirement 类型、importance、归一化能力和 evidenceSpan 提交不可变 Accept / Reject；只有 20/20 reviewed、无 stale、非 Fixture 后，页面才允许用户本人提交最终 `accept_for_match / reject_for_match`。若最终接受，立即进入真实 `interested / maybe` Target Cohort → Skill Gap → P0/P1 → Action Plan；若拒绝，则根据人工 issue codes 修 Requirement 质量，不进入 Gap。自动任务不得代签任何 Case 或最终结论。Phase 8 维持 `ENGINEERING_COMPLETE`，不进入 Multi-Agent 或未经独立质量证据支持的自由文本路由。

> 开发原则：不要先做漂亮 Dashboard，也不要先做 Multi-Agent。先把 Phase 1–5（MVP v0.1）跑通，且每个 LLM Pipeline 从第一天接 Eval。进度优先看未完成验收项是否减少，而不是 commit 数。
