# JobLens Agent 系统架构

## 1. 架构目标

系统分为两个明确层次：

```text
Market Data Plane
负责：岗位事实

Career Intelligence Plane
负责：这些事实对当前用户意味着什么
```

---

## 2. 总体架构

```text
┌──────────────────────────────────────────────┐
│                JobLens Web                   │
│ Profile | Job Pool | Match | Gap | Prepare   │
└───────────────────┬──────────────────────────┘
                    │ HTTP
┌───────────────────▼──────────────────────────┐
│               Application API                │
│ Profile / Jobs / Targets / Reports / Actions │
└───────────┬──────────────────┬───────────────┘
            │                  │
            │                  │ Agent Run
            │         ┌────────▼──────────────┐
            │         │     Career Agent      │
            │         │  Single Agent + Tools │
            │         └────────┬──────────────┘
            │                  │
            │       ┌──────────┼────────────┐
            │       │          │            │
            │    Profile     Job/Market   Artifacts
            │     Tools        Tools        Tools
            │       │          │            │
┌───────────▼───────▼──────────▼────────────▼──┐
│                  Database                     │
│ Raw Jobs | Profiles | Evidence | Reports      │
└───────────────────▲───────────────────────────┘
                    │ import / sync
┌───────────────────┴───────────────────────────┐
│          JobLens Collector Extension          │
│ Search → Collect → Normalize → Export/Sync    │
└───────────────────▲───────────────────────────┘
                    │
                  BOSS
```

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

不负责：

- 判断用户是否适合岗位；
- 分析用户技能差距；
- 生成学习路线；
- 修改简历。

### apps/web

负责：

- Profile 确认和编辑；
- Job Pool；
- Match Reports；
- Job Target；
- Skill Gap；
- Job Preparation Pack。

### services/api

负责：

- 数据持久化；
- 领域规则；
- Job Import；
- CRUD；
- Agent Run 创建与结果保存。

### services/agent

负责：

- Career Agent Loop；
- Tool Registry；
- Context Builder；
- Structured Outputs；
- Trace；
- Eval。

Agent 必须通过 Tools 读取确定性数据，不直接绕过 API/Repository 随意修改数据库。

---

## 4. 核心数据关系

```text
UserProfile 1 ────── N Evidence
     │
     │ matched against
     ▼
    Job N ────────── 1 JobSource
     │
     ├────────────── N MatchReport
     │
     └──── selected by ─── JobTarget
                              │
                              ▼
                          SkillGap
                              │
                              ▼
                          ActionItem
```

---

## 5. Agent Runtime

MVP：单 Agent。

```text
User Goal
→ Context Builder
→ Career Agent
→ Tool Call
→ Tool Result
→ Structured Artifact
→ Validate
→ Persist
```

### Context 优先级

```text
P0 用户确认事实
P0 当前具体 Job / JobTarget
P1 相关 Evidence
P1 聚合市场统计
P2 历史 Agent Artifact
P3 一般职业知识
```

### 关键原则

LLM 的一般知识不能覆盖真实用户事实和真实 JD。

---

## 6. Matching Pipeline

建议不要把所有匹配逻辑一次性交给模型。

```text
Job Raw Data
→ Requirement Extraction
→ Deterministic Hard Filters
→ Profile Evidence Retrieval
→ LLM Semantic Match
→ Score Aggregation
→ MatchReport Validation
```

硬条件如：

- 城市；
- 薪资；
- 是否接受远程；
- 明确学历门槛；
- 明确必须年限。

优先用确定性代码判断。

技能同义和经验迁移等语义问题再交给 LLM。

---

## 7. 数据版本与可追踪

所有重要 Artifact 建议记录：

```text
source_profile_version
source_job_version
agent_version
prompt_version
model
created_at
```

避免用户更新简历后无法解释“为什么上周 80 分，这周 65 分”。

---

## 8. MVP 数据库建议

MVP 使用 SQLite，表建议：

```text
users
user_profiles
evidence
job_imports
jobs
job_sources
job_targets
job_target_jobs
match_reports
skill_gaps
action_items
preparation_packs
agent_runs
```

P1 再迁移 PostgreSQL。
