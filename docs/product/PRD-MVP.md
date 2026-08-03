# JobLens Agent MVP 产品需求文档

- 状态：v2.0（与 ROADMAP Phase 0.5+ / SYSTEM-ARCHITECTURE / DOMAIN-MODEL / ADR-0001..0005 对齐）
- 目标版本：MVP v0.1（首个可运行闭环）→ MVP v0.2 → P1
- 产品定位：基于真实岗位市场数据的个人求职与职业转型 Agent
- 关联文档：[路线图](roadmap/ROADMAP.md) · [系统架构](architecture/SYSTEM-ARCHITECTURE.md) · [领域模型](architecture/DOMAIN-MODEL.md) · [评估与追踪](architecture/EVAL-AND-TRACE.md) · [Collector 接入契约](integration/COLLECTOR-CONTRACT.md) · [MVP 范围决策](decisions/0001-mvp-scope.md)

## 1. 背景与问题

现有求职 AI 工具大多停留在三个孤立场景：简历润色、岗位推荐、模拟面试。它们普遍缺少一个关键闭环：**用户的真实能力与真实招聘市场之间没有持续连接**。

用户真正面对的问题不是“帮我生成一份更漂亮的简历”，而是：

- 我现在到底适合什么岗位？
- 我感兴趣的岗位，市场真实要求是什么？
- 我与目标岗位的差距在哪里？
- 哪些差距最值得优先补？
- 学完或完成项目后，如何形成可写进简历的证据？
- 对一个具体岗位，我应该怎么改简历和准备面试？

JobLens 已有的岗位筛选浏览器插件解决了“真实岗位从哪里来”的问题。JobLens Agent 在此基础上解决“这些岗位对我意味着什么、我下一步应该做什么”的问题。

---

## 1.1 MVP 范围边界（先读这一节）

### MVP 不是一次性做完所有事

我们把 MVP 拆成两个可独立交付的版本，外加一个 P1 收口：

```text
MVP v0.1（首个可运行闭环）
Profile
→ SearchIntent
→ Job Pool
→ JobRequirement
→ Eligibility
→ Match
→ Ranking
→ UserFeedback

MVP v0.2（从岗位反推学习路线与准备）
Target Cohort
→ Skill Gap
→ Action Plan
→ Resume / Interview

P1（让 Agent 编排成熟能力）
Career Agent
→ 调用成熟 Workflow
```

v0.1 的价值主张很窄但很硬：

> **基于我的真实经历和一批真实目标岗位，告诉我哪些岗位最值得优先投，以及为什么。**

v0.2 再回答“缺什么、怎么补、怎么改简历、怎么面试”。P1 才让 Career Agent 成为面向用户的统一入口，去编排 v0.1 / v0.2 已经稳定下来的 Workflow。

### MVP v0.1 明确不做（详见 ADR-0001 / 0001-mvp-scope）

- 完整职业发现（用户自己已有大致方向）
- 长期课程系统
- 自动投递 / 自动打招呼
- Multi-Agent
- 复杂 Memory
- 跨平台自动采集

### v0.2 / P1 才做

- Skill Gap / Action Plan（v0.2）
- Resume Delta / Interview Pack（v0.2）
- Career Agent 统一入口（P1）

完整“暂不做 vs 永远不做”见 §10 与 ADR-0001。

---

## 2. 产品目标

### 2.1 MVP v0.1 核心目标

把最短、最可验证的闭环打通：

```text
用户真实经历
→ UserProfile
→ SearchIntent
→ 真实岗位池
→ 每个岗位的 JobRequirement
→ Eligibility Gate
→ 语义 Match
→ 批量 Ranking
→ UserFeedback
```

数字分数只用于内部排序，**不被解释为概率**，也不单独展示给用户。

### 2.2 MVP v0.1 成功标准

一个用户能够在一次完整流程中：

1. 导入自己的简历或结构化经历，得到带 Evidence 的 `UserProfile`；
2. 定义 `SearchIntent`（目标角色、城市、薪资下限、硬约束等）；
3. 导入 JobLens Collector 采集的岗位 JSON，形成 `Job Pool`；
4. 系统为每个岗位抽取结构化 `JobRequirement`；
5. 看到每个岗位的 `Eligibility`（Eligible / Conditional / Blocked）与 `Fit`（Strong / Good / Stretch / Low）；
6. 看到按推荐等级排序的岗位列表，每条都可追溯到 Profile Evidence 或 Job Requirement；
7. 对岗位给出 `UserFeedback`（值得投 / 可以考虑 / 不适合）及原因。

---

## 3. 目标用户

### Primary Persona：主动求职 / 转型中的有经验候选人

> 有 **3～10 年工作经验**，有现成简历，已有 **1～3 个大致目标方向**，正在主动求职或职业转型的人。

特征：

- 不是应届生，也不是完全没方向的探索者；
- 已经有简历和项目经历，痛点不是“写不出简历”，而是“不知道哪些岗位真的值得投、为什么”；
- 会自己收集岗位（BOSS / 猎聘 / 内推），但逐条读 JD、手工比对、定制简历成本高；
- 想要一个能引用真实经历和真实 JD 的判断，而不是泛泛的职业建议。

> 设计取舍：早期版本**不服务**“完全不知道自己要做什么”的职业探索场景，也不服务“需要系统帮我从零规划职业”的用户。这两类需要完整的职业发现能力，属于 MVP v0.1 明确不做项。

---

## 4. 核心价值主张

### 4.1 MVP v0.1 核心价值（一句话）

> **基于我的真实经历和一批真实目标岗位，告诉我哪些岗位最值得优先投，以及为什么。**

它必须回答的不是“我适合什么、缺什么、怎么学、怎么改简历、怎么面试”（那是 v0.2 以后的事），而是更前置、更可证伪的一步：

> 在我导入的这批真实岗位里，哪些最值得我现在就投？理由能不能引用我的真实经历或真实 JD？

### 4.2 基于真实岗位，而不是泛泛职业建议

系统的推荐必须能回答：

> 为什么推荐这个岗位？它匹配了我经历里的哪一条证据，或命中了 JD 里的哪一条要求？

### 4.3 基于证据，而不是模型拍脑袋

- “用户会某个技能”必须关联到经历、项目和结果证据（`Evidence`）；
- “岗位要求某能力”必须关联到具体 JD 文本（`JobRequirement.evidenceSpan`）；
- 任何推荐都可通过 `UserProfile` 或 `JobRequirement` 追溯到来源（见 EVAL-AND-TRACE）。

### 4.4 从岗位判断，回到能力事实

v0.1 先把“哪些岗位值得投”做扎实。`JobRequirement` 成为后续 `Match` / `Gap` / `Resume` / `Interview` 统一的事实基础——这也是为什么 `Requirement Intelligence` 被单独提升为一个阶段（ROADMAP Phase 3），而不是 Match 内部的一个步骤。

---

## 5. MVP 功能范围

## 5.1 Career Profile｜我的职业画像（v0.1）

### 输入

- 简历文本 / PDF 解析后的文本；
- 用户手动补充项目和职业偏好；
- 用户确认 / 修正的 `Evidence`。

### 输出

结构化 `UserProfile`（Schema：`user-profile.schema.json`）：

- 基础工作年限；
- 技能（必须关联 `evidenceIds`，禁止只存“React：熟练”这类无证据标签）；
- 项目；
- 行业与业务领域；
- 可迁移优势；
- `Evidence` 列表。

职业偏好不再重复内嵌于 UserProfile，由独立版本化 `SearchIntent` 作为唯一事实来源。

### 关键要求

技能尽量绑定证据：

```text
React
├── 8 年经验
├── 项目 A
└── 复杂业务结果
```

无证据的能力标签是 v0.1 必须避免的（见 P1 的 `user-profile.schema.json` 增强：`ProfileFact` / `Evidence` / `CapabilityAssessment`）。当前手工确认闭环已实现；简历/LLM 抽取只能生成“待确认提案”，不能直接写入已确认 Profile。

---

## 5.2 SearchIntent｜求职意向（v0.1，新增）

`SearchIntent` 是 `UserProfile` 之后、`Job Pool` 之前的独立环节。它把“用户想找什么”从零散偏好变成可计算、可复现的约束。

### 字段（Schema：`search-intent.schema.json`）

- `targetRoles`：目标角色列表；
- `cities`：目标城市；
- `remoteAccepted`：是否接受远程；
- `minimumSalaryK`：薪资下限（千）；
- `seniority`：级别（如 junior / mid / senior / staff）；
- `employmentTypes`：全职 / 兼职 / 实习等；
- `excludeKeywords`：排除关键词；
- `hardConstraints`：硬约束（确定性 Eligibility 判定用）；
- `softPreferences`：软偏好（排序加权用，不打分强制）。

### 作用

`SearchIntent` 同时驱动：

- `Eligibility Gate`（硬约束做确定性判定）；
- `Ranking`（软偏好参与排序）；
- Collector 复现分析（快照随导入批次保存，见 COLLECTOR-CONTRACT）。

---

## 5.3 Job Pool｜我的岗位池（v0.1）

### 数据来源

```text
JobLens Collector JSON
→ 手动上传/导入
→ JobLens Agent API
```

P1 再改成浏览器插件直接 POST API（见 ROADMAP Phase 9 / COLLECTOR-CONTRACT §5）。

### 能力

- 导入 report JSON；
- 保留原始岗位字段（`sourceRaw`）；
- 标准化薪资、城市、远程、技能、JD；
- 基于 URL + 公司 + 标题去重；
- 查询、筛选、收藏、忽略。

详细 FR / BR / API / 数据模型 / 错误处理 / 兼容策略 / 验收标准见 `P0-1-job-data-foundation.md`。

---

## 5.4 JobRequirement｜岗位需求抽取（v0.1，新增，核心）

每个岗位在进入 Match 之前，先抽成结构化 `JobRequirement`（Schema：`job-requirement.schema.json`）。这是 v0.1 最重要的新增模型。

### 抽取链路

```text
Job
→ Requirement Extraction（LLM Structured Output）
→ JobRequirement
→ Match
```

### 字段要点

- `id` / `jobId` / `originalText`；
- `type`：`skill` / `experience` / `education` / `responsibility` / `domain` / `constraint`；
- `normalizedCapability`：归一化后的能力名（用于同义归一、跨岗位聚合）；
- `importance`：`must_have` / `preferred` / `bonus`；
- `evidenceSpan`：命中 JD 原文的片段（可追溯）；
- `confidence`：抽取置信度；
- `extractorVersion`：抽取器版本（可复现）。

### 为什么重要

`JobRequirement` 是 `Match` / `Gap` / `Prepare` 的**统一事实来源**（见 ADR-0004 与 DOMAIN-MODEL）。v0.1 先让它服务于 `Match` 和 `Eligibility`；v0.2 的 `Skill Gap` 与 `Prepare` 直接复用，不需要重新读 JD。

---

## 5.5 Match｜岗位匹配（v0.1，重定义）

v0.1 **不再把固定 100 分权重作为核心规则**。匹配结果由两层组成，数字只用于内部排序。

### Eligibility（确定性 / 半确定性）

```text
Eligibility
├── Eligible      硬性条件全部满足
├── Conditional   有硬条件需人工确认（如“经验 3-5 年，你有 2.5 年”）
└── Blocked       明确不满足硬约束（城市 / 学历 / 年限硬门槛）
```

优先用确定性代码判定（城市、薪资下限、明确学历门槛、明确必须年限、远程要求）。

### Fit（语义匹配）

```text
Fit
├── Strong     强匹配
├── Good       良好
├── Stretch    有差距但可冲刺
└── Low        弱匹配
```

基于 `Profile Evidence` 与 `JobRequirement` 的语义匹配，输出可解释理由与证据链接。

### 输出 `MatchReport`（v0.1 字段）

- `eligibility`：`eligible` / `conditional` / `blocked`
- `blockedReasons`：被 Blocked 的原因
- `recommendation`：`strong` / `good` / `stretch` / `low` / `blocked`
- `matchedRequirementIds`：命中的 JobRequirement id
- `missingRequirementIds`：缺失的 JobRequirement id（尤其 `must_have`）
- `evidenceLinks`：到 `UserProfile` Evidence 或 `JobRequirement.evidenceSpan` 的链接
- `score`（可选，仅内部排序，不解释为概率）

完整字段演进见 P1 的 `match-report.schema.json` 增强。

---

## 5.6 Ranking｜批量排序（v0.1）

基于 `Eligibility` + `Fit` + `SearchIntent.softPreferences` 对 `Job Pool` 批量排序：

- Blocked 沉底或默认隐藏；
- Eligible 内按 Fit 与软偏好综合排序；
- 数字 `score` 仅用于排序，不单独展示为“87%”。

---

## 5.7 UserFeedback｜用户反馈（v0.1，新增）

排序之后必须收回人类判断，形成可评估、可改进的闭环。

### 决策（Schema：`user-feedback.schema.json`）

```text
值得投     interested
可以考虑   maybe
不适合     rejected
```

### 字段要点

- `jobId` / `profileVersion` / `matchReportId`；
- `decision`：`interested` / `maybe` / `rejected`；
- `reasons`：反馈原因（结构化标签 + 自由文本）；
- `comment`：用户备注；
- `createdAt`。

### 作用

- 作为 `Match Eval` 的人工基准（见 EVAL-AND-TRACE）；
- 作为 v0.2 `Target Cohort` 的来源之一（`createdFromFeedback`）；
- 让“模型推荐”与“真人判断”可被一起评测，而不是各自为政。

---

## 5.8 v0.2 才做的：Target Cohort / Skill Gap / Preparation

以下属于 MVP v0.2，不在 v0.1 范围：

- `Target Cohort`：由收藏岗位、或 `UserFeedback` 聚合出的目标岗位集（概念演进见 `job-target.schema.json` → `TargetCohort`）；
- `Skill Gap`：基于 `JobRequirement` 聚合，优先级不单看频率（见 P1 `skill-gap.schema.json`：`targetCoverage` / `mustHaveRatio` / `evidenceCoverage` / `gapSeverity`）；
- `Action Plan`：最多 3 个 P0 / 5 个 P1；
- `Resume Delta` / `Interview Pack`：单岗位简历调整建议与面试准备清单。

---

## 6. 核心用户流程

### Flow A：从“我是谁 + 我想找什么”到“哪些岗位值得投”（v0.1 主链路）

```text
导入简历
→ Profile Extraction
→ 用户确认 Evidence
→ Define SearchIntent
→ 导入岗位（Job Pool）
→ Requirement Extraction（每岗 JobRequirement）
→ Eligibility Gate
→ Semantic Match
→ 批量 Ranking
→ UserFeedback
```

### Flow B：从目标岗位集反推学习路线（v0.2）

```text
Target Cohort（收藏岗位 / UserFeedback 聚合）
→ Requirement Aggregation（复用 JobRequirement）
→ Profile Comparison
→ Skill Gap
→ P0/P1 Action Plan
```

### Flow C：准备一个具体岗位（v0.2）

```text
打开岗位
→ 查看 Match Report
→ 点击“为这个岗位准备”
→ Resume Advice
→ Project Story
→ Interview Checklist
```

---

## 7. Agent 设计

MVP v0.1 不要求用户直接面对 Agent。底层能力由 **LLM Capability → Domain Workflow → Career Agent** 三层组成（见 ADR-0004）：

```text
LLM Capability（最小可评估的 LLM 能力）
   Profile Extraction
   Requirement Extraction
   Semantic Match

Domain Workflow（组合 Capability + 确定性代码）
   JobRequirement Extraction
   Single Job Match
   Batch Ranking

Career Agent（P1 才作为统一入口）
   编排成熟 Workflow，不直接实现业务能力
```

### v0.1 可用 Tools（供 Workflow 调用，不是业务全在 Agent 里）

- `get_user_profile`
- `get_search_intent`
- `list_jobs`
- `get_job`
- `get_job_requirement`
- `run_eligibility`
- `match_job`
- `rank_jobs`
- `save_user_feedback`

### Agent 不负责

- 直接写数据库；
- 修改原始采集数据；
- 自动申请岗位；
- 绕过确定性业务规则（Eligibility 必须由代码判定，Agent 不能推翻）；
- 在 v0.1 充当统一用户入口（那是 P1）。

---

## 8. 核心数据模型

v0.1 以七个模型为主：

```text
UserProfile
SearchIntent
Job
JobRequirement
MatchReport
UserFeedback
（JobTarget / TargetCohort 在 v0.2 引入）
```

并辅以：

```text
Evidence
```

JSON Schema 位于：`packages/contracts/schemas/`，当前包含：

- `user-profile.schema.json`
- `job.schema.json`
- `search-intent.schema.json`（新增）
- `job-requirement.schema.json`（新增，最重要）
- `user-feedback.schema.json`（新增）
- `job-target.schema.json`（v0.2 演化为 TargetCohort）
- `skill-gap.schema.json`（v0.2）
- `match-report.schema.json`（v0.1 字段已落地，P1 增强 `eligibility` / `evidenceLinks` 等）

关系图见 `DOMAIN-MODEL.md`。

---

## 9. 非功能需求

### 可解释

所有关键职业判断必须尽量带 `evidence` 与 `evidenceLinks`。

### 可追踪

记录：

- 模型版本；
- Prompt / Extractor 版本；
- 输入 Profile 版本；
- Job / JobRequirement 版本；
- 输出 Artifact。

统一 Trace 结构见 `EVAL-AND-TRACE.md`。

### 可评估（Eval 是横切要求，不是最后一个 Phase）

每个 AI 能力都必须从第一天起配套 Eval：

```text
Profile Extraction  → Profile Eval
Requirement Extraction → Requirement Eval
Match              → Match Eval
（P1）Agent        → Agent Eval
```

至少建立：

- 10 条 Profile Extraction 测试；
- 20 条 Job Match 测试；
- 10 条 Requirement Extraction 测试；
- UserFeedback 作为 Match 人工基准集。

### 隐私

简历和个人经历默认本地存储；未经用户操作，不对外分享。

---

## 10. 明确不做

MVP v0.1 **明确暂不做**（不是永远不做；多平台 / 成长闭环 / 产品扩展见 ROADMAP Phase 7–9）：

- 自动投递；
- 自动 Boss 打招呼；
- Multi-Agent；
- 语音模拟面试；
- Offer 比较；
- 全网岗位爬虫；
- 复杂在线课程；
- 完整职业发现（用户无方向时的探索）；
- 长期课程系统；
- 复杂 Memory；
- 跨平台自动采集。

v0.2 / P1 才重启的能力（不在 v0.1）：Skill Gap、Action Plan、Resume Delta、Interview Pack、Career Agent 统一入口、GitHub 项目解析、多简历版本、定时更新与提醒、面试复盘、Offer 比较。

---

## 11. MVP v0.1 验收清单

### Profile

- [ ] 用户可导入一份简历文本并得到结构化画像
- [ ] 用户可以修改错误的技能和经历
- [ ] 核心技能至少关联一个 Evidence 或明确标记“缺少证据”

### SearchIntent

- [ ] 用户可定义目标角色 / 城市 / 薪资下限 / 硬约束 / 软偏好
- [ ] SearchIntent 快照随导入批次保存，可用于复现分析

### Jobs

- [ ] 可导入 Collector v1.3.1 report JSON
- [ ] 可查看最终岗位与候选岗位
- [ ] 重复导入不会产生大量重复岗位

### JobRequirement

- [ ] 每个岗位产出结构化 JobRequirement
- [ ] 每条 Requirement 有 `type` / `importance` / `evidenceSpan` / `confidence`

### Match

- [ ] 每个岗位有 Eligibility（Eligible / Conditional / Blocked）
- [ ] 每个岗位有 Fit（Strong / Good / Stretch / Low）
- [ ] 报告可追溯到 Profile Evidence 或 Job Requirement
- [ ] `score` 仅用于内部排序，未作为概率展示

### Ranking + Feedback

- [ ] 可按 Eligibility + Fit + 软偏好批量排序
- [ ] 用户可对岗位给出 interested / maybe / rejected 及原因
- [ ] 反馈可回查到对应 MatchReport

---

## 12. 首推开发顺序（落地起点）

严格按以下顺序开发，先形成第一个真实闭环，再扩展：

1. **Job Data Foundation（第一个基础设施节点）**
   - 实现 `POST /api/v1/job-imports`；
   - 把浏览器插件导出的 `boss-job-filter-report-v1.3.1-*.json` 真正导入系统；
   - 闭环变为：`BOSS → JobLens Collector → 导出 JSON → JobLens Agent → 我的岗位池`；
   - 详见 `P0-1-job-data-foundation.md` 与 ROADMAP Phase 1。

2. **UserProfile + SearchIntent + 单岗位 Match（第一个可演示 Agent）**
   - 上传真实经历 → 生成带 Evidence 的 UserProfile；
   - 定义 SearchIntent；
   - 导入刚从 BOSS 采集的真实岗位；
   - 抽取 JobRequirement → Eligibility → Match；
   - 用户给出 UserFeedback；
   - 对应 ROADMAP Phase 2–5。

> 不要先做漂亮 Dashboard，也不要先做 Multi-Agent。先把上面两步跑通，且从第一个 LLM Pipeline 就接 Eval（见 ADR-0005）。
