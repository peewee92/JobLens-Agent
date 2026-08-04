# P0-3B-3F 学习记录｜Requirement Live Readiness Gate

## 1. 本次真正要学什么

这次不是学习“怎么检查环境变量”，而是学习：

> 在一个有成本、有人工门禁、有持久化状态的 Agent 工作流里，如何判断下一步究竟属于机器还是人，以及机器是否真的获准继续。

需要掌握：

- Preflight 与 Readiness；
- 静态配置与动态运行状态；
- `workflowReady`、`providerExecutionAllowed`、`readyForNextAction`；
- blocker code；
- read-only database inspection；
- CLI exit code 与 JSON contract；
- 为什么 Readiness 不属于模型质量证据。

## 2. 先预测

先不要看解释，写下答案：

1. 数据集正式、Key 和 Model 都存在，但数据库仍在旧 migration，能调用吗？
2. Run 已经调用 3 次，API Key 被移除，下一步是什么？
3. Run 已 Continue，但 Key 缺失，`workflowReady` 和 `providerExecutionAllowed` 分别是什么？
4. Run 已 Stop，但所有配置齐全，Readiness 应输出 `fix_blockers` 还是 `stopped`？
5. Run 已有 Batch，为什么 Provider permission 应为 false？
6. 为什么不能只返回一个 `ready`？
7. 为什么数据库不存在时，Readiness 不应该顺手创建数据库？
8. 为什么 migration head 不能硬编码？
9. 为什么不通过一次便宜模型调用测试 Provider 是否健康？
10. 为什么 command preview 可以输出，但 API Key 不能出现？

## 3. 最小知识

### 3.1 Preflight 与 Readiness 不是同一个问题

Preflight：

```text
这个输入是不是正式、独立、可复现的 20-JD 数据集？
```

Readiness：

```text
在当前环境和当前 Run 状态下，下一步是什么？
如果下一步是模型调用，现在是否获准？
```

数据有效不代表运行可执行。

### 3.2 Static facts 与 dynamic facts

静态事实：

```text
Provider
Model
API Key 是否存在
Database URL
Requested budget
```

动态事实：

```text
Run 是否存在
attemptedCalls
Canary Review
Continue / Stop
Batch 是否存在
```

只看静态配置会绕过运行状态机。

### 3.3 为什么有三个布尔值

#### workflowReady

系统能否正确理解这次工作流身份：

- DB 可读；
- migration current；
- provider/model/reviewer/title 完整。

#### providerExecutionAllowed

是否允许新的付费调用：

- 下一动作必须是 `run_canary` 或 `resume_run`；
- Key 存在；
- 显式额度合法；
- 未超过未审核 Canary budget。

#### readyForNextAction

下一步是否明确且可执行。

例如：

```json
{
  "workflowReady": true,
  "providerExecutionAllowed": false,
  "readyForNextAction": true,
  "nextAction": "review_canary"
}
```

这不是失败，而是轮到人。

### 3.4 六个 nextAction

#### fix_blockers

系统无法可靠识别工作流，例如 migration 或配置身份不完整。

#### run_canary

无 Run，或累计调用仍低于 3 且未审批。

#### review_canary

已达到人工门槛，下一步必须去 Web 检查证据。

#### resume_run

已有不可变 Continue，可以使用新显式预算继续。

#### open_manual_review

20 条成功并已有 Batch，下一步是逐条人工质量判断。

#### stopped

不可变 Stop 已存在。没有配置可以解除它。

### 3.5 blocker scope

`workflow` blocker：

```text
database_unreachable
database_migration_not_current
live_provider_not_configured
live_model_not_configured
reviewer_missing
title_missing
```

`provider_execution` blocker：

```text
openai_api_key_missing
max_new_extractions_missing
max_new_extractions_out_of_range
initial_canary_limit_exceeded
remaining_canary_limit_exceeded
```

机器可以根据 code 做行为，用户可以阅读 message。

### 3.6 只读 SQLite

错误做法：

```python
create_engine("sqlite:///missing.db").connect()
```

某些情况下会创建一个空文件，使检查本身改变被检查对象。

本实现：

```text
file:/absolute/path/joblens.db?mode=ro
```

数据库不存在时返回 blocker，文件仍不存在。

### 3.7 exit code

```text
0  下一动作已明确且可执行
1  Readiness 已完成，但仍有 blocker 或 Run 已 Stop
2  输入文件/正式数据集无效
```

Exit 0 不代表模型质量通过，只表示下一操作可执行。

## 4. 状态推导

### 新 Run

```text
max 1–3 + live config + current DB
→ run_canary
→ providerExecutionAllowed=true
```

### 新 Run 请求 4 条

```text
→ run_canary
→ initial_canary_limit_exceeded
→ providerExecutionAllowed=false
```

### 2 attempts

```text
max=1 → 可执行
max=2 → remaining_canary_limit_exceeded
```

### 3 attempts

```text
无 Review
→ review_canary
→ API Key 是否存在不影响人工动作
```

### Continue

```text
→ resume_run
→ 仍需 Key 与显式预算
```

### Stop

```text
→ stopped
→ 不生成 command preview
```

### Batch attached

```text
→ open_manual_review
→ 不需要新的 Provider 调用
```

## 5. 常见错误实现

```python
if dataset_ok and api_key and model:
    print("READY")
```

它无法区分：

- 3 attempts 正等待人工判断；
- 已 Continue；
- 已 Stop；
- 已创建 Batch；
- DB schema 不支持当前代码；
- 请求额度绕过累计门禁。

## 6. 失败案例

环境：

```text
Dataset 合法
Provider=openai
Model 已配置
Key 已配置
Run attemptedCalls=3
Canary Review=null
```

错误检查返回 `READY`，然后执行第 4 次调用。

正确输出：

```json
{
  "workflowReady": true,
  "providerExecutionAllowed": false,
  "readyForNextAction": true,
  "nextAction": "review_canary",
  "workbenchUrl": "http://localhost:3000/evals/requirements/canary/run_xxx",
  "providerCalls": 0
}
```

## 7. 代码结构

### Pure policy

```text
app/application/requirement_acceptance/readiness.py
```

输入：Preflight、配置事实、DB revision、Existing Run、预算。

输出：next action、permission、blockers、URL。

### Infrastructure adapter

```text
scripts/check_requirement_acceptance_readiness.py
```

负责：

- 读文件；
- 获取 settings；
- 动态读取 Alembic head；
- 只读查询 DB revision；
- 查询 Existing Run；
- 输出 JSON/text/exit code。

Policy 不自己打开文件、数据库或环境变量。

## 8. 面试问题

1. Preflight 和 Readiness 有什么区别？
2. 为什么 Readiness 要读取业务 Run，而不是只读配置？
3. 为什么一个系统需要 `workflowReady` 与 `providerExecutionAllowed` 两个概念？
4. Human-in-the-loop 中，何时 `readyForNextAction=true` 但不能调用模型？
5. 如何保证环境检查不创建 SQLite 数据库？
6. 为什么 blocker 应有稳定 code，而不只有 message？
7. 为什么 API Key 只返回 boolean？
8. 为什么 migration mismatch 应在 Provider 调用前发现？
9. Continue 与 Batch ready 的下一动作有什么不同？
10. 为什么 Readiness 不能证明模型质量？
11. 如何扩展到多个 live Provider？
12. 如果改为 Web 队列执行，还需要哪些并发控制？

## 9. Demo 内容

### Demo A：缺少 Key

展示：

```text
workflowReady=true
providerExecutionAllowed=false
blocker=openai_api_key_missing
providerCalls=0
dbWrites=0
```

### Demo B：首次请求超过 3

展示 `initial_canary_limit_exceeded`。

### Demo C：3 attempts

展示 `review_canary` 和 Workbench URL，不要求 Key。

### Demo D：Continue

展示 `resume_run` 与不含密钥 command preview。

### Demo E：Stop

展示 `stopped`，无 command preview。

### Demo F：Batch ready

展示 Manual Review URL。

## 10. 作品集表述

可以表述：

> 为带成本与 Human-in-the-loop 门禁的 Requirement Extraction 工作流设计了零调用 Readiness Gate。它组合 formal dataset、动态 Alembic head、只读 DB revision、live config 和持久化 Run 状态，区分机器执行与人工下一动作，并以稳定 blocker code、无密钥 command preview 和 exit code 提供可复现操作证据。

不要表述：

> 已完成真实模型质量验收。

因为尚未有真实 Provider Trace 和 20 条人工质量结论。

## 11. 学习验收问题

完成后不用看代码回答：

1. Preflight 已通过，为什么 Readiness 仍可能失败？
2. 三个 readiness boolean 分别回答什么？
3. 3 attempts、无 Key 时为什么仍然 `readyForNextAction=true`？
4. Stop 为什么不是一个可修复 blocker？
5. Batch ready 时为什么没有 command preview？
6. 为什么 Existing Run 的身份包含 dataset/title/reviewer/cohort？
7. 哪些 blocker 属于 workflow，哪些属于 provider execution？
8. SQLite `mode=ro` 防止了什么？
9. Exit 0 能证明什么，不能证明什么？
10. 现在还缺哪些真实证据才能进入 Match？
