# Contracts

This package is the source of truth for cross-component domain structures.

Layout:

- `schemas/` — JSON Schema 契约（见下）
- `examples/` — 各契约的示例 payload（随真实样例出现时填充）

Schemas:

- `user-profile.schema.json` — 用户职业画像（含 Evidence）；v0.1 使用，P1 增强
- `job.schema.json` — 标准化 Job 读模型；`id` 为 JobLens internal ID，包含三态远程信息；`sourceRaw` 由 Backend 的 JobSource 持久化，不进入普通 Job Contract
- `job-page.schema.json` — Job Pool 分页响应，包含 `total / limit / offset / items`
- `job-import-detail.schema.json` — 单次导入审计详情，包含批次统计、快照和逐条 outcome；错误 raw 不进入公开契约
- `search-intent.schema.json` — 求职意向（v0.1 新增）
- `job-requirement.schema.json` — 岗位需求抽取，Match/Gap/Prepare 统一事实来源（v0.1 新增，核心）
- `user-feedback.schema.json` — 用户对推荐的人类反馈（v0.1 新增）
- `job-target.schema.json` — 目标岗位集，v0.2 演进为 TargetCohort
- `match-report.schema.json` — 岗位匹配报告；v0.1 字段已落地，P1 增强 eligibility/evidenceLinks
- `skill-gap.schema.json` — 能力差距；v0.2，P1 增强优先级字段

领域关系见 `docs/architecture/DOMAIN-MODEL.md`。
