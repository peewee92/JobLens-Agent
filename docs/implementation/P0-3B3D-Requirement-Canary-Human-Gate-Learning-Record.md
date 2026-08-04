# P0-3B-3D｜Requirement Canary Human Gate 学习记录

## 1. 这次真正解决的问题

上一轮已经限制单次 OpenAI 调用数量，但下面的操作仍可绕过人工检查：

```text
第 1 次 max=1
第 2 次 max=1
第 3 次 max=1
第 4 次 max=17
```

每次命令都没有超过自己的上限，但同一个 Run 已经累计执行 20 次。

本轮把约束升级为：

```text
同一个 Run 的累计第 4 次真实调用
必须先有一条不可变的人类 Canary 决策
```

## 2. 先预测，不看答案

先独立填写：

| 场景 | 你的预测 | 原因 |
|---|---|---|
| 新 Run 直接请求 4 次 |  |  |
| 已调用 2 次，再请求 1 次 |  |  |
| 已调用 2 次，再请求 2 次 |  |  |
| 已调用 3 次，无 Review，再请求 1 次 |  |  |
| 已调用 1 次，Review=continue，再请求 19 次 |  |  |
| 已调用 1 次，Review=stop，再请求 1 次 |  |  |
| stop 后重新提交 continue |  |  |
| 被门禁阻止时，Import 是否新增 |  |  |
| 被门禁阻止时，Trace 是否新增 |  |  |

## 3. 最小知识

### 3.1 Command limit 和 Run policy 不是一回事

Command limit 只回答：

> 这一条命令最多调用几次？

Run policy 回答：

> 这个实验累计到什么阶段后，必须由谁做什么决定？

需要持久化的 `attemptedCalls` 才能跨命令执行 Run policy。

### 3.2 为什么失败调用也计数

一次 Provider 调用即使失败，也可能已经消耗：

- 请求额度；
- Token；
- 时间；
- Trace 存储；
- 排查精力。

所以：

```text
成功调用 = 1 attempt
失败调用 = 1 attempt
安全复用 = 0 attempt
主动 deferred = 0 attempt
```

### 3.3 为什么门禁必须在 Application

错误做法：

```python
# CLI only
if max_new_extractions > 3:
    print("too many")
```

另一个脚本、API 或测试可以直接调用 Use Case，绕过 CLI。

正确边界：

```text
CLI：提前解释
Application：权威判断
Database：保证决策唯一
```

### 3.4 为什么客户端不能提交 reviewedCaseIds

若请求允许：

```json
{
  "reviewedCaseIds": ["case_that_user_never_opened"]
}
```

系统不能证明审核者真的基于当前 Canary。

本轮请求只接受：

```json
{
  "reviewer": "will",
  "decision": "continue",
  "notes": "..."
}
```

Backend 从 Run 中找出 `attemptCount > 0` 的 Case，并冻结：

- Case ID；
- Extraction ID；
- Trace ID。

### 3.5 为什么 Review 不可修改

Canary Review 是当时的治理事实：

> 基于这些输出和 Trace，我决定继续或停止。

允许修改会造成：

- stop 被覆盖为 continue；
- 原始责任人和理由消失；
- 审计无法还原；
- 指标只保留最终答案。

纠正错误应创建新的 Run，而不是改写旧判断。

### 3.6 continue 不等于模型通过

`continue` 只表示：

> 当前 1～3 条证据没有差到需要立即终止，可以在显式预算下继续收集证据。

它不表示：

- 20 条已完成；
- 人工质量通过；
- 模型可成为 baseline；
- 可以进入 Match。

## 4. 状态真值表

```text
new Run, request=4
→ block before Import

attempted=2, no Review, request=1
→ allow, cumulative=3

attempted=2, no Review, request=2
→ block, remainingCanaryCalls=1

attempted=3, no Review, request=1
→ block, status=awaiting_canary_review

attempted=1, Review=continue, request=19
→ allow under explicit budget

attempted=1, Review=stop, request=1
→ block before Import

Review already exists, submit another
→ 409; database unique constraint remains final protection
```

## 5. 常见错误实现

```python
if request.max_new_extractions <= 3:
    execute(request.max_new_extractions)
```

失败案例：

```text
09:00 max=1
09:10 max=1
09:20 max=1
09:30 max=17
```

单条命令日志全部“合法”，整体业务规则已经失效。

另一个错误实现：

```python
run.canary_approved = request.decision == "continue"
```

它丢失：

- 谁决定；
- 为什么；
- 审核了哪几个 Case；
- 对应哪次 Extraction；
- 对应哪些 Trace；
- stop 是否曾经存在。

## 6. 实现结构

```text
RequirementAcceptanceRun
  ├─ 20 RunCase
  └─ 0..1 CanaryReview
```

Canary Review：

```text
id
runId (unique)
reviewer
decision = continue | stop
notes
reviewedCaseIds
reviewedExtractionIds
reviewedTraceRunIds
reviewedAt
```

## 7. 为什么 POST Review 可以走 HTTP

Provider 执行：

- 可能持续数分钟；
- 消耗费用；
- 需要重试、取消、租约；
- 不适合普通同步浏览器请求。

Canary Review：

- 一个短数据库事务；
- 没有模型调用；
- 可立即返回；
- 适合 HTTP command。

所以本轮增加：

```http
POST /api/v1/requirement-acceptance-runs/{runId}/canary-review
```

但仍不增加：

```http
POST /api/v1/requirement-acceptance-runs/{runId}/resume
```

## 8. 测试如何证明，而不是“看起来合理”

### 第四次调用门禁

验证：

```text
Run attemptedCalls=3
再次请求 max=1
→ 抛出 CanaryGateError
→ JobImport 数量不变
→ Trace 数量不变
```

### continue

验证：

```text
3 Extractions
→ Review continue
→ snapshot 3 Case + 3 Extraction + 3 Trace
→ resume max=17
→ same Run ID
→ 20 Trace
→ one Batch
```

### stop

验证：

```text
1 Extraction
→ Review stop
→ Run status=stopped
→ 再次执行被拒绝
→ Import/Trace 数量不增加
```

### immutable

验证：

```text
第一次 POST → 201
第二次 POST → 409
DB unique(run_id)
```

### migration

验证：

```text
upgrade head
→ Canary Review table exists

downgrade 0011
→ Canary Review table removed
→ Run/Case tables remain

upgrade head
→ table restored
```

## 9. 尚未解决的并发问题

当前假设一个本地操作者。

仍可能出现：

```text
进程 A 查询：Review 尚未 stop
进程 B 提交：stop
进程 A 已开始下一次 Provider 调用
```

彻底解决需要：

- 运行租约；
- 原子 claim；
- worker 状态；
- 取消语义；
- 数据库锁或队列。

本轮不引入这些基础设施，但必须明确不能声称“分布式并发安全”。

## 10. 面试问题

1. 为什么单次限流不能实现跨命令的 Canary 策略？
2. 为什么失败调用也应计入 attemptedCalls？
3. 为什么审批策略必须放在 Application 层？
4. 如何证明用户审核的是哪一版模型输出？
5. 为什么 reviewed IDs 应由服务端生成？
6. 为什么 Canary Review 应不可变？
7. 数据库唯一约束与 Application 重复检查分别解决什么问题？
8. 为什么短审批可以走 HTTP，长 Provider 执行暂时不走 HTTP？
9. `continue` 和“模型通过验收”有什么区别？
10. 单用户 SQLite 方案迁移到多 worker 时还缺什么？
11. stop 决策为什么不删除 Run？
12. 如何设计多个阶段的 3/10/20 分级放量？

## 11. Demo 脚本（3～5 分钟）

### 场景 A：绕过失败

1. 用模拟 live provider 执行 3 条；
2. GET Run，展示：
   ```text
   attemptedCalls=3
   status=awaiting_canary_review
   canaryReviewRequired=true
   ```
3. 再请求 1 条；
4. 展示被拒绝，Import 和 Trace 数量未变化。

### 场景 B：continue

1. 打开 3 个 Job/Extraction/Trace；
2. POST continue；
3. 展示冻结的 3 组 IDs；
4. 续跑剩余 17 条；
5. 展示同一个 Run、20 Trace 和一个 Batch。

### 场景 C：stop

1. 新 Run 执行 1 条；
2. POST stop；
3. 展示 status=stopped；
4. 再次执行，展示无新 Import、无新 Trace。

## 12. 你需要能独立回答

1. 为什么 `max=3` 不能单独证明 Canary 策略成立？
2. 为什么门禁在 Import 之前执行？
3. 为什么 Review 冻结 Trace ID 而不仅是 Extraction ID？
4. 为什么 stop 后不允许改成 continue？
5. 为什么 continue 可以在 1 条之后提交？它有什么风险？
6. 为什么 continue 至少需要一个成功 Extraction？
7. 哪些测试证明没有发生第 4 次调用？
8. 当前实现在哪种并发场景下仍可能失效？
9. 完成 20 条调用后，还需要哪些人工证据？
10. 什么时候才可以开始 Match？
