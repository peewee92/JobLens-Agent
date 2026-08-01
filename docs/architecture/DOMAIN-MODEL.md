# JobLens Agent 领域模型

> 本文档是领域模型的单一事实来源（single source of truth），不塞进 SYSTEM-ARCHITECTURE。架构、流程与边界见 [SYSTEM-ARCHITECTURE.md](SYSTEM-ARCHITECTURE.md)；Eval 与 Trace 见 [EVAL-AND-TRACE.md](EVAL-AND-TRACE.md)。

## 1. 核心实体

### UserProfile

用户的事实底座。由简历/经历抽取，经用户确认。

- 关键约束：**技能必须关联 Evidence**，禁止只存“React：熟练”这类无证据标签（v0.1 起步即遵守，P1 进一步拆为 `ProfileFact` / `Evidence` / `CapabilityAssessment`）。
- 关联：`Evidence`（1—N）。

### Evidence

支撑“用户会某能力 / 做过某事”的事实条目。

- 类型：`work` / `project` / `education` / `achievement` / `self_report`。
- 被 UserProfile 的技能、MatchReport 的 `evidenceLinks` 引用。

### SearchIntent

“用户想找什么”的明确、可计算约束。

- 字段见 `search-intent.schema.json`：`targetRoles` / `cities` / `remoteAccepted` / `minimumSalaryK` / `seniority` / `employmentTypes` / `excludeKeywords` / `hardConstraints` / `softPreferences`。
- 作用：驱动 `Eligibility` 硬判定、`Ranking` 软加权、Collector 复现分析快照。

### Job

JobLens 内部统一、稳定的岗位实体，保存用于查询、匹配和排序的标准化当前状态。

- `id` 是 JobLens internal Job ID，不是 Collector / 招聘网站的外部岗位 ID；
- 远程事实采用 `remoteStatus: confirmed | rejected | unknown`，并保留 `remoteConfidence`；
- 数据库内部持久化 `canonicalKey` / `canonicalKeyVersion` 用于幂等去重，但不进入公共 Job Contract；
- 对外字段见 `job.schema.json`；
- 一个 Job 可以关联多个 `JobSource`，并对应多个 `JobRequirement`（1—N）。

### JobSource

某个外部来源对 Job 的来源记录和原始证据。

- 保存 `source` / `sourceJobId` / `sourceUrl` / `sourceVersion` / `sourceRaw`；
- 保存 `firstSeenAt` / `lastSeenAt` / `collectedAt`；
- `sourceJobId` 只在具体 `source` 内有意义，不能作为 `Job.id`；
- `sourceRaw` 属于 JobSource，普通 Job API 默认不返回；
- JobSource 表示来源身份，不表示某一次 Import 事件。批次逐条处理结果由 `JobImportItem` 记录。

详细决策见 ADR-0007。

### JobRequirement（最重要）

每个岗位 JD 结构化后的需求条目。是 `Match` / `Gap` / `Prepare` 的**统一事实来源**。

- 字段见 `job-requirement.schema.json`：`type`（`skill` / `experience` / `education` / `responsibility` / `domain` / `constraint`）、`normalizedCapability`、`importance`（`must_have` / `preferred` / `bonus`）、`evidenceSpan`、`confidence`、`extractorVersion`。
- 被 `MatchReport.matchedRequirementIds` / `missingRequirementIds` 引用；被 v0.2 `SkillGap.supportingRequirementIds` 引用。

### MatchReport

单个 Job 对用户的可解释匹配结果。

- 关键字段：`eligibility`（`eligible` / `conditional` / `blocked`）、`recommendation`（`strong` / `good` / `stretch` / `low` / `blocked`）、`matchedRequirementIds`、`missingRequirementIds`、`evidenceLinks`、内部 `score`（仅排序，不解释为概率）。
- 输入：UserProfile + SearchIntent + JobRequirement。

### UserFeedback

人类对推荐结果的最终判断，形成闭环。

- 字段见 `user-feedback.schema.json`：`decision`（`interested` / `maybe` / `rejected`）、`reasons`、`comment`。
- 作为 `Match Eval` 人工基准；作为 v0.2 `Target Cohort` 来源之一（`createdFromFeedback`）。

### JobTarget / TargetCohort

目标岗位集。v0.1 不引入；v0.2 由收藏岗位或 UserFeedback 聚合形成，概念从 `JobTarget` 演进为 `TargetCohort`。

- 字段演进见 `job-target.schema.json`：增加 `selectionSource` / `jobIds` / `sampleSize` / `filters` / `createdFromFeedback`。

### SkillGap

v0.2 由 `JobRequirement` 聚合生成的差距。

- 关键字段（P1 增强）：`targetCoverage` / `mustHaveRatio` / `evidenceCoverage` / `gapSeverity` / `supportingRequirementIds`。
- 优先级不单看频率。

---

## 2. 实体关系

```text
UserProfile
    │
    ├── Evidence（1—N，技能回溯证据）

SearchIntent
    │
    ▼
Job ── JobSource（1—N，来源身份与原始证据）
 │
 └── JobRequirement（1—N，统一事实来源）
    │
    ▼
MatchReport（每 Job 每 ProfileVersion 一份）
    │
    ▼
UserFeedback（每 Job 一份人类判断）
    │
    ▼
TargetCohort（v0.2：收藏 / UserFeedback 聚合）
    │
    ▼
SkillGap（v0.2：由 JobRequirement 聚合）
```

关系说明：

- `UserProfile 1 — N Evidence`：技能条目引用 Evidence。
- `Job 1 — N JobSource`：一个统一岗位未来可关联多个外部来源；MVP 主要来源是 BOSS Collector。
- `Job 1 — N JobRequirement`：一个岗位拆成多条需求。
- `UserProfile + SearchIntent + JobRequirement → 1 MatchReport`：匹配结果可追溯到三者。
- `MatchReport 1 — N UserFeedback`（按时间，保留历史）：人类反馈回查到报告。
- `UserFeedback / 收藏 → TargetCohort`：反馈是目标岗位集的来源之一。
- `TargetCohort + JobRequirement → SkillGap`：差距由需求聚合，不回读 JD。

---

## 3. 版本与可追溯

每个关键 Artifact 都记录来源版本，避免“为什么上周 80 分、这周 65 分”不可解释：

- `UserProfile.version`
- `SearchIntent.version`
- `JobRequirement.extractorVersion`
- `MatchReport.profileVersion` + `matchReportId`
- `UserFeedback.profileVersion` + `matchReportId`

统一 Trace 结构（run_id / capability / version / model / prompt_version / input_refs / output / latency / tokens / error）见 `EVAL-AND-TRACE.md`。

---

## 4. 与 Schema 文件的对应

| 实体 | Schema 文件 | 阶段 |
| --- | --- | --- |
| UserProfile | `user-profile.schema.json` | v0.1（P1 增强） |
| Evidence | 内嵌于 `user-profile.schema.json` | v0.1 |
| SearchIntent | `search-intent.schema.json` | v0.1（新增） |
| Job | `job.schema.json` | v0.1 |
| JobRequirement | `job-requirement.schema.json` | v0.1（新增，核心） |
| MatchReport | `match-report.schema.json` | v0.1（P1 增强） |
| UserFeedback | `user-feedback.schema.json` | v0.1（新增） |
| TargetCohort | `job-target.schema.json`（演进） | v0.2 |
| SkillGap | `skill-gap.schema.json` | v0.2（P1 增强） |

> 所有 Schema 位于 `packages/contracts/schemas/`，由 `packages/contracts/README.md` 索引。
