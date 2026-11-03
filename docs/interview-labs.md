# 面试向 Backend Labs（本地学习轨道）

> 本文件原是 `README.md` 的一部分。为让仓库首页更聚焦「产品 + 工程信号」、避免在招聘方视角下显得像一个课程练习项目，已把这部分移到此处。内容**完整保留**，仅供本地面试准备使用。
>
> 这是一个基于真实 JobLens 代码库的本地学习 / 面试准备轨道，**不是**独立的产品路线图，也不应由此产生平行的演示服务。每个 Lab 都必须以一个可运行实验、一篇简短设计笔记、以及从本仓库回答的面试问题收尾。

## Lab 1 — 跟踪一次 FastAPI 请求：从 HTTP 到 DB

用一条真实的读路径，例如 `GET /api/v1/jobs` 或 `GET /api/v1/match-ranking`。

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

具体锚点：

- `services/backend/app/api/v1/jobs.py`
- `services/backend/app/api/deps.py#get_list_jobs_use_case`
- `services/backend/app/application/job_queries/`
- `services/backend/app/application/ports/job_query_repository.py`
- `services/backend/app/repositories/sqlalchemy_job_query_repository.py`
- `services/backend/app/db/models.py`

交付物：

- 用具体的 JobLens 类 / 文件画出真实调用路径；
- 解释为什么 Router 不包含 SQL / 业务规则；
- 解释 Pydantic 请求 / 响应校验与依赖注入；
- 解释本 API 中 404 / 409 / 422 / 500 的区别；
- 增加或识别一个证明该边界的测试；
- 记录一段 60–90 秒、不翻笔记的面试回答。

目标耗时：**约 2 小时**。

## Lab 2 — `asyncio`：并发、超时与背压

围绕三个模拟或真实的 I/O 调用，做一个小型 JobLens 侧实验。

对比：

```text
sequential awaits
vs
asyncio.gather
vs
bounded concurrency with Semaphore
```

补充：

- 单次调用超时；
- 取消行为；
- 一个 CPU 密集示例，说明为什么它不应阻塞事件循环；
- 一篇短文，说明 JobLens / AI Provider 调用在哪些地方受益于 async、哪些地方不受益。

面试产出：能解释 async 主要改善 I/O 并发，而不是单个模型调用的速度。

目标耗时：**2–3 小时**。

## Lab 3 — SQLAlchemy Session / Transaction / 幂等性

用一条真实的写路径，例如 UserFeedback、Eval Review、Final Decision 或另一个不可变的 JobLens 命令。

研究与演示：

```text
Session
→ flush
→ commit
→ rollback
→ transaction boundary
→ unique constraint
→ duplicate request handling
```

具体锚点：

- `services/backend/app/repositories/sqlalchemy_job_requirement_unit_of_work.py`
- `services/backend/app/repositories/sqlalchemy_career_context_unit_of_work.py`
- `services/backend/app/repositories/sqlalchemy_trace_unit_of_work.py`
- `services/backend/app/api/deps.py` UoW factories

必答失败场景：

> 一个 Tool / HTTP 请求写入成功，但客户端超时并重试。JobLens 如何避免产生重复的业务事实？

用「幂等标识 + 适当写前查询 + 数据库唯一性 + 事务边界 + HTTP 冲突语义」的具体组合来回答。

必做实验：在一次暂存写入后注入异常，证明事务回滚而非留下半成品业务状态。

目标耗时：**约 3 小时**。

## Lab 4 — 索引 / 分页 / 慢查询推理

挑选真实表，例如：

- Job / JobSource；
- MatchReport；
- UserFeedback；
- Eval Run / Case Result；
- Trace spans。

从 `services/backend/app/repositories/sqlalchemy_job_query_repository.py` 里真实的 Job Pool 查询出发（它组合了 `LIKE` 过滤、来源存在性、最新来源排序、`LIMIT` 与 `OFFSET`）。

对至少两条查询：

- 写出过滤 / 排序模式；
- 指出一个合理的索引；
- 用 SQLite `EXPLAIN QUERY PLAN`（或可用时的 PostgreSQL `EXPLAIN ANALYZE`）检查；
- 解释为什么 `%keyword%` 搜索无法被普通 B-tree 索引拯救；
- 解释复合索引前缀规则；
- 解释为什么深 `OFFSET` 分页会变慢，以及何时游标 / keyset 分页更优；
- 说明额外索引的写入放大成本。

目标耗时：**约 2 小时**。

## Lab 5 — Agent 系统中的 Redis：什么该放、什么不该放

JobLens 本地仍以 SQLite 为主；本 Lab 是一次设计 + 最小可运行 Redis 练习，而非强制把领域真相迁移进 Redis。

实现或原型化其中 2–3 个：

```text
rate limit
short-lived run progress
hot read cache
distributed lock / lease
idempotency token
```

然后解释为什么这些事实**不应**只存在于 Redis：

```text
Confirmed Profile / Evidence
Released JobRequirement
MatchReport
Human Review / Final Decision
```

这些是持久、可审计的业务事实，需要主数据库 / 系统记录。

目标耗时：**2–3 小时**。

## Lab 6 — 长时运行 Run + SSE 进度 / 重连

把一个 AI run 映射成显式的后端生命周期：

```text
POST /runs
→ run_id
→ worker/runtime
→ persisted run state
→ SSE progress events
→ completed / failed / cancelled
```

设计并（在可行处）实现一个最小 JobLens 实验，覆盖：

- SSE vs WebSocket 选择；
- 客户端断开而不静默破坏 run；
- 用 `run_id` 重连；
- 事件是否需要重放 / 序号；
- 取消语义；
- 最终状态独立于浏览器连接持久化。

把这个 Lab 连回 LangGraph checkpoint / resume 工作，而不是另起一个隔离运行时。目标状态机应与 `docs/implementation/P1-JobLens-LangGraph-Runtime-Execution-Plan.md` 对齐：

```text
created
→ running
→ waiting_human
→ running
→ completed / failed / cancelled / stale
```

目标耗时：**2–3 小时**。

## Backend Lab 完成规则

一个 Lab 只有在以下四件产物都齐备时才算完成：

```text
1. 具体的 JobLens 代码路径或可运行实验
2. 一个失败用例
3. 一次验证 / 测试
4. 一段 60–90 秒的面试回答
```

**不要**在完成这些 Lab 之前，先花一个月去上一门通用 Python 后端课。目标是让后端概念能从 JobLens 本身给出答案。
