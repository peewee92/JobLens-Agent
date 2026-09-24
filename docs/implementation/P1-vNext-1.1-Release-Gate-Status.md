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

2026-09-24 已切换到新的 OpenAI-compatible Provider。当前已验证：

```text
GET /v1/models                = 200
model                         = deepseek-v4.1-flash
plain chat completion         = 200
json_schema completion        = 200
Career Intent single adapter  = 1/1 success（Prompt compatibility fix 后）
```

旧 `deepseek-v4-flash` 在新 Provider 上返回 `model_not_found`，因此新的正式测量必须把：

```text
provider + deepseek-v4.1-flash + prompt/schema/dataset fingerprint
```

视为一个新的 Cohort Identity，不能与历史旧 Provider / 旧模型结果拼接。

真实 Intent 诊断批次随后暴露的主要问题集中在 Prompt / Model / Eval 语义对齐，而不是已证实的 Core Runtime 缺陷：模型会对 `this batch / current set / cohort` 过度澄清，部分 goal 边界混淆，并偶发 strict structured output 缺字段。Agent B 已形成 Prompt v2 候选 `d1ba0dc`，确定性相关回归 65 passed；在真实 Provider 重新测量前，Agent A 继续保持 Core handoff freeze。

最新一次 Provider 状态为：

```text
HTTP 403
code=insufficient_user_quota
remaining≈¥0.065264
required precharge≈¥0.080000 / request
```

因此当前准确状态仍是：

```text
Intent          = RELEASE GATE NOT YET PASSED
Tool Selection  = RELEASE GATE NOT YET PASSED
```

不能把余额不足解释成模型质量失败，也不能把此前诊断批次解释成最终 PASS。

## 6. Provider Eval 成本治理

2026-09-24 复盘发现调试期约 `¥48.64` 消耗主要来自重复真实 Provider 请求；按当前服务商约 `¥0.08 / request` 估算，对应约 608 次调用。根因是把完整 60 + 44 Release Gate 反复用于 Prompt 调试，加上分类重跑、超时后的重新执行和 probe 调用。

Provider Eval 现改为：

```text
离线回归
→ 默认 5 Intent + 5 Tool Selection Canary
→ Prompt/Model Bad Case 收敛
→ 仅发布节点执行 60 + 44 Full Gate
→ 相同 runFingerprint 直接 Replay Cache，0 新调用
```

新增硬保护：

- `maxProviderCalls` 在真实 HTTP 请求前执行，Retry 也消耗同一预算；
- `--max-cost-cny` 在调用前做人民币预算检查；
- full release 必须显式 `--full-release-gate`；
- Replay Cache 独立保存在 `data/local/career-provider-gate-cache/`，不会被普通 latest snapshot / dry-run 覆盖；
- 自动定时任务不得继承历史 live-cost 授权，Provider calls 必须保持 0；
- 真实付费 Gate 必须由当前人工会话显式授权。

完整复盘与操作 SOP：`docs/implementation/P1-Provider-Eval-Cost-Budget-Canary-Replay-Cache-Retrospective.md`。

## 7. vNext 1.1 Remaining Criteria

当前只剩：

1. Provider 余额恢复；
2. 人工显式授权一个受成本预算保护的 Prompt v2 Canary；
3. Canary 稳定后执行真实 Intent 60-case Gate；
4. Intent 达到 `>=95%` 且 safety violation = 0 后，再执行 Tool Selection 44-case Gate；
5. 两门均达到 `>=95%` 且 safety violation = 0；
6. 若真实 Gate 暴露 Core Contract / Runtime bad case，交 Agent A 做“失败回归 → 最小修复 → targeted regression”；
7. 两门通过后由 Integration Owner 更新 ROADMAP，将 vNext 1.1 标记 COMPLETE，并才允许切换到 vNext 1.2。

## 8. 当前停止规则

在 Provider 余额不足或没有当轮人工 live-cost 授权时：

- 自动任务 Provider calls 必须为 0；
- 不每小时重复跑 probe 或 104-case cohort；
- 不继续扩 Runtime；
- 不新增 Eval Dataset；
- 不伪造 PASS；
- 不进入 vNext 1.2；
- 不用低价值重构制造 commit。

下一次真实 Provider 质量测量必须先从受预算保护的 Canary 开始；只有 Canary 表明 Prompt/Model 已明显收敛后，才值得执行完整 60 + 44 Release Gate。
