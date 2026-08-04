# P0-3B-3J｜Explicit Live Canary Operator 学习记录

## 1. 本轮我应该掌握什么

本轮重点不是“会调用 OpenAI”，而是会设计一个不会被误触、不会绕过人工审核、能留下证据的副作用入口。

核心模型：

```text
Readiness = 系统是否允许
Operator Plan = 这次命令是否满足正式数据和预算要求
Execution Authorization = 操作者是否明确请求副作用并接受后续责任
Run / Trace = 副作用实际留下的事实
Human Review = 模型质量是否值得继续
```

## 2. 最小知识

### 2.1 Plan Ready 不等于 Execution Authorized

```text
planReady=true
executeRequested=false
liveCostConfirmed=false
executionAuthorized=false
```

代表系统具备条件，但本次命令不会调用 Provider。

真正授权必须同时满足：

```text
planReady
AND --execute-canary
AND --confirm-live-cost-and-human-review
```

### 2.2 Attempt 不等于 Provider 成功

`attemptCount` 表示系统进入了一次新的 Extraction Attempt。它不能单独证明：

- 网络请求一定离开本机；
- Provider 一定收到请求；
- Provider 一定返回成功；
- Structured Output 一定通过验证；
- Extraction 一定持久化成功。

因此需要同时看：

```text
Case attemptCount delta
Trace ID / Trace error
Extraction ID
Case status / errorCode
```

### 2.3 为什么使用 Before/After Delta

Run 可能已经有 1-2 次历史 Attempt。本次命令不能把历史 Case 再次算作本次证据。

```python
attempt_delta = after.attempt_count - before.attempt_count
```

只有 Delta 大于 0 的 Case 属于本次 Invocation。

### 2.4 为什么 1-2 条后不自动补第 3 条

“最多 3 条”是累计上限，不是自动目标。每一次 Provider 副作用都必须由明确 Invocation budget 触发。

```text
第一次 max=1
→ 完成 1 条
→ 系统可以建议 remaining=2
→ 但不会自动继续
```

### 2.5 为什么第三次后只能进入 Workbench

第三次之后最重要的下一步不再是“多跑数据”，而是判断：

- Requirement 是否漏项；
- importance 是否合理；
- evidenceSpan 是否准确；
- Trace 是否有错误或异常成本；
- 当前模型是否值得继续花费。

这些是本轮刻意保留给学习者的核心能力。

### 2.6 Manifest 写失败的两种时间

#### 执行前失败

```text
Manifest write failed
→ Provider Runtime 不构造
→ 0 live attempt
```

#### 执行后失败

```text
Run / Trace 已存在
→ Post Manifest 更新失败
→ 不能说“没有执行”
→ 返回 completed_with_attention_required
```

数据库和 Trace 是事实来源，Manifest 是便于操作的证据索引。

## 3. 预测题与答案

### 题 1

Readiness 返回 Provider Allowed，但只运行 Operator Plan。

答案：不调用 Provider，不构造 Preparation Runtime。

### 题 2

传 `--execute-canary`，但忘记确认成本与人工审核。

答案：执行被阻止；可以留下执行前 Plan Manifest，但没有 Domain/Provider 副作用。

### 题 3

已有 2 次 Attempt，本次请求 max=2。

答案：Readiness 因 remaining=1 拒绝，Operator 不执行。

### 题 4

已有 3 次 Attempt，且其中一条成功。

答案：进入 `review_canary`。Continue 可用与否由 Backend Human Gate 判断，但必须由人提交。

### 题 5

本次增加 1 个 Attempt，但 Case 没有 Trace ID。

答案：不能当作完整可审计证据，返回 Attention Required。

### 题 6

Preparation 返回的 Model 与授权 Readiness Model 不同。

答案：违反 Cohort invariant，fail closed。

## 4. 常见错误实现

```python
if readiness.provider_execution_allowed:
    use_case.execute(
        payload=payload,
        max_new_extractions=3,
    )
```

问题：

1. 只要有人运行 Readiness 就可能产生费用；
2. 没有 private handoff；
3. 没有 explicit execute；
4. 没有人工责任确认；
5. 没有执行前 Manifest；
6. 没有本次 Attempt delta；
7. 没有第三次后的 Human Stop；
8. 没有 Post Evidence failure handling。

## 5. 面试问题

1. 为什么 Readiness 与 Operator Command 应分开？
2. `planReady` 和 `executionAuthorized` 分别代表什么？
3. 为什么需要两个显式 CLI Flag？
4. 为什么数据必须位于 fingerprint-addressed private path？
5. `attemptCount` 能证明什么，不能证明什么？
6. 如何从 Persistent Run 中提取本次 Invocation 的证据？
7. 为什么 Trace ID 和 Extraction ID 都需要？
8. Provider 已调用但 Manifest 写失败，系统应该返回什么？
9. 为什么第三次 Attempt 后不自动 Continue？
10. 为什么这个命令不允许 Controlled Resume？
11. 为什么不能把 CLI Exit Code 当成质量结论？
12. 如何防止 Manifest 目录被符号链接替换？
13. 为什么 Dataset Fingerprint 和 File SHA-256 是不同证据？
14. 当前方案能实现 exactly-once Provider 调用吗？为什么不能？
15. 如何把该设计迁移到团队环境中的 Queue/Lease/RBAC？

## 6. 5 分钟 Demo

### 第 1 分钟：展示当前事实

```text
DB at Alembic Head
formal private dataset expected path
Provider disabled / Model missing / Key missing
```

### 第 2 分钟：展示 Plan

运行 Operator，不带 `--execute-canary`。

展示：

- `planReady`；
- `executionAuthorized=false`；
- `liveExtractionAttemptsObserved=0`；
- 推荐执行命令。

### 第 3 分钟：展示安全失败

只带 `--execute-canary`，不带确认。

展示 Runtime 没有构造，退出 2。

### 第 4 分钟：展示测试中的受控执行

展示一个 Fake Provider/Use Case 测试：

- Before Attempt=0；
- After Attempt=1；
- Extraction ID；
- Trace ID；
- Post Manifest。

### 第 5 分钟：展示 Human Boundary

展示第三次 Attempt 后：

```text
nextAction=review_canary
workbenchUrl=...
automaticCanaryDecisionSubmitted=false
```

说明真实质量结论仍需要本人检查。

## 7. 实际学习任务

在真实 Canary 前，先不用看代码回答：

1. 如果第一条成功，但 importance 明显错误，你会 Continue 还是 Stop？为什么？
2. 如果 Requirement 正确，但 Trace 延迟和 Token 异常高，你如何决定？
3. 如果第三条失败且有完整 Trace，Stop 是否一定比 Continue 合理？
4. 如果 Dataset File SHA 变化但 Dataset Fingerprint 不变，说明可能发生了什么？
5. 为什么成功 2 条后系统不直接运行第 3 条？

## 8. 当前尚未完成

- 正式文件还未进入 DevSpace；
- 没有真实 OpenAI Model/Key；
- 没有真实 Run/Trace；
- 没有人工 Continue/Stop；
- 没有 20 条人工审核；
- 没有模型批准；
- 没有 Match 放行。
