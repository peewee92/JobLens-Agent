# Contracts

This package is the source of truth for cross-component domain structures.

Layout:

- `schemas/` — JSON Schema 契约（见下）
- `examples/` — 各契约的示例 payload（随真实样例出现时填充）

Schemas:

- `user-profile.schema.json` — 已确认的版本化职业画像；每个 Skill 至少关联一个 Evidence ID，偏好不再重复内嵌
- `profile-extraction-proposal.schema.json` — 简历文本生成的待确认 Profile Proposal，包含 evidenceSpan 与 run/model/prompt 版本，不代表 confirmed fact
- `profile-eval-run-detail.schema.json` — 不可变 Profile Eval Run 详情；记录 dataset/provider/model/prompt/gate 版本、聚合指标、逐案例失败与 Trace 引用，不包含简历文本
- `job.schema.json` — 标准化 Job 读模型；`id` 为 JobLens internal ID，包含三态远程信息和 JD 质量门禁；`sourceRaw` 由 Backend 的 JobSource 持久化，不进入普通 Job Contract
- `collector-requirement-review-dataset.schema.json` — Collector v1.4.6 导出的 Requirement 人工质量验收数据集；只包含具备岗位职责/任职条件证据、无页面噪声、无招聘者尾部且经过近重复去重的 `full_jd` 岗位，20 条独立样本齐备才标记 `ready`
- `job-page.schema.json` — Job Pool 分页响应，包含 `total / limit / offset / items`
- `job-import-detail.schema.json` — 单次导入审计详情，包含批次统计、快照、candidateSummary 和逐条 outcome；错误 raw / candidateRaw 不进入公开契约
- `search-intent.schema.json` — 独立版本化求职意向，区分 hardConstraints 与 softPreferences
- `job-requirement.schema.json` — 单条 evidence-grounded JobRequirement；包含 Extraction ID、原文、归一化能力、importance、evidenceSpan、confidence 与 extractorVersion
- `job-requirement-extraction.schema.json` — 不可变 Requirement Extraction Run；记录 Job/input hash/provider/model/prompt/Trace 与逐条 Requirements，作为 Match/Gap/Prepare 统一事实来源
- `evidence-retrieval.schema.json` — Phase 4 只读候选证据检索结果；区分 `direct / related` 与检索依据，只返回已确认 Profile Evidence，不包含 `matched/status` 等 Match verdict 字段
- `semantic-match.schema.json` — Phase 4 Semantic Match 暂态结果；保留 deterministic `eligibility / eligibilityStatus`，另行输出 `matched / partial / not_matched` 语义判断，Provider 无权输出或升级 Eligibility、推荐等级或分数；当前 promptVersion 为 `semantic-match-v3`，在 v2 的 transferable-capability 校准上进一步约束“表面流程相似 ≠ shared core mechanism”
- `semantic-match-eval-case.schema.json` — Match Eval JSONL 单案例契约；人工标注 expected verdict / evidence IDs，并显式携带冻结 Eligibility 与 Candidate Evidence
- `semantic-match-eval-report.schema.json` — Match Eval 自包含报告；包含 verdict/evidence accuracy、workflow success、Trace coverage、混淆矩阵、逐案例结果和临时 Eval Trace 摘要，不代表自动 release gate
- `user-feedback.schema.json` — 用户对推荐的人类反馈（v0.1 新增）
- `job-target.schema.json` — 目标岗位集，v0.2 演进为 TargetCohort
- `match-report.schema.json` — Phase 4 persisted MatchReport snapshot；组合 immutable Eligibility 与 Semantic Match，Backend policy 输出 `strong / good / stretch / low / blocked`，包含可追溯 strengths/risks/requirementResults/evidenceLinks，不包含百分制匹配概率；runtime 成功时 `dbWrites=1`
- `skill-gap.schema.json` — 能力差距；v0.2，P1 增强优先级字段

领域关系见 `docs/architecture/DOMAIN-MODEL.md`。
