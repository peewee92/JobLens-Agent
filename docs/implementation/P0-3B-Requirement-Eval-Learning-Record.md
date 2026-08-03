# P0-3B｜Requirement Eval 持久化与质量证据学习记录

- Date: 2026-08-03
- Phase: 3B-1
- Status: implemented and verified
- Product boundary: Requirement quality governance before Match

## 1. 本次真实问题

Phase 3A 已经具备：

```text
JD
→ Requirement Workflow
→ Structured Output
→ deterministic grounding
→ Trace
→ 10-case Fixture Eval
```

但 Eval 结果只存在于终端，无法回答：

- 哪一版 Dataset / Provider / Model / Prompt 被评估；
- 哪些 Case 失败；
- 失败对应哪条 Trace；
- 当前版本是否比历史版本退化；
- Fixture 通过是否被误当成真实 Provider 可发布。

因此本次没有进入 Match，而是先完成：

```text
Requirement Eval Dataset
→ Workflow × N
→ Trace × N
→ deterministic Gate
→ immutable Eval Run + Case Results
→ optional Baseline comparison
→ read-only API
```

## 2. 业务风险与学习风险

### 业务风险：高

错误 Requirement 会继续污染：

```text
Eligibility
→ Match
→ Ranking
→ Skill Gap
→ Resume / Interview
```

典型后果：把 preferred 错当 must-have、漏掉硬约束、凭空补出能力，或者让后续推荐建立在错误事实之上。

### 学习风险：高

最容易发生的伪学习是照抄 Profile Eval，而不能解释：

- 为什么 Provider 调用不放在数据库事务里；
- 为什么 Trace 与 Eval Run 分开持久化；
- 为什么 Fixture 10/10 仍不可发布；
- 为什么 Baseline Delta 在查询时推导；
- 为什么 Gate 通过仍需人工 Review。

## 3. 已确认事实 / 推断 / 假设 / 未知

### 已确认事实

- Requirement Eval Dataset 有 10 个脱敏 Case；
- Fixture 当前 10/10 通过；
- 每个 Case 已能产生 Trace ID；
- 之前没有 Requirement Eval Run/Case 数据表；
- 之前 CLI 只打印结果；
- Profile Eval 已证明不可变 Run + Case + Baseline 模式可行，但两个领域的指标不同。

### 推断

- Match 前必须先有可回查、可比较的 Requirement 质量证据；
- Requirement Eval 应独立建模，不能塞进 Profile Eval 的通用表；
- 人工 Review 应是下一独立切片，而不是和持久化同时扩大范围。

### 假设

- MVP 继续使用 SQLite；
- `fixture` 是 Fixture 模式，非 Fixture 的允许 Provider 视为 Live；
- Live + Gate 通过只表示有资格进入人工审查；
- 当前阶段不通过 HTTP 触发昂贵 Provider Eval。

### 尚未知

- 真实 OpenAI Provider 的准确率、成本和延迟；
- 当前 10 个 Case 是否充分代表目标岗位市场；
- Gate 阈值是否适合生产；
- 20 个真实岗位人工审查会暴露哪些归一化和 importance 问题。

## 4. 先预测：核心能力训练

在查看实现前，应先手写以下答案。

### 预测 A｜发布资格真值表

| mode | gatePassed | releaseEligible |
|---|---:|---:|
| fixture | false | false |
| fixture | true | false |
| live | false | false |
| live | true | true |

Fixture 只证明测试管线可重复，不证明真实模型质量。

### 预测 B｜事务边界

正确链路：

```text
每个 Case 执行 Workflow
→ 每个 Case 独立写 Trace
→ 汇总指标
→ 开启短事务
→ 原子写入 Run + 全部 Case Results
```

不应在一个长事务中调用模型 10 次。

### 预测 C｜最终落库失败时 Trace 是否保留

应保留。

收益：仍能诊断模型执行和验证过程。  
代价：可能存在没有 Eval Run 引用的孤立 Trace，需要后续治理策略。

### 预测 D｜六个月后复现所需信息

至少包括：

- Dataset Version；
- Provider / Model；
- Extractor Version；
- Prompt Version；
- Gate Version；
- Case Results；
- Trace IDs；
- Baseline Run ID；
- Created At。

### 预测 E｜Baseline Delta 是否落库

不落库。当前 Run 只保存不可变 `baselineRunId`，查询时读取两个不可变 Run 推导 Delta，避免重复数据漂移。

## 5. 本次最小知识

### Repository

定义应用需要的读写能力，不负责事务，不暴露 SQLAlchemy。

### Unit of Work

控制一次业务写入的事务范围。本次保证：

```text
1 个 RequirementEvalRun
+
10 个 RequirementEvalCaseResult
```

要么全部提交，要么全部回滚。

### Trace

记录一次真实 Workflow 执行，回答“这次模型具体发生了什么”。

### Eval

把固定 Dataset 和外部预期作用于 Workflow，回答“这个能力是否达到定义的质量标准”。

### Gate

当前包括：Case Pass Rate、Workflow Success Rate、Capability Recall、Importance Accuracy 和 Forbidden Capability Rate。

### Human Review

检查 Dataset/Gate 没覆盖的语义与真实业务问题。当前未实现。

## 6. 关键设计与权衡

### Fixture 与 Live 强制隔离

应用层：

```python
release_eligible = mode is LIVE and report.gate_passed
```

数据库层再次用 Check Constraint 防止 `fixture + releaseEligible=true`。

### Trace 与 Eval 使用不同事务

Provider 是慢且不可靠的外部依赖，不应长期占用数据库事务。

最终 Eval 持久化失败时，测试证明：

```text
Trace = 10
Eval Run = 0
Eval Cases = 0
```

### Baseline 在运行前校验

不存在的 Baseline 会在任何 Workflow/Trace 前返回错误，避免浪费 Provider 成本和产生无法比较的运行证据。

### Comparison 是派生读模型

Run 只保存 Baseline 引用；Repository 查询详情时推导指标 Delta。

### Read API 不暴露 raw JD

API 只返回 Provenance、Metrics、Case Diagnostics、Trace ID 与 Baseline Comparison，不返回 raw description、`originalText` 或 `evidenceSpan`。

## 7. 常见错误实现

```python
report = run_requirement_eval(...)
if report.gate_passed:
    enable_match = True
```

失败原因：

- Fixture 可错误开启生产能力；
- 没有不可变历史；
- 无 Case/Trace 证据；
- Dataset/Prompt/Gate 版本丢失；
- 没有人类治理边界；
- 一次幸运运行可改变系统行为。

## 8. 失败案例

`DegradedRequirementExtractor` 只返回每条 JD 的第一项 Requirement。

结果：

```text
Workflow Success Rate = 100%
Trace = 10/10
Capability Recall < 95%
Gate = failed
Release Eligible = false
```

结论：HTTP 成功、JSON 合法、Workflow 无异常，只能证明执行成功，不能证明业务事实完整。

## 9. 工程完成证据

- `requirement_eval_runs` 与 `requirement_eval_case_results` 已迁移；
- Fixture Run 持久化 1 Run、10 Cases、10 Traces；
- Fixture 10/10 仍 `releaseEligible=false`；
- Live + Gate 通过测试可成为 `releaseEligible=true`；
- 退化 Extractor 以可解释缺失项失败；
- Provider 失败仍保留 Case → Trace；
- 最终 Eval 持久化失败保留 10 Trace、无半成品 Run/Case；
- Baseline 不存在时产生 0 Trace、0 Run；
- 列表/详情/404/OpenAPI 已测试；
- Alembic upgrade/downgrade/check 已测试；
- 全量 Backend：226 passed。

## 10. 学习完成问题

请脱离代码回答：

1. 为什么模型调用不能放在 Requirement Eval 数据库事务中？
2. 为什么 Trace 已成功而 Eval Run 落库失败时，Trace 应保留？
3. 为什么 Fixture 10/10 通过仍必须 `releaseEligible=false`？
4. 为什么 Baseline 要在任何 Workflow 执行前验证？
5. Repository 与 Unit of Work 的职责有什么区别？
6. 为什么 Gate 通过不能自动进入 Match？
7. 为什么 Requirement Eval 与 Profile Eval 不共用一张通用表？
8. `capabilityRecall=100%` 仍可能漏掉什么？

学习完成标准：能用自己的话解释，并画出 Provider/Trace/Eval 两类事务边界。

## 11. 面试问题

### 后端

- 为什么外部 API 调用通常不应放在数据库事务中？
- 如何保证父 Run 和全部 Case Result 原子写入？
- 为什么应用约束和数据库 Check Constraint 要同时存在？
- 为什么 Baseline Delta 不落库？
- 不可变运行记录如何支持审计和回归？

### Agent / AI 应用

- Fixture Eval、Live Eval、Human Review 各自证明什么？
- Trace 与 Eval 有什么区别？
- Workflow Success 与 Capability Recall 为什么要分开？
- 如何防止错误 Requirement 污染 Match、Gap 与 Resume？
- 为什么不能让模型评价并批准自己的输出？

## 12. Demo 脚本

### 运行 Fixture Eval

```bash
cd services/backend
REQUIREMENT_EXTRACTOR_PROVIDER=fixture \
uv run python -m scripts.run_requirement_eval
```

预期：

```text
id=reqeval_...
passed=10/10
gatePassed=True
releaseEligible=False
```

### 查询历史和详情

```bash
curl http://127.0.0.1:8000/api/v1/requirement-evals
curl http://127.0.0.1:8000/api/v1/requirement-evals/reqeval_xxx
```

### 对比 Baseline

```bash
REQUIREMENT_EXTRACTOR_PROVIDER=fixture \
uv run python -m scripts.run_requirement_eval \
  --baseline-run-id reqeval_xxx
```

### 展示退化失败

```bash
uv run pytest tests/test_requirement_eval_runs.py -k degraded -vv
```

## 13. 尚未验证

- 真实 OpenAI Provider；
- 20 个真实岗位人工质量验收；
- Requirement Human Review / Accepted Baseline；
- 真实成本、P50/P95 延迟和重试策略；
- Web Review UI；
- Eligibility / Match / Ranking。

因此当前结论是：

> Requirement Eval 质量证据基础设施已完成；真实模型质量尚未被批准，不能进入 Match。
