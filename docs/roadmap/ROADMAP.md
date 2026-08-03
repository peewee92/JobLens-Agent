# JobLens Agent 路线图

## 总目标

用最小工程成本打通：

```text
Profile → SearchIntent → JobRequirement → Eligibility → Match → Ranking → UserFeedback
```

路线图强调先形成可验证闭环，再增加能力广度与平台规模。**Eval 从 Phase 1 就介入，不是最后一个 Phase。**

领域模型、阶段边界与关键决策见：
- [领域模型](architecture/DOMAIN-MODEL.md)
- [系统架构](architecture/SYSTEM-ARCHITECTURE.md)
- [评估与追踪](architecture/EVAL-AND-TRACE.md)
- [MVP 范围决策](decisions/0001-mvp-scope.md)
- [后端技术栈](decisions/0002-backend-stack.md)
- [数据库策略](decisions/0003-database-strategy.md)
- [LLM / Workflow / Agent 边界](decisions/0004-llm-workflow-agent-boundary.md)
- [Eval 从第一天开始](decisions/0005-eval-from-day-one.md)

---

# Phase 0.5｜产品与领域模型冻结（P0，概念基线）

目标：在写第一行业务逻辑前，先把**产品定义、领域模型、阶段边界、架构边界**冻结。

### 为什么有这个 Phase

早期最容易失控的是“文档无限扩张但无工程证据”。Phase 0.5 只做三件事：

1. 收缩 Primary Persona（有 3–10 年经验、有简历、有 1–3 个目标方向、主动求职/转型）；
2. 冻结领域模型（`UserProfile` / `SearchIntent` / `Job` / `JobRequirement` / `MatchReport` / `UserFeedback` / `TargetCohort` / `SkillGap`）；
3. 冻结阶段边界与后端边界（单 FastAPI 进程 + 分层，不拆微服务；LLM Capability → Domain Workflow → Career Agent）。

### 交付

- [x] MVP PRD v2.0（单 Persona、两阶段 MVP、JobRequirement、UserFeedback、Eligibility+Fit）
- [x] 领域模型 `DOMAIN-MODEL.md`
- [x] 系统架构 `SYSTEM-ARCHITECTURE.md`（单后端应用 + 新执行链）
- [x] Collector 导入契约
- [x] 核心领域 Schema（含 3 个新增：`search-intent` / `job-requirement` / `user-feedback`）
- [x] ADR-0001..0005

### 完成标准

开发者进入仓库后，可以直接回答：

- 系统解决什么问题、不解决什么；
- 第一阶段只做哪 8 步（v0.1）；
- Collector 与 Agent 如何分工；
- 第一批 API 和数据模型是什么；
- 不需要理解整个 JobLens 长期愿景就能开工。

---

# Phase 1｜Job Data Foundation（P0）

对应需求文档：`P0-1-job-data-foundation.md`

建议周期：2–3 天

目标：不依赖手工 CSV 分析，把已有 Collector 的 JSON 正式导入系统，形成可靠的 `Job Pool`。

### 任务

1. 单个 FastAPI 进程（非微服务，见 ADR-0002 / 0003）；
2. SQLite 数据库；
3. `POST /api/v1/job-imports`；
4. 解析 Collector report：`jobs` / `candidates` / `statistics` / `config`；
5. Job 标准化与去重（canonical key）；
6. Job Pool 查询接口；
7. 保存 `sourceRaw`，避免数据不可追溯；
8. 导入批次记录：`Import Batch` / `Source Snapshot` / `Collector Version` / `Collected At` / `SearchIntent Snapshot`（见 COLLECTOR-CONTRACT）。

### 验收

- 同一 JSON 重复导入两次，Job 数量基本不增加；
- 可以按城市、薪资、关键词查看岗位；
- 可以打开原始 BOSS URL；
- 能回答“这批岗位里 Python 比例为什么这么高”（需保存搜索关键词 / 城市 / 时间 / Collector 版本）。

> 这一阶段**只做数据地基**，不碰 Match / Profile LLM。做完即可作为第一个可独立验收的节点。

---

# Phase 2｜Profile + SearchIntent（P0）

建议周期：3–5 天

目标：建立个人事实底座与“我想找什么”的明确约束。

### 任务

1. 简历文本输入；
2. LLM Structured Output → `UserProfile`（带 `Evidence`）；
3. Evidence 抽取与用户确认；
4. Profile Version；
5. `SearchIntent` 定义（目标角色 / 城市 / 远程 / 薪资下限 / 级别 / 硬约束 / 软偏好）；
6. `Profile Eval` 数据集与断言（从第一个 LLM Pipeline 开始，见 ADR-0005）。

### 当前进度（2026-08-03）

- 手工确认的 Profile + Evidence + Skill 链接已完成；
- Profile/SearchIntent 不可变版本、`expectedVersion` 冲突保护、API 与 Web 编辑闭环已完成；
- Resume Text → Profile Proposal、strict Structured Output、evidenceSpan/reference 门禁、Trace 0004 和 10-case Profile Eval 已完成；
- PDF/DOCX 文本摄取、文件隐私边界与 Web 上传已完成；Eval Run/Case Result、`profile-eval-gate-v1`、baseline 对比、人工 accept/reject Review、正式 accepted baseline 与 Eval Review Web 已完成；下一步是带真实凭据的 Provider Eval 和人工质量结论。Fixture 通过仍不代表生产模型质量。

### 验收

Profile 页面可以明确区分：

- 我真的做过；
- 我了解但缺少项目证据；
- 我完全没有。

`SearchIntent` 可保存为快照并与导入批次关联。

---

# Phase 3｜Requirement Intelligence（P0，核心新增）

目标：`JobRequirement` 成为 `Match` / `Gap` / `Prepare` 的**统一事实基础**。

### 为什么单独成 Phase

过去 Requirement Extraction 只是 Match 内部一步。现在它被提升为独立能力，因为：

- `Match` 需要它对每条 JD 要求结构化；
- v0.2 的 `Skill Gap` 直接复用它做需求聚合，不必回读 JD；
- `Resume` / `Interview` 的准备也基于它定位差距。

### 任务

1. JD → `JobRequirement`（LLM Structured Output）；
2. `type` 分类：`skill` / `experience` / `education` / `responsibility` / `domain` / `constraint`；
3. `normalizedCapability` 归一化；
4. `importance`：`must_have` / `preferred` / `bonus`；
5. `evidenceSpan` 命中 JD 原文；
6. `confidence` / `extractorVersion`；
7. `Requirement Eval` 数据集与断言。

### 当前进度（2026-08-03）

- `JobRequirementExtraction` 与逐条 `JobRequirement` 已按不可变版本持久化；
- strict Structured Output Adapter、exact `originalText/evidenceSpan` 门禁与 Requirement Trace 已完成；
- POST 抽取、GET 最新版本、GET 历史版本 API 已完成；
- 10-case 脱敏 Requirement Eval、Fixture Gate、失败案例解释和独立 CLI 已完成；
- Job 详情页可显式触发新版本并展示 Requirement ID、importance、evidenceSpan、confidence 与 Trace；
- 尚未完成真实 Provider 评测、20 个真实岗位人工验收和 Requirement 人工 Review，因此不能将 Fixture 结果视为生产质量结论，也不进入 Match。

### 验收

抽样 20 个岗位，人工检查：

- `must_have` 与 `bonus` 区分合理；
- `evidenceSpan` 能精确指向 JD 原文；
- 同义能力已归一（如 “React.js” / “ReactJS” → “React”）。

---

# Phase 4｜Single Job Match（P0，核心）

建议周期：5–7 天

目标：让单个岗位判断“是否值得投、为什么”可信、可解释。

### 任务

1. `Eligibility Gate`（确定性 / 半确定性硬条件判定）；
2. `Evidence Retrieval`（从 UserProfile 拉相关 Evidence）；
3. `Semantic Match`（LLM，基于 Evidence 与 JobRequirement）；
4. `MatchReport` Structured Output（`eligibility` / `recommendation` / `matchedRequirementIds` / `missingRequirementIds` / `evidenceLinks`）；
5. 推荐等级：`strong` / `good` / `stretch` / `low` / `blocked`；
6. `Match Eval` 数据集与断言（含 UserFeedback 作为人工基准）。

### 验收

至少选 20 个真实岗位人工评审：

- Top 推荐是否大体合理；
- 推荐理由是否能引用真实经历；
- 不匹配原因是否能引用 JD / JobRequirement；
- 数字 `score` 未被当作概率展示。

---

# Phase 5｜Batch Ranking + UserFeedback（P0）

建议周期：3–4 天

目标：从“单个岗位判断”到“一批岗位排序 + 人类反馈闭环”。

### 任务

1. 批量 Match 队列；
2. Ranking（Eligibility + Fit + SearchIntent.softPreferences）；
3. Blocked 沉底 / 默认隐藏；
4. `UserFeedback` 采集（interested / maybe / rejected + reasons）；
5. 反馈回查到 MatchReport；
6. 反馈作为 `Match Eval` 基准与 v0.2 `Target Cohort` 来源。

### 验收

- 可批量匹配至少 50 个岗位；
- 可按推荐等级排序；
- 用户反馈可回查；
- 反馈数据落库，可进入 Eval 统计。

> 到 Phase 5 结束，MVP v0.1 闭环完成。此时即可独立演示与评测，不必等 v0.2。

---

# Phase 6｜Target Cohort + Skill Gap（v0.2）

建议周期：4–6 天

目标：把岗位池变成用户自己的学习路线，而不是通用课程。

### 任务

1. 创建 `Target Cohort`（收藏岗位 / UserFeedback 聚合，概念从 `JobTarget` 演进）；
2. 复用 `JobRequirement` 聚合需求；
3. 归一化同义技能；
4. 市场要求 vs Profile；
5. 生成 `SkillGap`：优先级不单看频率，引入 `targetCoverage` / `mustHaveRatio` / `evidenceCoverage` / `gapSeverity`；
6. 生成 P0/P1 Action Plan；
7. 每项建议关联 `supportingRequirementIds`。

### 验收

用户点击任一 Gap，可以看到：

```text
为什么重要
哪些岗位要求（JobRequirement）
我当前有什么证据
具体缺什么
做到什么算补齐
```

---

# Phase 7｜Job Preparation（v0.2）

建议周期：3–5 天

目标：让分析直接服务于投递和面试。

### MVP 交付

- Resume Delta（简历调整建议，非整份重写）；
- 项目排序建议；
- STAR / 项目讲述重点；
- 预计面试问题；
- 面试前补习清单。

### 验收

所有建议只能使用 UserProfile 中已存在的事实，不得虚构项目和成绩。

---

# Phase 8｜Career Agent（P1）

目标：让 `Career Agent` 成为面向用户的统一入口，去**编排**已经成熟的 Workflow（Profile / SearchIntent / Requirement / Match / Ranking / Gap / Prepare）。

### 关键边界（ADR-0004）

- Agent 不直接实现业务能力；
- Agent 组合稳定 Workflow；
- 所有业务事实仍来自 `JobRequirement` 等统一模型；
- 多 Agent 不进入本期。

### 任务

- 统一对话入口；
- Tool Registry（复用 Workflow 能力，不是把业务全写成 Agent Tool）；
- Context Builder（P0 用户确认事实 / 当前 Job，P1 相关 Evidence）；
- `Agent Eval`。

---

# Phase 9｜Growth Loop / Collector Sync（P1）

目标：形成真正的 `Gap → Action → Evidence → Re-match`，并从“下载 JSON → 上传”升级为一键同步。

### 任务

- ActionItem 状态；
- 学习 / 项目 Evidence 录入；
- Profile 更新与重新匹配；
- Collector API 同步（插件 POST Agent API，增量导入，保留 JSON 兜底）；
- “补完这个能力后影响了哪些岗位”对比；
- 新岗位提醒 / 定时更新（价值验证后再做）。

---

# 当前最推荐的开发顺序

```text
Phase 0.5  产品与领域基线（本文档 + PRD v2.0 + DOMAIN-MODEL + ADR）
Phase 1    Job Data Foundation（POST /api/v1/job-imports）
Phase 2    Profile + SearchIntent
Phase 3    Requirement Intelligence（JobRequirement）
Phase 4    Single Job Match（Eligibility + Fit）
Phase 5    Batch Ranking + UserFeedback
--- v0.1 闭环完成，可独立演示与评测 ---
Phase 6    Target Cohort + Skill Gap
Phase 7    Job Preparation
Phase 8    Career Agent
Phase 9    Growth Loop / Collector Sync
```

不要先做漂亮 Dashboard，也不要先做 Multi-Agent。先把 Phase 1–5 跑通，且每个 LLM Pipeline 从第一天接 Eval。
