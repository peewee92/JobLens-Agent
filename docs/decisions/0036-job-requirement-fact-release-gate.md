# ADR-0036：Job Requirement Fact Release Gate

- Status: Accepted
- Date: 2026-08-05
- Scope: Phase 3 Requirement Intelligence → Phase 4 boundary

## Context

JobLens 已具备：

1. 不可变 `JobRequirementExtraction` 与逐条 `JobRequirement`；
2. Requirement Trace；
3. 20 Case Manual Review Batch；
4. 不可变 Batch Final Decision；
5. 当前有效的 human-accepted Requirement baseline Query。

这些能力仍不足以证明任意岗位的最新 Requirement 可直接供 Match 使用。

人工接受的 baseline 只证明某个 provider/model/extractor/prompt cohort 在一组正式样本上的质量被人工接受。它不自动证明：

- 某个岗位已有 Extraction；
- Extraction 仍对应当前 JD；
- Extraction 使用的是被接受的 cohort；
- Trace 成功且确实属于该 Extraction；
- Trace 输入、输出与数据库中的事实一致；
- Requirement 记录非空且计数一致。

若 Match 只检查“存在 accepted baseline”，历史、过期、错误 cohort 或 Trace 漂移的 Requirement 仍可能进入匹配事实链。

## Decision

新增只读 `Job Requirement Fact Release Gate`。

```text
current Job description
+ latest JobRequirementExtraction
+ exact persisted JobRequirements
+ immutable Trace
+ current human-accepted Requirement baseline
→ JobRequirementReleaseReadiness
```

只有所有条件同时成立时：

```text
releaseEligible = true
```

未来 Match 只能消费 `releaseEligible=true` 的 Requirement facts。

本 ADR 不实现 Match、Eligibility、Semantic Fit、推荐等级或 MatchReport。

## Trust chain

### 1. Current Job input

Gate 对当前 `job.description.strip()` 计算 SHA-256，并要求：

```text
latestExtraction.inputHash == currentDescriptionSha256
```

Job 修改后，旧 Extraction 立即失效。

### 2. Accepted quality baseline

Gate 只读取 `get_accepted_baseline()`。

该 Query 已动态要求：

- 20 Case 正式证据完整；
- Final Decision 为 `accept_for_match`；
- Batch 当前未 stale。

历史已接受但已 stale 的 Batch 不会被返回。

### 3. Cohort equality

Target Extraction 必须与 accepted baseline 完全共享：

- provider；
- model；
- extractorVersion；
- promptVersion。

不允许“同一家 Provider”或“模型名字近似”替代精确 cohort 对齐。

### 4. Persisted fact integrity

Gate 要求：

- 至少一条 Requirement；
- `requirementCount == loaded requirements length`。

### 5. Trace integrity

Gate 要求 Trace：

- 存在；
- `error is null`；
- capability 为 `requirement_extraction`；
- version/model/prompt 与 Extraction 一致；
- `inputRefs.jobId` 与 Job 一致；
- `inputRefs.descriptionSha256` 与 Extraction input hash 一致；
- Trace output 中每条 Requirement 的 type、originalText、normalizedCapability、importance、evidenceSpan、confidence 与持久化事实逐条精确一致。

仅比较数量不足以证明同一份输出。

## Fail-closed blocker model

存在的 Job 使用 HTTP 200 返回结构化 blockers，而不是将不可信状态隐藏为异常。

主要 blocker：

- `accepted_baseline_missing`；
- `requirement_extraction_missing`；
- `extraction_input_stale`；
- `extraction_cohort_mismatch`；
- `requirements_empty`；
- `requirement_count_mismatch`；
- `trace_missing`；
- `trace_failed`；
- `trace_capability_mismatch`；
- `trace_cohort_mismatch`；
- `trace_input_mismatch`；
- `trace_output_mismatch`。

多个事实同时损坏时允许返回多个 blocker，以保留诊断信息。

不存在的 Job 仍返回 404，因为资源本身不存在，不属于 readiness 状态。

## Query/Command boundary

Release Gate 是纯 Query：

- 不创建 Extraction；
- 不写 Trace；
- 不修改 Review 或 Final Decision；
- 不调用 Provider；
- 不生成 MatchReport。

Extraction Command、人工 Final Decision Command 与 Release Readiness Query 保持分离。

## Alternatives rejected

### 只检查 accepted baseline 存在

拒绝。无法证明目标岗位 Extraction 当前有效或 cohort 对齐。

### 只检查 Extraction provider/model

拒绝。忽略 JD 变化、Trace 失败和数据库/Trace 内容漂移。

### 将 releaseEligible 持久化到 Extraction

拒绝。其值依赖动态 baseline 与当前 Job 输入。持久化布尔值容易在 baseline stale 或 Job 修改后过期。

### 在 Web 页面计算门禁

拒绝。浏览器不能成为质量策略事实来源，且未来 API/Batch Match 无法复用。

### 直接开始 Match，再在失败时提示

拒绝。会让不可信事实进入更下游的 LLM 和排序链路。

## Consequences

### Positive

- 人工接受的模型质量可传播到单个岗位事实；
- Job 修改、baseline stale 和 cohort 漂移会自动撤销资格；
- blocker 可被 API、UI 和未来 Match 统一消费；
- 不需要新增表或迁移；
- Gate 可在零 Provider 调用下持续复查。

### Trade-offs

- 每次 Query 需要读取 Job、latest Extraction、accepted baseline 和 Trace；
- 当前实现按单 Job 查询，Batch Match 前需要批量化或缓存策略；
- accepted baseline 是全局最新有效 baseline，尚未支持按 job family 或语言分区；
- Reviewer 身份仍是本地自由文本治理模型。

## Verification

- Application blocker truth-table tests；
- SQLite Trace adapter test；
- HTTP 200 + blockers / 404 tests；
- Query 前后 Extraction/Trace 计数不变；
- Web architecture tests：页面只消费 Backend facts；
- production Next build；
- FastAPI + Next + temporary SQLite smoke：

```text
no Final Decision
→ Job facts blocked
→ Final Accept
→ Job facts released
→ newer Extraction makes baseline stale
→ Job facts blocked again
```

## Not proven

- 真实 OpenAI Provider 质量；
- 正式 20-JD Final Decision；
- 真实岗位的 releaseEligible 状态；
- Phase 4 Match 正确性；
- Batch release gate 的吞吐与缓存方案。
