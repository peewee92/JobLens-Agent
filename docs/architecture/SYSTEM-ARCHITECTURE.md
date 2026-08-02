# JobLens Agent 系统架构

## 1. 架构目标

系统分为两个明确层次：

```text
Market Data Plane
负责：岗位事实（来自 Collector）

Career Intelligence Plane
负责：这些事实对当前用户意味着什么
```

MVP 阶段**不拆微服务**：一个 FastAPI 进程 + 一个 SQLite，内部按职责分层。代码逻辑分层，但部署形态是单体。详见 ADR-0002 / ADR-0003。

---

## 2. 总体架构（MVP：单体分层）

```text
┌──────────────────────────────────────────────┐
│                JobLens Web                   │
│ Profile | SearchIntent | Job Pool | Match    │
│ Ranking | UserFeedback | (v0.2) Gap/Prepare  │
└───────────────────┬──────────────────────────┘
                    │ HTTP
┌───────────────────▼──────────────────────────┐
│            Backend Application                │
│            (一个 FastAPI 进程)                │
│                                              │
│  ┌────────────────────────────────────────┐ │
│  │ api          路由 / 请求校验 / 响应      │ │
│  │ domain       领域模型与纯业务规则        │ │
│  │ application  用例编排（Workflow 调用）   │ │
│  │ repositories 持久化（SQLAlchemy）        │ │
│  │ llm         LLM Capability 封装         │ │
│  │ workflows   组合 Capability + 确定性代码 │ │
│  │ agent       Career Agent（P1 入口）      │ │
│  │ evals       各能力评测集与断言          │ │
│  │ tracing     统一 Trace 记录             │ │
│  └────────────────────────────────────────┘ │
│                    │                          │
│                    ▼                          │
│              SQLite（MVP）                    │
└───────────┬───────────────────────────────────┘
            │ import / sync
┌───────────▼──────────────────────────────────┐
│          JobLens Collector Extension          │
│ Search → Collect → Normalize → Export/Sync    │
└───────────────────▲───────────────────────────┘
                    │
                  BOSS
```

> 注意：`services/api` 与 `services/agent` 当前是占位目录。MVP 不把它们当成两个独立服务，重构为 `services/backend/app/{api,domain,...}` 与 **Phase 1（Job Data Foundation）** 一起完成（见 ROADMAP）。不要现在只为了“架构好看”空建 20 个目录。

---

## 3. 组件职责

### apps/collector-extension

只负责：

- 招聘网站搜索；
- 岗位卡片采集；
- 字体解码；
- 基础标准化；
- 去重；
- 详情补采；
- 导出或同步。

不负责：判断用户是否适合岗位、分析技能差距、生成学习路线、修改简历。

### apps/web

负责：

- Profile 确认和编辑；
- SearchIntent 定义；
- Job Pool；
- Match Reports / Ranking；
- UserFeedback；
- （v0.2）Target Cohort / Skill Gap / Preparation Pack。

### services/backend（单体应用）

一个 FastAPI 进程内的分层：

- `api`：HTTP 路由、请求/响应校验（用 Pydantic）；
- `domain`：领域实体、值对象、纯业务规则（如 Eligibility 判定逻辑）；
- `application`：用例编排，调用 workflow；
- `repositories`：持久化，SQLAlchemy；
- `llm`：对 LLM 的最小封装，产出结构化输出；
- `workflows`：组合 LLM Capability + 确定性代码，形成可复用能力（Profile / Requirement / Match / Ranking）；
- `agent`：Career Agent Runtime，P1 才作为统一用户入口；
- `evals`：每个 AI 能力的评测集与断言；
- `tracing`：统一 Trace 写入。

Agent 必须通过 workflow / repository 读取与写入，不直接绕过领域规则随意改库。

---

## 4. 核心数据关系

```text
UserProfile 1 ────── N Evidence
     │
     │ matched against
     ▼
    Job N ────────── 1 JobSource
     │
     ├────────────── N JobRequirement
     │
     ├────────────── 1 MatchReport（每 ProfileVersion）
     │
     └──── judged by ─── UserFeedback
                              │
                              ▼
                         TargetCohort（v0.2）
                              │
                              ▼
                          SkillGap（v0.2）
```

领域实体与关系见 [DOMAIN-MODEL.md](DOMAIN-MODEL.md)。

---

## 5. 核心执行链（v0.1 主链路）

```text
                    UserProfile
                         │
                    SearchIntent
                         │
                         ▼
Job → JobRequirement → Eligibility Gate
                         │
                         ▼
                  Evidence Retrieval
                         │
                         ▼
                   Semantic Match
                         │
                         ▼
                    MatchReport
                         │
                         ▼
                   UserFeedback
```

要点：

- `JobRequirement` 在 Match 之前抽取，是统一事实来源；
- `Eligibility Gate` 用确定性代码判定硬条件（城市 / 薪资下限 / 明确学历门槛 / 明确必须年限 / 远程），输出 `eligible` / `conditional` / `blocked`；
- `Evidence Retrieval` 从 UserProfile 拉相关 Evidence；
- `Semantic Match` 基于 Evidence 与 JobRequirement 产出 Fit（`strong` / `good` / `stretch` / `low`）与 `evidenceLinks`；
- `UserFeedback` 收回人类判断，进入 Eval 与 v0.2 的 Target Cohort。

---

## 6. Agent Runtime（P1 才作为入口）

v0.1 不要求用户直接面对 Agent。底层能力由 **LLM Capability → Domain Workflow → Career Agent** 三层组成（见 ADR-0004）：

```text
LLM Capability（最小可评估）
   Profile Extraction
   Requirement Extraction
   Semantic Match

Domain Workflow（组合 Capability + 确定性代码）
   JobRequirement Extraction
   Single Job Match
   Batch Ranking

Career Agent（P1 入口）
   编排成熟 Workflow，不直接实现业务能力
```

MVP 单体进程内的 Agent 模块只做：

```text
User Goal
→ Context Builder
→ Career Agent（P1）
→ Workflow Call
→ Structured Artifact
→ Validate
→ Persist
```

### Context 优先级

```text
P0 用户确认事实
P0 当前具体 Job / SearchIntent
P1 相关 Evidence
P1 聚合市场统计
P2 历史 Agent Artifact
P3 一般职业知识
```

### 关键原则

LLM 的一般知识不能覆盖真实用户事实和真实 JD。

---

## 7. Matching Pipeline

不要把所有匹配逻辑一次性交给模型。

```text
Job Raw Data
→ Requirement Extraction（→ JobRequirement）
→ Deterministic Eligibility Gate
→ Profile Evidence Retrieval
→ LLM Semantic Match
→ MatchReport Validation
```

硬条件（城市 / 薪资 / 远程 / 明确学历门槛 / 明确必须年限）优先用确定性代码判断；技能同义和经验迁移等语义问题再交给 LLM。

---

## 8. 数据版本与可追踪

所有重要 Artifact 记录：

```text
source_profile_version
source_job_version
job_requirement_extractor_version
agent_version
prompt_version
model
created_at
```

避免用户更新简历后无法解释“为什么上周 80 分，这周 65 分”。统一 Trace 结构见 [EVAL-AND-TRACE.md](EVAL-AND-TRACE.md)。

---

## 9. MVP 数据库建议

MVP 使用 SQLite（ADR-0003），表建议：

```text
users
user_profiles
evidence
search_intents
job_imports
job_import_items
job_import_candidates
jobs
job_sources
job_requirements
match_reports
user_feedbacks
job_targets          （v0.2 演化为 target_cohorts）
skill_gaps           （v0.2）
action_items         （v0.2）
preparation_packs    （v0.2）
agent_runs
eval_runs
trace_spans
```

P1 再迁移 PostgreSQL（同一 SQLAlchemy 模型，仅换 engine）。Job / JobSource / JobImportItem 的身份与来源边界见 ADR-0007；Candidate 审计证据持久化见 ADR-0013。
