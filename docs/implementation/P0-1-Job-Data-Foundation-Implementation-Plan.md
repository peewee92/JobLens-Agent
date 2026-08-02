# P0-1 Job Data Foundation 实施计划

> 目标：打通 Collector → Import → Database → API → Job Pool UI 的第一条真实数据闭环。

**文档定位**：本文是 P0-1 阶段的**实施计划**，回答"按什么顺序落地"。与它配合阅读的文档：

- 需求与验收：[`../product/P0-1-job-data-foundation.md`](../product/P0-1-job-data-foundation.md)（做什么 / 为什么做 / 验收什么）
- 契约：[`../integration/COLLECTOR-CONTRACT.md`](../integration/COLLECTOR-CONTRACT.md)（Collector report 结构与导入约定）
- 技术选型：[`../decisions/0002-backend-stack.md`](../decisions/0002-backend-stack.md)（后端栈冻结）
- 全局顺序：[`../roadmap/ROADMAP.md`](../roadmap/ROADMAP.md)（Phase 0–9）

四者关系：**PRD → ADR / Architecture → Implementation Plan → Code + Tests**。

---

## 0. 现在的原则

上面这些文档和模型改完之后，**下一步不要继续扩需求，也不要再做一轮大架构设计**。

直接进入第一个 Vertical Slice。

---

## 1. 目标

目标只有一个：

> **让 JobLens Collector 采集出来的真实岗位，能够正式进入 JobLens-Agent，并在页面里被查询和查看。**

完整链路：

```text
JobLens Collector
↓
report JSON
↓
POST /api/v1/job-imports
↓
解析 / 校验
↓
标准化
↓
去重
↓
SQLite
↓
GET /api/v1/jobs
↓
Job Pool 页面
```

做到这里，JobLens-Agent 才从"设计项目"第一次变成"真实可运行产品"。

---

## 2. 具体执行顺序

### 当前切片进度（2026-08-02）

| Slice | 内容 | 状态 |
| --- | --- | --- |
| 1 | Backend Baseline | 已完成 |
| 2 | ORM Model + Migration | 已完成 |
| 3 | Collector Adapter + Normalizer + Canonical Key | 已完成 |
| 4 | Repository + Transaction Boundary | 已完成 |
| 5 | ImportJobsUseCase + Idempotency | 已完成 |
| 6 | `POST /api/v1/job-imports` | 已完成 |
| 7 | Job Pool Query API | 下一步 |
| 8 | 最小 Web E2E | 计划中 |

采用该顺序的原因：

```text
外部格式隔离
→ 内部语义稳定
→ 数据访问边界
→ 业务事务
→ HTTP 入口
```

每层都可以独立测试，避免在 Router 中同时完成 JSON 解析、去重、SQLAlchemy 写入和事务处理。

> Slice 4 状态（2026-08-02）：已新增 Application-owned Repository / Unit of Work Port、SQLAlchemy Repository、SQLAlchemy Unit of Work 和 FastAPI UoW Factory。Repository 只负责 query / add / update / flush，不负责 commit / rollback；Application 在一个 Unit of Work 中显式提交整条业务链。事务测试证明：显式 commit 后四表共同持久化，忘记 commit 或中途异常时四表全部回滚。
>
> Slice 5 状态（2026-08-02）：已实现 `ImportJobsUseCase`，完成首次 `created`、重复导入 `updated`、单条 Adapter/Normalizer 问题 `error + skipped`、批次统计不变量和单事务提交。身份冲突会回滚整个新批次；不支持的 Collector 版本在事务前失败。
>
> Slice 6 状态（2026-08-02）：已实现 `POST /api/v1/job-imports`、camelCase Response DTO、FastAPI Dependency Injection 和统一错误映射。成功返回 201；无效/不支持 report 返回 422；身份冲突返回 409；未知错误返回不泄漏内部信息的 500。HTTP 集成测试覆盖真实 SQLite 写入、重复导入、部分错误、回滚和 OpenAPI。当前后端测试为 53 passed。

### 第 1 步：技术基线落地

创建真正的 Backend：

```text
services/backend/
├── app/
│   ├── api/
│   ├── domain/
│   ├── application/
│   ├── repositories/
│   └── db/
├── tests/
└── pyproject.toml
```

第一版技术栈直接定（与 ADR-0002 一致）：

```text
Python
FastAPI
Pydantic
SQLAlchemy
Alembic
SQLite
pytest
```

这一步不要引入：

```text
Agent SDK
LangGraph
Vector DB
Redis
Celery
```

都还不需要。Agent / LLM / Workflow 相关的分层（`llm` / `workflows` / `agent` / `evals` / `tracing`）按 ADR-0002 在后续阶段再补，不在本阶段建空目录。

### 第 2 步：把 Job 模型真正落到代码

> 当前状态（2026-08-01）：**ORM Model + 第一条 Alembic Migration 已完成并验证**。已落地 `JobORM` / `JobSourceORM` / `JobImportORM` / `JobImportItemORM`，开发库已升级到 `20260801_0001`，迁移支持 upgrade / downgrade，ORM 与 Migration 经 `alembic check` 验证无漂移。Pydantic **API Request / Response DTO** 留到 HTTP API Slice 再实现；Collector Adapter 已在独立 Application Boundary 中使用版本化 Pydantic 外部模型，它们不等同于 API DTO。

现在 JSON Schema 只是"设计契约"。下一步需要变成：

```text
Pydantic Model
+
SQLAlchemy Model
+
Database Migration
```

核心至少包括：

```text
Job              # JobLens 统一岗位实体
JobSource        # 外部来源身份与 sourceRaw
JobImport        # 一次 report 导入批次
JobImportItem    # 批次内每条输入的处理结果
```

数据所有权冻结为：

```text
Job
└── 标准化当前状态：title / company / salary / area / skills / remoteStatus / ...

JobSource
└── 来源证据：source / sourceJobId / sourceUrl / sourceRaw / firstSeenAt / lastSeenAt

JobImport
└── 批次快照和汇总

JobImportItem
└── created / updated / skipped / error 的逐条轨迹
```

同时：

- `Job.id` 由 JobLens 生成；
- Collector / 招聘网站 ID 只进入 `JobSource.sourceJobId`；
- `jobs.canonical_key` 持久化并唯一，但不通过公共 Contract 暴露；
- 远程状态采用 `confirmed / rejected / unknown` 三态。

详细决策见 ADR-0007。

原则：

> 永远不要因为后续解析逻辑变化而丢失 Collector 原始数据，也不要让外部来源 ID 控制 JobLens 的内部主键。

### 第 3 步：实现第一个真正的 API

#### `POST /api/v1/job-imports`

输入：

```text
Collector v1.3.1 report JSON
```

完成：

```text
版本识别
↓
Schema 校验
↓
Job Adapter
↓
字段标准化（含三态 remoteStatus）
↓
提取 sourceJobId / 规范化 sourceUrl
↓
生成带版本的 internal canonical key
↓
去重
↓
创建 / 更新
↓
返回导入统计
```

响应类似（字段名与 COLLECTOR-CONTRACT §4 对齐；正式字段见 PRD §4.1）：

```json
{
  "received": 120,
  "created": 80,
  "updated": 35,
  "skipped": 5
}
```

> 这个功能是整个项目第一个真正值得认真做好的后端能力。

### 第 4 步：马上写测试

不要等后面统一补测试。至少写：

```text
test_import_valid_report
test_import_duplicate_report
test_import_same_job_twice
test_import_missing_optional_fields
test_import_unsupported_version
test_import_invalid_payload
```

这里非常适合你的 Build-to-Learn 思路：

> 一边写 FastAPI，一边学习 FastAPI；一边写 SQLAlchemy，一边解决真实数据问题。

不要先单独学一个星期 Python Backend。

### 第 5 步：实现 Job Pool API

至少：

```text
GET /api/v1/jobs
GET /api/v1/jobs/{id}
```

第一版支持：

```text
城市
关键词
最低薪资
远程
分页
排序
```

然后再做：

```text
收藏
忽略
```

收藏和忽略甚至都可以稍晚。

### 第 6 步：做最小 Job Pool 页面

这时候才开始 Web。第一版页面不用漂亮。只需要：

```text
[导入 JSON]

岗位数量：85

----------------------

AI Application Engineer
某某公司
武汉
15-30K

[查看详情]
```

重点是证明：

```text
真实 BOSS 数据
↓
Collector
↓
Backend
↓
Database
↓
Frontend
```

这条链真的跑通。

---

## 3. 完成这一阶段后，再做什么？

### 下一阶段：Profile + SearchIntent

链路：

```text
Resume
↓
Profile Extraction
↓
UserProfile
↓
Evidence
↓
用户确认
```

同时：

```text
用户设置：
AI Application Engineer
Agent Engineer
武汉
远程
最低 14K
```

形成：

```text
SearchIntent
```

### 第三阶段：JobRequirement Extraction

```text
真实 JD
↓
LLM Structured Output
↓
JobRequirement
```

例如：

```text
Python Backend       must_have
RAG                  must_have
Agent Development    preferred
FastAPI              bonus
```

这里开始正式加入：

```text
LLM Provider
Structured Output
Prompt Version
Trace
Eval Dataset
```

### 阶段顺序：严格按此推进

```text
① Job Data Foundation
        ↓
② UserProfile + SearchIntent
        ↓
③ JobRequirement Extraction
        ↓
④ Single Job Match
        ↓
⑤ Batch Ranking + UserFeedback
```

做到第 ⑤ 步，我认为：

> **JobLens MVP v0.1 就已经成立了。**

因为用户已经可以：

```text
导入自己的真实经历
+
导入真实岗位
↓
看到哪些岗位最值得投
↓
知道为什么
↓
反馈系统判断是否正确
```

这已经有独立产品价值。

### Skill Gap 和 Career Agent 不要急着做

尤其不要现在就开始：

```text
Career Agent
Multi-Agent
Memory
RAG
复杂 Workflow
```

JobLens 当前最重要的是先建立几个可信的基础能力：

```text
Job Import
Profile Extraction
Requirement Extraction
Match
```

只有这些 Workflow 稳定之后，Agent 才有工具可以调用。否则会变成：

```text
一个聊天框
+
几个还不可靠的 Prompt
```

---

## 4. 下一阶段的唯一 Ship Goal

未来几天只盯这个：

> **把一份真实的 JobLens Collector JSON 导入 JobLens-Agent，并在 Job Pool 页面看到真实岗位。**

完成标准：

- [ ] FastAPI 可以启动
- [ ] SQLite 自动初始化
- [ ] 可以上传 Collector JSON
- [ ] Job 正确入库
- [ ] 同一个文件导入两次不会制造大量重复数据
- [ ] 可以 GET 查询岗位
- [ ] 前端可以看到岗位列表
- [ ] 有基础自动测试
- [ ] README 写清楚如何启动
- [ ] 用你自己的真实 Collector 数据跑通一次

做完以后再进入 Profile。

---

## 5. 收尾原则

这会非常符合我们刚才确定的 Build-to-Learn 原则：

> **现在规划已经足够，下一步不是再学习或再设计，而是让第一个真实数据闭环跑起来。**

---

相关文档：

- [`../product/P0-1-job-data-foundation.md`](../product/P0-1-job-data-foundation.md) — P0-1 需求与验收
- [`../integration/COLLECTOR-CONTRACT.md`](../integration/COLLECTOR-CONTRACT.md) — Collector 接入契约
- [`../decisions/0002-backend-stack.md`](../decisions/0002-backend-stack.md) — 后端技术栈 ADR
- [`../roadmap/ROADMAP.md`](../roadmap/ROADMAP.md) — 全局路线图
