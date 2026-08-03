# Contracts

This package is the source of truth for cross-component domain structures.

Layout:

- `schemas/` — JSON Schema 契约（见下）
- `examples/` — 各契约的示例 payload（随真实样例出现时填充）

Schemas:

- `user-profile.schema.json` — 已确认的版本化职业画像；每个 Skill 至少关联一个 Evidence ID，偏好不再重复内嵌
- `profile-extraction-proposal.schema.json` — 简历文本生成的待确认 Profile Proposal，包含 evidenceSpan 与 run/model/prompt 版本，不代表 confirmed fact
- `profile-eval-run-detail.schema.json` — 不可变 Profile Eval Run 详情；记录 dataset/provider/model/prompt/gate 版本、聚合指标、逐案例失败与 Trace 引用，不包含简历文本
- `job.schema.json` — 标准化 Job 读模型；`id` 为 JobLens internal ID，包含三态远程信息；`sourceRaw` 由 Backend 的 JobSource 持久化，不进入普通 Job Contract
- `job-page.schema.json` — Job Pool 分页响应，包含 `total / limit / offset / items`
- `job-import-detail.schema.json` — 单次导入审计详情，包含批次统计、快照、candidateSummary 和逐条 outcome；错误 raw / candidateRaw 不进入公开契约
- `search-intent.schema.json` — 独立版本化求职意向，区分 hardConstraints 与 softPreferences
- `job-requirement.schema.json` — 单条 evidence-grounded JobRequirement；包含 Extraction ID、原文、归一化能力、importance、evidenceSpan、confidence 与 extractorVersion
- `job-requirement-extraction.schema.json` — 不可变 Requirement Extraction Run；记录 Job/input hash/provider/model/prompt/Trace 与逐条 Requirements，作为 Match/Gap/Prepare 统一事实来源
- `user-feedback.schema.json` — 用户对推荐的人类反馈（v0.1 新增）
- `job-target.schema.json` — 目标岗位集，v0.2 演进为 TargetCohort
- `match-report.schema.json` — 岗位匹配报告；v0.1 字段已落地，P1 增强 eligibility/evidenceLinks
- `skill-gap.schema.json` — 能力差距；v0.2，P1 增强优先级字段

领域关系见 `docs/architecture/DOMAIN-MODEL.md`。
