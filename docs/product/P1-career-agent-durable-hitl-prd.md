# P1 Career Agent Durable Human-in-the-loop 产品需求文档

- 状态：Planned / vNext 1.0 强制组成部分
- 对应缺口：**3. Durable Human-in-the-loop**
- 目标阶段：vNext 1.0 / LG-2
- 前置条件：Agent Runtime Boundary、LangGraph State、持久化 Checkpoint 已可用
- 核心目标：把 JobLens 现有分散在页面、URL、localStorage 和单次 API 请求中的人工确认，升级为可跨请求、可恢复、可审计、幂等的 Runtime 状态边界
- 关联 Runtime PRD：`docs/product/P1-career-agent-langgraph-vnext.md`
- 关联实施方案：`docs/implementation/P1-Career-Agent-LangGraph-Runtime-Integration-Plan.md`

---

## 1. 背景与问题

JobLens 已经有大量必须由用户本人决定的边界：

- Profile / Evidence 确认；
- Requirement Review / Final Decision；
- UserFeedback；
- Target Cohort 选择；
- Evidence 是否属于自己的真实经历；
- Provider 成本动作；
- 未来 Application 状态与外部动作。

当前这些交互虽然存在，但主要由页面、API 和局部状态分别承载。对于单步 Workflow 没问题，但当 Career Agent 进入长流程后，会出现新的产品问题：

```text
Agent 完成 Ranking
→ 需要用户确认 Target Cohort
→ 用户关掉页面
→ 第二天回来
→ 系统能否知道停在哪里？
→ 能否继续原 Run？
→ 这期间 Profile 是否已经变化？
→ 同一个 Approve 重复点两次会不会重复执行 Gap？
```

因此需要把 Human Gate 从“页面交互”提升为 Runtime 的正式状态。

---

## 2. 产品目标

### 2.1 一句话目标

> 用户可以在 Career Agent 长流程中安全地暂停、离开、回来、确认或修改关键决策，并从原执行位置继续；系统不会因为旧状态、重复点击或页面刷新而重复执行业务动作。

### 2.2 第一阶段只验证一个人工边界

第一阶段只支持：

```text
Ranking
→ Target Cohort Proposal
→ Durable Interrupt
→ Approve / Edit / Reject
→ Resume
→ Skill Gap
```

选择 Target Cohort 的原因：

- 它是真实用户职业决策；
- 当前已有 Ranking / Gap Workflow；
- 不需要自动写 UserFeedback；
- 可以完整验证 Interrupt / Resume / stale / idempotency；
- 不需要第一阶段引入 Provider 调用。

---

## 3. 非目标

第一阶段不做：

- 自动替用户 Approve；
- 自动提交 UserFeedback；
- 自动修改 Profile / SearchIntent；
- 自动执行 Requirement Final Decision；
- 自动投递职位；
- 自动联系招聘者；
- Multi-Agent handoff；
- 跨设备实时协同编辑；
- 长期 Memory。

---

## 4. 核心用户故事

### US-HITL-01：等待确认

作为用户，我希望 Agent 完成岗位排序后暂停，并明确告诉我：

- 推荐了哪些目标岗位；
- 为什么需要我确认；
- 我可以 Approve、Edit 还是 Reject；
- 确认后系统会做什么。

### US-HITL-02：关闭页面后继续

作为用户，我希望在 Agent 等待确认时关闭浏览器，稍后重新打开还能看到原 Run 的 pending action，而不是重新执行 Ranking。

### US-HITL-03：编辑建议

作为用户，我希望可以删掉或增加本 Run 范围内的岗位，再继续 Skill Gap 分析。

### US-HITL-04：拒绝

作为用户，我希望 Reject 后 Run 正常结束，并且 Agent 不继续执行 Gap。

### US-HITL-05：事实变化后阻止旧 Run

作为用户，我希望如果暂停期间 Profile / SearchIntent / MatchReport 已更新，旧 Run 不会把旧结果和新事实混在一起继续执行。

### US-HITL-06：防止重复点击

作为用户，我希望网络重试或重复点击 Approve 不会重复执行下游 Workflow。

---

## 5. Runtime 状态机

第一阶段冻结以下状态：

```text
created
  ↓
running
  ↓
interrupted
  ├─ approve/edit → resuming → running → completed
  ├─ reject       → cancelled
  ├─ stale        → stale
  └─ error        → failed
```

完整终态：

```text
completed
cancelled
blocked
failed
stale
```

### 5.1 状态语义

- `created`：Run 已创建，未开始执行 Graph；
- `running`：正在执行节点；
- `interrupted`：等待人工决定；
- `resuming`：人工决定已成功消费，正在从 Checkpoint 恢复；
- `completed`：Graph 正常结束；
- `cancelled`：用户显式 Reject / Cancel；
- `blocked`：业务 readiness / release gate 不满足；
- `stale`：暂停期间关键业务事实发生变化；
- `failed`：Runtime / Checkpoint / invariant 异常。

---

## 6. Interrupt 数据模型

建议结构：

```text
HumanInterrupt
├── interrupt_id
├── thread_id
├── run_id
├── type
├── status
├── created_at
├── expires_at?
│
├── reason
├── proposed_action
├── allowed_actions
│
├── fact_snapshot
│   ├── profile_id
│   ├── profile_version
│   ├── search_intent_id
│   ├── search_intent_version
│   └── match_fingerprint
│
└── payload
    ├── proposed_job_ids
    ├── job_summaries
    ├── ranking_positions
    ├── recommendation_summaries
    └── next_step_description
```

### 6.1 Interrupt Payload 只保存最小必要信息

可以保存：

- IDs；
- versions；
- ranking position；
- title / company；
- recommendation / blocker summary；
- fact fingerprint。

禁止保存：

- API Key；
- raw Resume；
-完整 raw JD；
- 未发布 Requirement 草稿；
- 长 Tool Output。

---

## 7. Human Decision 数据模型

```text
HumanDecision
├── action_id
├── interrupt_id
├── decision       approve | edit | reject
├── selected_job_ids?
├── submitted_at
└── actor          explicit_user
```

### 7.1 Approve

```text
selected_job_ids = proposed_job_ids
```

### 7.2 Edit

必须满足：

- 1..10 个 Job；
- Job 属于本 Run 初始 `requested_job_ids`；
- Resume 时仍存在 current MatchReport；
- 不允许 Agent 自动补入 Run 外岗位。

### 7.3 Reject

- Run → `cancelled`；
- 不执行 Gap；
- 不写 UserFeedback；
- 不把 Reject 偷换成“不喜欢这些岗位”的业务事实。

---

## 8. 幂等设计

### FR-HITL-01：同一 Interrupt 只能成功消费一次

唯一消费身份：

```text
thread_id + interrupt_id + action_id
```

重复 Resume：

- 若同一 `action_id` 已成功：返回原 Resume 结果或 `already_resumed`；
- 不得重复执行 Gap；
- 不得重复写 Runtime checkpoint；
- 不得改变第一次成功决策。

### FR-HITL-02：冲突决策

如果已经 `approve` 成功，再收到新的 `reject`：

```text
409 decision_conflict
```

不得覆盖原决定。

---

## 9. Stale State Protection

Resume 前必须重新读取当前事实并比较：

```text
Profile ID + version
SearchIntent ID + version
selected jobs current MatchReport identity / fingerprint
Requirement release eligibility
```

出现任一变化：

```text
state_stale
```

并进入 `stale` 终态。

### 9.1 明确禁止

禁止：

```text
旧 Checkpoint Profile v1
+
当前 MatchReport Profile v2
→ 继续 Gap
```

也禁止“自动迁移”旧 Run 到新事实。

### 9.2 用户体验

提示：

> 你的职业背景或岗位匹配结果在等待确认期间发生了变化。为了避免把旧判断和新事实混在一起，请重新开始这次分析。

提供：

- 查看变化原因；
- 新建 Run；
- 返回当前 Ranking。

---

## 10. API 需求

建议 Runtime API：

```text
POST /api/v1/career-agent/runs
GET  /api/v1/career-agent/runs/{thread_id}
POST /api/v1/career-agent/runs/{thread_id}/resume
POST /api/v1/career-agent/runs/{thread_id}/cancel
```

### 10.1 GET state

至少返回：

```json
{
  "threadId": "...",
  "runId": "...",
  "status": "interrupted",
  "currentStep": "target_cohort_confirmation",
  "interrupt": {},
  "terminalResult": null,
  "blockers": []
}
```

### 10.2 Resume

```json
{
  "interruptId": "...",
  "actionId": "client-generated-idempotency-key",
  "decision": "edit",
  "selectedJobIds": ["job_1", "job_3"]
}
```

---

## 11. Web 交互需求

第一阶段不要求聊天 UI。

需要一个最小 Run 页面：

```text
Agent Run
├── 当前状态
├── 已完成步骤
├── 当前人工确认卡
├── Approve
├── Edit Selection
├── Reject
└── 技术详情（折叠）
```

### 11.1 人工确认卡必须展示

- 本次分析目标；
- proposed jobs；
- Ranking position；
- 推荐理由摘要；
- “确认后将分析这些岗位的共同 Skill Gap”；
- 明确告诉用户这是职业选择，不会自动写 UserFeedback。

### 11.2 Resume 反馈

点击后 UI 必须区分：

```text
正在恢复原 Run
已完成
状态已过期，需要重新开始
已经处理过
执行失败
```

---

## 12. Error Classification

| 类型 | 行为 |
|---|---|
| invalid decision payload | 4xx，fail fast |
| selected job out of scope | 422 / structured blocker |
| stale domain state | 进入 stale，禁止继续 |
| duplicate action | 返回已有结果 / already_resumed |
| conflicting decision | 409 |
| checkpoint unavailable | runtime failed |
| transient persistence error | bounded retry |
| user reject | 正常 cancelled，不记 error |
| business readiness blocker | blocked，不重试 |

---

## 13. Trace / Audit

每次 HITL 至少记录：

```text
trace_id
thread_id
run_id
interrupt_id
action_id
interrupt_created_at
decision_received_at
resume_started_at
resume_completed_at
fact_snapshot_before
fact_snapshot_on_resume
stale_check_result
terminal_state
```

不能记录：

- secret；
- raw Resume；
- 不必要的完整 JD。

---

## 14. Eval 最小集

至少 20 条 deterministic cases：

### Happy Path

1. rank → interrupt；
2. approve → gap → complete；
3. edit → gap → complete；
4. reject → cancelled；

### Persistence

5. interrupt 后 GET state 可读；
6. 新 Runtime instance 可恢复 pending state；
7. browser-like reconnect 后状态一致；

### Idempotency

8. duplicate approve；
9. duplicate edit；
10. same action_id replay；
11. approve 后 reject conflict；

### Stale

12. Profile version changed；
13. SearchIntent changed；
14. MatchReport changed；
15. selected MatchReport missing；

### Guard

16. selected job out of original scope；
17. empty edit selection；
18. >10 edit selection；
19. Provider call remains 0；
20. business state write remains 0。

---

## 15. Release Gate

Durable HITL 只有满足以下条件才算完成：

- approve / edit / reject 全部可跨请求 Resume；
- 服务重启后 pending Run 可恢复；
- duplicate resume side effect = 0；
- stale continuation = 0；
- user decision auto-sign = 0；
- provider calls = 0；
- business-state writes = 0；
- 20/20 trajectory / HITL cases 通过；
- Trace 能重建 Interrupt → Decision → Resume；
- Web 最小入口可真实演示关闭页面后恢复。

---

## 16. 后续扩展顺序

第一阶段 Target Cohort HITL 成功后，按风险逐步扩展：

```text
1. Provider / Cost PendingAction
2. Profile / Evidence write confirmation
3. Application status change confirmation
4. 外部系统动作 confirmation
```

Requirement Final Decision 与 UserFeedback 已有独立治理边界，不因为有 LangGraph 就自动迁移或放松权限。

---

## 17. DoD

- [ ] Persistent Checkpoint 已接入；
- [ ] Interrupt 状态可查询；
- [ ] Approve / Edit / Reject API 完整；
- [ ] Duplicate Resume 幂等；
- [ ] Stale Guard 完整；
- [ ] Cancel 完整；
- [ ] Trace 完整；
- [ ] 20+ Eval；
- [ ] Web 最小演示；
- [ ] 不改变业务事实边界；
- [ ] README / 架构文档在实现完成后更新。
