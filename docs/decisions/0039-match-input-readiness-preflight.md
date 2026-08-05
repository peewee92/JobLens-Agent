# ADR-0039：Match Input Readiness 只读预检

## 状态

Accepted

## 背景

Phase 4 的 Eligibility 与 Semantic Match 尚未实现。此前系统已经分别建立：

- Confirmed Career Context Release Gate；
- Job Requirement Fact Release Gate。

如果未来 Match 调用方分别读取两个 Gate 并自行组合，容易出现默认放行、漏报 blocker，或在 Web 层重复实现 Backend 策略。

## 决策

新增只读接口：

```http
GET /api/v1/jobs/{job_id}/match-input-readiness
```

Backend Application 层组合两个既有 Gate，并返回：

- `inputsReleaseEligible`；
- 完整 Career Context readiness；
- 完整 Job Requirement readiness；
- 带 `source` 的统一 blocker 列表；
- `dbWrites=0`、`providerCalls=0`、`traceRunsCreated=0`。

只有两个既有 Gate 都 `releaseEligible=true` 时，预检才为 true。

## 边界

该接口不是 Match 执行，也不定义 Eligibility 规则。它不会：

- 调用 LLM/Provider；
- 创建 Trace；
- 写数据库；
- 生成 MatchReport；
- 计算 score/recommendation；
- 将预检结果持久化为长期事实。

真实 Match 执行仍必须在执行边界重新读取并记录具体 Profile、SearchIntent、Requirement Extraction 与 Trace 身份，不能把较早的预检响应当作事务锁或永久授权。

## 原因

- 复用现有可信事实门禁，不复制规则；
- 在进入核心 Eligibility 设计前，先明确所有输入 blocker；
- 为 API、Web 和后续 Agent Workflow 提供统一只读契约；
- fail-closed：任一 Gate 阻塞都不得执行 Match。

## 后果

优点：

- 调用方不需要理解两个 Gate 的内部规则；
- blocker 保留来源与原始证据身份；
- 可以在没有 Provider、真实数据或 Match 规则时完整测试。

限制：

- 这是 advisory preflight，不提供跨多个查询的数据库事务一致性保证；
- 当前真实环境仍因 Requirement 人工验收缺失而无法放行；
- Eligibility 产品规则仍属于独立 HUMAN_GATE。
