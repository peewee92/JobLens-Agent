# ADR-0004：LLM / Workflow / Agent 边界

## 状态

Accepted

## 决策

业务能力分层，而不是“所有业务都写成 Agent Tool”：

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

## 约束

- Agent **不直接实现**业务能力（匹配、需求抽取、排序都由 Workflow 负责）；
- Agent 只做**编排**：理解用户目标、选择并调用已稳定的 Workflow、汇总结果；
- 确定性业务规则（如 `Eligibility` 硬条件判定）必须由代码实现，Agent 不能推翻；
- v0.1 不要求用户直接面对 Agent；Agent 入口推迟到 P1。

## 反模式（明确不做）

```text
所有业务都是 Agent Tool
→ Agent 里塞满 get_user_profile / match_job / analyze_skill_gap ...
→ 业务逻辑散落在 Prompt 与 Tool 之间，无法单独评测
```

## 原因

- 把能力拆成“可单独评测的 LLM Capability”+“可组合 Workflow”，每个环节都能接 Eval（见 ADR-0005）；
- Agent 只负责编排，业务事实仍来自 `JobRequirement` 等统一领域模型，避免 Prompt 各自为政；
- 多 Agent 不进入本期，避免协调复杂度压垮尚不稳定的核心价值链。

## 影响

- `SYSTEM-ARCHITECTURE.md` §6 明确三层结构；
- `AGENTS.md` 开发规则第 3 条：“Agent 不直接实现业务能力，Agent 组合稳定 Workflow”。
