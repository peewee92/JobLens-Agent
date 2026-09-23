# vNext 1.1 Release Gate 状态

- Milestone：`vNext 1.1 Natural Language + Bounded Multi-turn Tool Calling`
- 状态：`RELEASE_CANDIDATE / PROVIDER_QUALITY_BLOCKED`
- 日期：2026-09-23
- Integration Owner 结论：确定性 Runtime / Safety Gate 已满足当前产品范围；真实模型质量门尚未测量通过，因此 **vNext 1.1 不能标记 COMPLETE，也不能进入 vNext 1.2**。

## 1. 当前集成候选

共享 `main` 当前仍为：

```text
82c4770 test(agent): make the provider gates operable and pin the transport path
```

Agent B 在此基础上的线性候选为：

```text
1f3029f fix(agent): honour provider rate limits instead of failing the cohort
e6bd617 test(agent): record replay-grade evidence identity in the provider gates
```

`1f3029f` 解决真实 Provider 的 429 限流：按 Provider `retryAfterSeconds` 做 bounded wait，并允许请求间 pacing，避免 60-case cohort 把限流误记成模型质量失败。

`e6bd617` 为每个 Provider case 补齐可回放证据身份：Provider trace id、request fingerprint、dataset fingerprint；Authorization 不进入 fingerprint。即使 Provider 拒绝或 Gate 处于 `not_measured`，仍能证明本次计划测量的 Dataset / Prompt / Schema 身份。

## 2. 运行时基线

2026-09-23 复核：

```text
semanticPolicyVersion=requirement-semantics-v42.96
Requirement Review=20/20
accepted=15
rejected=5
finalDecision=accept_for_match
matchReleaseEligible=true
real_total_jobs=20
current MatchReport=20/20
UserFeedback=20/20
top_n_available=true
top_n_evidence_complete=true
next_priority=real_mvp_value_loop_observed
```

因此 vNext 1.1 不得回退 Requirement remediation，也不得重新生成已有 MatchReport / UserFeedback。

## 3. 确定性 Release Gate

在 `e6bd617` 候选上重新执行 Intent / Tool Selection / Loop Guard / Trajectory 相关 Gate：

```text
80 passed
```

Agent B 已完成的正式确定性证据包括：

- Loop Guard：26/26；
- Trajectory：50/50 case 通过；
- 轨迹形态：9 covered / 0 partial / 1 blocked；
- unknown tool / invalid params / retry / repeat loop / no-progress / stale / timeout / cancellation 均已有结构化终止与 Trace；
- Durable `Ranking → HITL → Gap` 已由真实 SQLite trajectory 覆盖；
- Provider calls = 0；
- unauthorized business writes = 0；
- human decision auto-sign = 0；
- P95 Runtime floor 已有可解释基线。

这些事实说明当前没有新的 Core Contract / Runtime blocker。

## 4. GAP-1 范围裁决

### 4.1 事实

PRD §15.3 列出：

```text
cost action → PendingAction
```

当前 `CareerAgentExecutionGate` 已实现：

```text
provider_compute
business_write
external_action
→ PendingAction
→ Workflow 在人工确认前不执行
```

且已有执行门回归证明：pending 路径不会调用 Tool Registry。

但当前 vNext 1.1 `CareerAgentToolRegistry` 有意只注册成熟的 read-only Workflow：

```text
rank_match_reports
target_cohort_gaps
job_preparation
```

三个 Tool 的真实治理属性均为：

```text
side_effect = read_only
provider_cost = none
human_gate = none
```

因此当前产品 Registry 中不存在一个真实、成熟、可合法加入生产范围的 cost-gated Tool。

### 4.2 Integration Owner 决定

**GAP-1 不作为 vNext 1.1 当前产品范围的 Release blocker，但不得伪报为 covered。**

理由：

1. vNext 1.1 第一阶段产品边界明确只自动执行 read-only / transient Tool；
2. §16 Release Gate 的安全目标是防止未授权写入、自动代签、无限循环和不可回放执行，并未要求为了测试必须制造一个真实收费 Tool；
3. PendingAction / Execution Gate 机制已经通过合成治理定义验证 fail-closed；
4. 为 Eval 人造收费 Tool 会扩大产品能力范围，违反“Agent 只组合成熟 Workflow”的仓库规则。

因此：

- Trajectory 报告继续真实显示 `GAP-1 = blocked`；
- 不把它改写成 `covered`；
- 不创建假 Provider Tool；
- vNext 1.1 Release 判定不再等待一个不存在于当前产品范围的真实 cost Tool；
- **未来第一个真实 `provider_compute / business_write / external_action` Workflow 进入 Registry 时，必须重新激活该真实纵向轨迹 Gate，并在允许发布前证明 `Tool → PendingAction → Durable HITL → resume`。**

## 5. 真实 Provider 模型质量门

当前正式 cohort：

```text
Intent          60 cases
Tool Selection  44 cases
```

目标：

```text
Intent acceptable accuracy >= 95%
Tool Selection accuracy     >= 95%
Safety violations           = 0
Registry / ACL bypass       = 0
Human Gate bypass           = 0
```

2026-09-23 使用 `deepseek-v4-flash` 对正式 Intent cohort 首 case 做真实 Provider 探针：

```text
HTTP 402
code=INSUFFICIENT_BALANCE
attempts=1
completed=0
traceId=trace_a58a788f-c905-4d64-987c-9747f95acf61
```

因此当前准确状态是：

```text
Intent          = NOT_MEASURED
Tool Selection  = NOT_MEASURED
```

`not_measured` 不能解释成 0%，也不能解释成 PASS。

当前唯一外部阻塞为 Provider 账户无生成余额；这不是 Core Runtime blocker。

## 6. 模型版本风险

Agent B 最近读取 Provider `/models` 时看到：

```text
deepseek-v4-flash-0731
```

而历史正式 cohort 使用：

```text
deepseek-v4-flash
```

余额为 0 时无法确认旧 alias 是否仍可调用。

余额恢复后必须先按原模型身份运行。如果返回 `model_not_found`，允许切到 `deepseek-v4-flash-0731`，但必须作为**新的模型版本测量**记录 Provider / Model / Prompt / Schema / Dataset fingerprint，不得把它冒充成历史同一 cohort 的连续结果。

## 7. vNext 1.1 Remaining Criteria

当前只剩：

1. Provider 余额恢复；
2. 基于 `1f3029f + e6bd617` 候选执行真实 Intent 60-case Gate；
3. 执行真实 Tool Selection 44-case Gate；
4. 两门均达到 `>=95%` 且 safety violation = 0；
5. 若真实 Gate 暴露 Core Contract / Runtime bad case，交 Agent A 做“失败回归 → 最小修复 → targeted regression”；
6. 两门通过后由 Integration Owner 更新 ROADMAP，将 vNext 1.1 标记 COMPLETE，并才允许切换到 vNext 1.2。

## 8. 当前停止规则

在 Provider 仍返回 402 时：

- 不每小时重复跑 104-case cohort；
- 不继续扩 Runtime；
- 不新增 Eval Dataset；
- 不伪造 PASS；
- 不进入 vNext 1.2；
- 不用低价值重构制造 commit。

下一次 Provider Gate 应从一个 bounded live probe 开始；只有 402 消失后才执行完整 60+44 cohort。
