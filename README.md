# JobLens Agent

> Evidence-grounded AI career agent built on real job-market data.
>
> 基于真实招聘岗位与个人经历证据的 AI 求职 Agent：不是“让模型替你猜匹配度”，而是把 **Profile Evidence → Job Requirements → Match → Ranking → Feedback → Skill Gap → Preparation** 做成一条可评测、可追溯、可回归的工程闭环。

[![CI](https://github.com/peewee92/JobLens-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/peewee92/JobLens-Agent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Why JobLens

Most AI job-search demos do one thing:

```text
Resume + Job Description → Prompt → Match Score
```

JobLens treats career recommendations as an evidence and quality problem instead:

```text
Real Profile Evidence
        +
Real Job Postings
        ↓
Versioned JobRequirement Fact Base
        ↓
Eligibility + Evidence-grounded Match
        ↓
Ranking + User Feedback
        ↓
Target Cohort + Skill Gap
        ↓
Resume / Interview Preparation
        ↓
Eval → Human Review → Regression → Release Gate
```

The product goal is deliberately narrow:

> **Given my real experience and a batch of real target jobs, which jobs should I apply to first, and what evidence supports that recommendation?**

## What is implemented

### 运行前检查

后端的 `/api/v1/health` 仅代表进程存活；`/api/v1/readiness` 才检查数据库连接、迁移版本及所需表。首页、Agent 与求职工作区入口会在环境未就绪时提供中文修复说明，不自动迁移或调用模型。真实数据先用 `scripts.verify_migration_copy` 验证新副本，具体操作见 [后端迁移说明](services/backend/README.md#先检查就绪再验证副本)。主业务闭环优化目前仅落地这一环境切片，不代表运行恢复和反馈闭环已全部完成。

### 1. Real job collection

`apps/collector-extension` is a Chrome extension used to collect real job postings and preserve source quality instead of feeding manually copied JD fragments into the model.

It supports:

- BOSS job search collection;
- multi-city / remote filtering;
- salary filtering and obfuscated-font decoding;
- job deduplication;
- detail-page enrichment and multiline JD preservation;
- source-quality levels such as `full_jd / partial_jd / card_only / unavailable`;
- export of raw jobs, diagnostics and Requirement-review datasets.

### 2. Versioned career evidence

JobLens does not let an LLM silently rewrite the user's career history.

Profile, Evidence and SearchIntent are explicit, versioned facts. Resume extraction first produces a proposal, then a human-confirmed profile becomes the released source of truth.

### 3. JobRequirement fact base

Raw job descriptions are converted into structured, versioned `JobRequirement` facts. Downstream Match / Gap / Preparation flows consume this fact base rather than independently rereading the raw JD and producing inconsistent interpretations.

### 4. Evidence-grounded matching

Recommendations are grounded in:

- confirmed profile evidence;
- explicit search intent;
- released job requirements;
- current match facts and user feedback.

A numeric score is treated as an internal ranking signal, **not a probability of getting the job**.

### 5. Eval-first quality loop

The project applies evaluation from the first LLM pipeline rather than adding an eval dashboard after the product is finished.

```text
Dataset
  ↓
Run
  ↓
Trace / Structured Output
  ↓
Deterministic Assertions + Human Review
  ↓
Accepted Baseline
  ↓
Bad Case Remediation
  ↓
Regression
  ↓
Release Gate
```

Real rejected cases are converted into regression tests before a new semantic policy is released.

### 6. Governed Career Agent and execution layer

The current Career Agent is intentionally **workflow-first** instead of pretending every business action should be an autonomous agent tool.

It already provides:

- a governed Context Builder;
- an explicit Tool Registry;
- coarse-grained read-only tools for Ranking, Skill Gap and Job Preparation;
- fail-closed context validation;
- deterministic Agent routing / grounding evals;
- LangGraph state, persistent checkpoint, durable human interrupt and stale-state recovery;
- an Application Workspace for evidence-grounded resume variants, interview practice, study/evidence actions, application status and re-match feedback.

Natural-language routing and bounded tool-loop engineering are complete at the deterministic boundary. The remaining vNext 1.1 release evidence is an explicitly authorized live-Provider quality gate; it is not represented as a completed model-quality claim.

### 7. Local MCP transport proof

The current vNext 1.3 slice exposes three mature, read-only workflows through a local STDIO Model Context Protocol (MCP) server:

```text
Standard MCP Client
        ↓ STDIO
JobLens MCP Adapter
        ↓
Governed Context Builder → Tool Registry → existing Ranking / Gap / Preparation workflows
```

The slice is deliberately bounded to `rank_match_reports`, `target_cohort_gaps`, and `job_preparation`. It has no Provider calls, no business-fact writes, no remote HTTP service, no Pi Extension, and no automatic application actions.

## Architecture

```mermaid
flowchart LR
    A[Chrome Job Collector] --> B[Next.js Web]
    B --> C[FastAPI Backend]

    C --> D[Career Context]
    C --> E[JobRequirement Pipeline]
    C --> F[Match / Ranking]
    C --> G[Skill Gap / Preparation]

    D --> H[Governed Career Agent]
    E --> H
    F --> H
    G --> H

    C --> I[(SQLite / SQLAlchemy)]
    C --> J[LLM Providers]
    J --> K[Trace + Eval]
    K --> L[Human Review]
    L --> M[Accepted Baseline / Release Gate]
```

### Backend structure

The backend is a **Modular Monolith**, not a demo split into unnecessary microservices:

```text
services/backend/app/
├── api/
├── domain/
├── application/
├── repositories/
├── llm/
├── workflows/
├── agent/
├── evals/
└── tracing/
```

The repository is a polyglot monorepo:

```text
JobLens-Agent/
├── apps/
│   ├── web/                  # Next.js user-facing application
│   └── collector-extension/  # real-job collection Chrome extension
├── services/
│   └── backend/              # FastAPI modular monolith
├── packages/
│   └── contracts/            # cross-boundary contracts
├── data/
│   ├── samples/              # safe sample / fixture data
│   └── evals/                # evaluation datasets
└── docs/                     # architecture, ADRs and implementation notes
```

## Engineering evidence

Local verification snapshot (2026-10-14):

- **1411 Backend tests passing** (`pytest`) in a fresh, isolated virtual environment on the same macOS arm64 machine, installed from `uv.lock` using `uv sync --locked`;
- standard MCP SDK client discovered and successfully called all **3/3 read-only tools** against synthetic SQLite data, with zero Provider calls and zero business writes;
- **170 Web tests passing**, TypeScript typecheck, production build and Web smoke E2E passing using the existing local Web dependencies;
- the first offline dependency sync required downloading `cryptography==50.0.2`; online locked sync succeeded. A separate clean OS or cross-machine installation has **not** been verified;
- schema migrations are managed by Alembic; local resumes, databases and secrets remain excluded from Git.

These results are a local snapshot, not a substitute for CI or cross-machine verification.

## Core design decisions

| Problem | Decision |
|---|---|
| LLM invents career evidence | Important recommendations must link back to confirmed Evidence or JobRequirement facts |
| Every feature becomes an Agent tool | Stable business capabilities stay as Workflows; the Agent composes them |
| Match score is misunderstood | Score is ranking-only, never presented as hiring probability |
| Prompt/model change silently changes production behavior | Versioned eval run + baseline comparison + release gate |
| Bad cases are fixed only by prompt tweaking | Convert real rejected cases into deterministic regression where possible |
| Human decisions get overwritten | Reviews / final decisions are explicit and immutable at the governance boundary |
| Agent receives too much raw context | Governed Context Builder exposes the minimum released facts required by the turn |

More detail:

- [System Architecture](docs/architecture/SYSTEM-ARCHITECTURE.md)
- [Domain Model](docs/architecture/DOMAIN-MODEL.md)
- [Eval & Trace](docs/architecture/EVAL-AND-TRACE.md)
- [LLM / Workflow / Agent Boundary](docs/decisions/0004-llm-workflow-agent-boundary.md)
- [Eval from Day One](docs/decisions/0005-eval-from-day-one.md)
- [Repository Strategy](docs/decisions/0006-repository-strategy.md)
- [Career Agent evolution plan](docs/implementation/P1-Career-Agent-Workflow-First-to-Governed-Agent-Evolution-Plan.md)
- [Career Agent LangGraph vNext PRD](docs/product/P1-career-agent-langgraph-vnext.md)
- [JobLens MCP Server + Pi Extension PRD](docs/product/P1-joblens-mcp-pi-extension.md)

## Quick start

### Backend

Requirements: Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

```bash
cd services/backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Run tests:

```bash
cd services/backend
uv run pytest -q
```

### Local MCP server (vNext 1.3 transport proof)

The MCP server uses the official Python SDK and only exposes three read-only tools. It reads the same local SQLite database as the Backend; it does not start FastAPI and stdout is reserved for the MCP protocol.

```bash
cd services/backend
uv sync
DATABASE_URL=sqlite:///./data/joblens.db uv run python -m scripts.run_mcp_server
```

For a fully reproducible standard-client demonstration, create a disposable synthetic database (it contains 20 synthetic review cases because the same release gate is exercised), then call the server through the official SDK client:

```bash
cd services/backend
uv run python -m scripts.seed_mcp_demo --database ./data/joblens-demo.db
uv run python -m scripts.run_mcp_demo_client \
  --database ./data/joblens-demo.db \
  --job-id job_mcp_demo_01 \
  --job-id job_mcp_demo_02 \
  --prepare-job-id job_mcp_demo_01
```

The output lists discovered tools and the three structured MCP responses. Do not commit databases, resumes, raw job data or Provider credentials.

### Web

Requirements: Node.js and `pnpm`.

```bash
cd apps/web
cp .env.example .env.local
pnpm install
pnpm dev
```

Run verification:

```bash
cd apps/web
pnpm test
pnpm typecheck
pnpm build
```

> The repository intentionally ships only safe samples and fixtures. Personal resumes, local databases, raw private job datasets and Provider credentials should remain local.

## Product workflow

```text
1. Import / confirm career profile
2. Define SearchIntent
3. Collect or import real target jobs
4. Extract JobRequirements
5. Pass requirement quality gate
6. Run eligibility + evidence-grounded Match
7. Rank the batch
8. Record explicit user feedback
9. Build a target cohort and analyze Skill Gaps
10. Prepare evidence-grounded resume / interview material
```

## Current Agent boundary

JobLens intentionally distinguishes **AI workflows** from an **Agent Runtime**.

Implemented today:

```text
Governed Context
      ↓
Structured Career Agent turn
      ↓
Tool Registry
      ↓
Mature Workflows
      ↓
Grounded output
```

Runtime evolution target:

```text
Existing Ranking / Gap / Preparation Workflows
      ↓
AgentRuntime boundary
      ↓
LangGraph Career Runtime
      ↓
Explicit State + Conditional Routing
      ↓
Persistent Checkpoint
      ↓
Target Cohort Human Interrupt
      ↓
Approve / Edit / Reject
      ↓
Resume + stale-state validation
      ↓
Skill Gap
      ↓
Trajectory Eval / Release Gate
```

The LangGraph path deliberately focuses on `Ranking → Target Cohort → HITL → Resume → Skill Gap`, so State, Checkpoint and recovery are exercised against existing JobLens Workflows. The local MCP adapter is a separate transport boundary: it reuses the governed Registry and never becomes a second Agent runtime.

Detailed plans:

- [Career Agent LangGraph Runtime Integration Plan](docs/implementation/P1-Career-Agent-LangGraph-Runtime-Integration-Plan.md)
- [JobLens LangGraph Runtime Interview Execution Plan](docs/implementation/P1-JobLens-LangGraph-Runtime-Execution-Plan.md)
- [Multi-Agent Development Collaboration Plan](docs/implementation/P1-JobLens-Multi-Agent-Development-Collaboration-Plan.md)

## Interview-oriented Backend Labs (local learning track)

> This section is a local learning / interview-preparation track built on the real JobLens codebase. It is **not** a separate product roadmap and should not create parallel demo services. Each lab must end with a runnable experiment, a short design note, and interview questions answered from this repository.

### Lab 1 — Trace one FastAPI request from HTTP to DB

Use a real read path such as `GET /api/v1/jobs` or `GET /api/v1/match-ranking`.

```text
HTTP request
→ FastAPI Router
→ Depends / dependency provider
→ Application Use Case
→ Repository Port
→ SQLAlchemy Repository
→ Session / DB
→ Response Schema
```

Concrete anchors:

- `services/backend/app/api/v1/jobs.py`
- `services/backend/app/api/deps.py#get_list_jobs_use_case`
- `services/backend/app/application/job_queries/`
- `services/backend/app/application/ports/job_query_repository.py`
- `services/backend/app/repositories/sqlalchemy_job_query_repository.py`
- `services/backend/app/db/models.py`

Deliverables:

- draw the actual call path with concrete JobLens classes/files;
- explain why Router does not contain SQL/business rules;
- explain Pydantic request/response validation and dependency injection;
- explain the difference between 404 / 409 / 422 / 500 in this API;
- add or identify one test that proves the boundary;
- record one **60–90 second interview answer** without reading notes.

Target effort: **~2h**.

### Lab 2 — `asyncio`: concurrency, timeout and backpressure

Build a tiny JobLens-side experiment around three simulated or real I/O calls.

Compare:

```text
sequential awaits
vs
asyncio.gather
vs
bounded concurrency with Semaphore
```

Add:

- per-call timeout;
- cancellation behavior;
- one CPU-heavy example showing why it should not block the event loop;
- a short note on where JobLens/AI Provider calls benefit from async and where they do not.

Interview outcome: be able to explain that async mainly improves I/O concurrency, not the speed of one model call.

Target effort: **2–3h**.

### Lab 3 — SQLAlchemy Session / Transaction / Idempotency

Use a real write path such as UserFeedback, Eval Review, Final Decision or another immutable JobLens command.

Study and demonstrate:

```text
Session
→ flush
→ commit
→ rollback
→ transaction boundary
→ unique constraint
→ duplicate request handling
```

Concrete anchors:

- `services/backend/app/repositories/sqlalchemy_job_requirement_unit_of_work.py`
- `services/backend/app/repositories/sqlalchemy_career_context_unit_of_work.py`
- `services/backend/app/repositories/sqlalchemy_trace_unit_of_work.py`
- `services/backend/app/api/deps.py` UoW factories

Required failure scenario:

> A Tool/HTTP request writes successfully, but the client times out and retries. How does JobLens avoid creating a duplicate business fact?

Answer using a concrete combination of idempotency identity, query-before-write where appropriate, database uniqueness, transaction boundaries and HTTP conflict semantics.

Required experiment: inject an exception after one staged write and prove the transaction rolls back instead of leaving a half-written business state.

Target effort: **~3h**.

### Lab 4 — Index / Pagination / Slow-query reasoning

Pick real tables such as:

- Job / JobSource;
- MatchReport;
- UserFeedback;
- Eval Run / Case Result;
- Trace spans.

Start from the real Job Pool query in `services/backend/app/repositories/sqlalchemy_job_query_repository.py`, which combines `LIKE` filters, source existence, latest-source ordering, `LIMIT` and `OFFSET`.

For at least two queries:

- write the filter/order pattern;
- identify a plausible index;
- inspect it with SQLite `EXPLAIN QUERY PLAN` (or PostgreSQL `EXPLAIN ANALYZE` when available);
- explain why `%keyword%` search is not rescued by an ordinary B-tree index;
- explain composite-index prefix rules;
- explain why deep `OFFSET` pagination becomes expensive and when cursor/keyset pagination is preferable;
- state the write-amplification cost of extra indexes.

Target effort: **~2h**.

### Lab 5 — Redis for Agent systems: what belongs there and what does not

JobLens remains SQLite-first locally; this lab is a design + minimal runnable Redis exercise, not a mandate to migrate domain truth into Redis.

Implement or prototype 2–3 of:

```text
rate limit
short-lived run progress
hot read cache
distributed lock / lease
idempotency token
```

Then explain why these facts should **not** live only in Redis:

```text
Confirmed Profile / Evidence
Released JobRequirement
MatchReport
Human Review / Final Decision
```

Those are durable auditable business facts and need the primary database/system of record.

Target effort: **2–3h**.

### Lab 6 — Long-running Run + SSE progress / reconnect

Map an AI run into an explicit backend lifecycle:

```text
POST /runs
→ run_id
→ worker/runtime
→ persisted run state
→ SSE progress events
→ completed / failed / cancelled
```

Design and, where practical, implement a minimal JobLens experiment covering:

- SSE vs WebSocket selection;
- client disconnect without silently corrupting the run;
- reconnect using `run_id`;
- whether events need replay / sequence numbers;
- cancel semantics;
- final state persisted independently of the browser connection.

Connect this lab back to the LangGraph checkpoint/resume work rather than creating another isolated runtime. The target state machine should line up with `docs/implementation/P1-JobLens-LangGraph-Runtime-Execution-Plan.md`:

```text
created
→ running
→ waiting_human
→ running
→ completed / failed / cancelled / stale
```

Target effort: **2–3h**.

### Backend Lab completion rule

A lab is complete only when all four artifacts exist:

```text
1. concrete JobLens code path or runnable experiment
2. one failure case
3. one verification/test
4. a 60–90 second interview answer
```

Do **not** spend the month completing a generic Python backend course before touching these labs. The goal is to make the backend concepts answerable from JobLens itself.

## Roadmap

Near-term public-project priorities, in execution order:

- [x] `vNext 1.0 / LG-0～LG-4`: LangGraph Runtime、State / Checkpoint、Durable HITL / Resume、Trajectory Eval 与最小 Web 纵向切片已经落地；
- [x] `vNext 1.1 Core`: Natural-language Intent Contract、Dynamic Tool Selection、Bounded Tool Loop、Context / Error、PendingAction、Runtime Dispatch、timeout / cancellation 已形成工程闭环；
- [ ] `vNext 1.1 Release Evidence`: 真实 Provider 的 Intent 60 + Tool Selection 44 模型质量证据仍待人工付费会话完成；这是发布门，不再阻塞后续无副作用工程开发；
- [x] `vNext 1.2 Job Search Execution Layer`：`Application Workspace → Resume Variant → Interview / Mock → Action → Evidence → Re-match` 已形成工程闭环；固定 Release Gate 为 Resume 30 + Interview 30 + Execution State 20，80/80 确定性验证通过，Provider calls=0；
- [ ] **下一工程主线：`vNext 1.3`**：JobLens MCP Server / external agent integration；
- [ ] `vNext 2.0`: Continuous Career Agent / proactive refresh / long-term plan；
- [ ] concise demo video and reproducible public sample dataset.

Engineering progression 与 release promotion 分开管理：外部 Provider、人工付费或人工验收可以阻塞对应版本发布，但不能让后续可离线验证、无外部副作用的主需求工程长期停摆。

The detailed engineering history remains in `docs/`; the README intentionally focuses on the product, architecture and verifiable engineering evidence rather than internal phase numbering.

## License

MIT. See [LICENSE](LICENSE).

### 主业务闭环：阶段 2A（证据与资格）

缺少技能、教育或专项年限证明不再直接判定不合格；确定性总年限冲突仍保留。没有核心证据支持的待核实岗位归为证据不足。新报告独立记录规则版本，旧快照保留原结论、不混入当前排序。偏好约束、完整推荐展示和运行恢复尚未包含在本切片，参见 [需求与验证记录](docs/implementation/P1-main-loop-eligibility-evidence.md)。

### 主业务闭环：阶段 2B（求职偏好）

城市、最低月薪、远程和排除词现在进入资格判断：明确冲突不进入默认推荐，未知条件保留待核实。“接受远程”不等于“只接受远程”。新报告保存意向版本及偏好依据，修改偏好或关键岗位字段后旧报告退出当前排序，历史快照不变。自由文本限制不由模型猜测解释，参见 [规则、边界与验证记录](docs/implementation/P1-main-loop-search-preferences.md)。

### 主业务闭环进展：保存当次分析（2026-10-25）

目标确认后，现在会保存当时的能力差距、逐岗位准备材料及事实版本，并可从原运行重新打开。刷新或重启不重新生成；资料变化后保留历史材料并明确提示不再适用。保存失败可显式继续，不留下“已完成但材料没保存”的半成品。

详见 [事实绑定与保存结果](docs/implementation/P1-main-loop-analysis-snapshot.md)。该切片没有调用收费模型、没有修改真实求职记录；一键进入工作区、反馈后的新旧结果比较仍在后续阶段，不能据此宣称完整求职闭环已完成。

主闭环 4A：已保存的分析结果页可以一键建立/复用目标岗位工作区、简历事实草稿和来源行动；刷新、并发和请求重试不会重复建立同一批材料，历史准备材料可以重新打开。尚未完成统一首页工作台和完整反馈再分析闭环，详见 [4A 交付记录](docs/implementation/P1-main-loop-start-execution.md)。

主闭环 4B：首页现为任务工作台，汇总准备情况、当前分析、目标工作区和最近变化，只突出一个下一步；GET 不启动业务执行、不保存重复进度。见 [工作台交付记录](docs/implementation/P1-main-loop-workbench.md)。

主闭环 5A：确认真实新事实时，新版职业资料、提案确认和确认事件共同提交；行动/投递状态与事件同样原子保存。并发、最后一步失败回滚与重复确认已用真实 SQLite 验证。反馈事务边界见 [5A 交付记录](docs/implementation/P1-main-loop-feedback-transactions.md)。

主闭环 5B：普通准备行动也能提交真实成果；用户选择行动原始要求，核对当前职业资料后保存待确认提案。原始依据和确认基准分开保存，资料变化后显式另存重新核对提案，不改原文；同一来源只确认一次。网页暂存原事实请求以恢复网络失败，刷新不自动发送。完整范围再分析与结果比较仍待 5C。见 [真实成果核对交付记录](docs/implementation/P1-main-loop-evidence-review.md)。

主闭环 5C-1a：已保存分析页新增更新范围预检，可查看原目标/整批岗位的复用、规则重算候选（最多 5 个）、模型授权缺口与输入修复。查看预检不改旧材料、不调用模型；更新执行、保存新结果和新旧比较仍在后续切片。见 [限定范围更新记录](docs/implementation/P1-main-loop-analysis-update.md)。

**主闭环更新进展（5C-1b-2）**：确认新事实后，可从原目标/原批次预检进入独立新分析；复用兼容报告，每次最多规则重算 5 个岗位，逐项保留进度，重启后显式继续。报告与步骤同事务保存，旧结果保留；用户明确选择部分岗位时如实标注未完成范围。离线规则路径与恢复已验证，不调用模型；统一入口和完整反馈闭环验收尚未完成，新旧比较见下方最新进展。[实施与证据](docs/implementation/P1-main-loop-analysis-update.md)。

**主闭环最新进展（5C-2）**：保存结果页可对比本次更新与明确来源的原结果，逐项查看推荐、证据与偏好判断；资料变了但结论没变也是合法结果。要求/规则不同、归档缺失或部分范围不伪造改善与名次升降。只读、零模型，离线浏览器与全量回归通过；入口收敛、模型授权计量和完整用户链路仍待后续。[结果比较实施证据](docs/implementation/P1-main-loop-analysis-comparison.md)。
