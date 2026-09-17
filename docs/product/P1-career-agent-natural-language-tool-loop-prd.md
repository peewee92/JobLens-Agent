# P1 Career Agent Natural Language + Bounded Tool Loop 产品需求文档

- 状态：Planned / vNext 1.1
- 对应缺口：**2. 自然语言理解 + 多轮 Tool Calling**
- 前置条件：vNext 1.0 Agent Runtime / Checkpoint / Durable HITL / Trajectory Eval Release Gate 全部通过
- 核心目标：让用户可以用自然语言表达求职目标，由单一 Career Agent 在受治理上下文内动态选择并组合成熟 Workflow，而不是要求调用方提前传入固定 `goal`
- 关联 Runtime PRD：`docs/product/P1-career-agent-langgraph-vnext.md`
- 关联 HITL PRD：`docs/product/P1-career-agent-durable-hitl-prd.md`
- 关联 Agent 演进方案：`docs/implementation/P1-Career-Agent-Workflow-First-to-Governed-Agent-Evolution-Plan.md`

---

## 1. 背景与问题

当前 Career Agent 已有：

```text
Governed Context Builder
→ structured goal
→ Tool Registry
→ mature Workflow
```

但调用方必须明确传：

```text
rank_jobs
review_gaps
prepare_job
```

这意味着它还不能自然处理用户真实表达：

> “帮我看看最近这批 AI Agent 岗位，哪些最值得投？如果差距比较大，再告诉我该补什么。”

真正的 Agent 化需要把“下一步调用哪个 Workflow”从调用方转移给 Agent，但不能破坏现有事实、权限、成本、人工决策和 Eval 边界。

---

## 2. 产品目标

### 2.1 一句话目标

> 用户用自然语言表达一个或多个求职目标后，Career Agent 能理解意图、选择合适 Tool、观察 Tool Result、决定是否继续调用、请求澄清或请求人工确认，并在有限轮次内返回证据可追溯的结果。

### 2.2 第一阶段能力边界

第一阶段只开放成熟、粗粒度、read-only / transient Tool：

- `rank_jobs`；
- `review_gaps`；
- `prepare_job`；
- current job / match read tools；
- 必要的 context/readiness query。

第一阶段不开放：

- 自动 Requirement Extraction；
- 自动 MatchReport 生成；
- 自动修改 Profile；
- 自动写 UserFeedback；
- 自动投递；
- 自动联系招聘者。

有 Provider 成本或业务写入的动作必须进入 `PendingAction / Human Gate`。

---

## 3. 用户故事

### US-NL-01：单目标

> “这批岗位里哪些最值得我先投？”

Agent 应识别为 Ranking，不额外调用 Gap / Preparation。

### US-NL-02：多目标

> “先选出最值得投的岗位，再看看这些岗位共同缺什么。”

Agent 应形成：

```text
Ranking
→ Target Cohort proposal
→ Human confirmation
→ Gap
```

### US-NL-03：当前岗位引用

> “这个岗位我面试前重点准备什么？”

如果页面 / Context 有合法 current job，则调用 Preparation；没有则必须询问用户，不猜 Job。

### US-NL-04：模糊请求

> “帮我看看这个怎么样。”

Context 不足时返回 clarification，而不是随机选择 Tool。

### US-NL-05：工具结果不足

> “哪些岗位最值得投？如果都不合适告诉我原因。”

Agent 可以先 Ranking；如果结果为空 / blocked，则基于结构化 blocker 总结，不继续无意义调用。

### US-NL-06：越界请求

> “帮我直接给这 20 个岗位全部投递。”

当前版本必须明确拒绝自动投递，并可建议进入 Preparation / Application Workspace。

---

## 4. 总体执行模型

```text
User Message
   ↓
Governed Context Builder
   ↓
Intent Understanding
   ↓
Agent State
   ↓
Model Decision
   ├─ Tool Call
   ├─ Ask Human
   ├─ Ask Clarification
   └─ Finish
        ↑
        │
    Tool Result
```

### 4.1 单一 Career Agent

第一阶段仍然只允许一个 Agent。

不拆：

- Ranking Agent；
- Gap Agent；
- Resume Agent；
- Interview Agent；
- Critic Agent。

业务能力继续由成熟 Workflow 提供。

---

## 5. Natural Language Intent Contract

建议第一层结构化输出：

```text
CareerIntent
├── goals[]
│   ├── rank_jobs
│   ├── review_gaps
│   ├── prepare_job
│   ├── review_application
│   └── unknown
├── referenced_job_ids[]
├── current_job_required
├── needs_clarification
├── clarification_question
├── unsupported_request
├── confidence
└── reasoning_summary   # 短结构化说明，不保存模型私有思维链
```

### 5.1 明确禁止输出 Chain of Thought

`reasoning_summary` 只允许简短可审计理由，例如：

```text
“用户要求先排序，再分析共同差距。”
```

不得持久化模型私有思维过程。

---

## 6. Intent 规则

### FR-NL-01：Grounded Entity Resolution

Job 引用解析顺序：

1. 显式 Job ID；
2. 当前页面 current Job；
3. 当前 Run 已冻结的 Job scope；
4. 否则 clarification。

禁止只根据模糊岗位名称自动选择可能错误的 Job。

### FR-NL-02：多目标保留顺序

用户表达：

> “先 A，再 B”

Intent 必须保留顺序，不把多目标压成一个 goal。

### FR-NL-03：不支持请求

例如：

- 自动投递；
- 自动联系 HR；
- 修改人工 Review；
- 绕过 evidence gate。

必须返回 structured unsupported action，而不是伪造 Tool。

---

## 7. Tool Registry 设计

Tool 必须是稳定业务 Workflow，不是内部函数。

建议第一阶段 Tool：

```text
get_current_context
rank_jobs
get_current_match_report
review_gaps
prepare_job
get_application_workspace   # vNext 1.2 后开放
```

每个 Tool 定义至少包含：

```text
name
description
input_schema
output_schema
side_effect_class
provider_cost_class
human_gate_requirement
timeout_class
idempotency_class
```

### 7.1 Side Effect Class

```text
read_only
transient_compute
provider_compute
business_write
external_action
```

vNext 1.1 第一阶段只允许前两类自动执行。

---

## 8. Bounded Tool Loop

建议第一版默认限制：

```text
max_turns = 6
hard_max_turns = 10
max_tool_calls = 8
max_same_tool_consecutive = 2
max_runtime_seconds = 90
```

参数必须可配置，但不得由模型自行扩大。

### FR-LOOP-01：每轮决策类型

```text
call_tool
ask_clarification
request_human_action
finish
```

禁止自由生成不存在的控制动作。

### FR-LOOP-02：Unknown Tool

如果模型请求不存在 Tool：

```text
unknown_tool
```

记录 Agent error，允许最多一次重新规划；再次出现则 fail closed。

### FR-LOOP-03：重复调用检测

同一 Tool + 同一规范化参数 + 相同输入事实 fingerprint 连续重复：

- 第 2 次允许作为显式 retry，仅 transient error 时；
- 第 3 次禁止，返回 loop_detected。

### FR-LOOP-04：No Progress Detection

如果连续两个 Tool Result 的：

- state fingerprint 不变；
- blocker 不变；
- 没有新事实；

Agent 不得继续机械调用，必须 clarification / human action / finish。

---

## 9. Tool Result Contract

Tool Result 统一为：

```text
AgentToolResult
├── status
│   ├── success
│   ├── blocked
│   ├── unavailable
│   └── failed
├── summary
├── data_refs
├── grounding_refs
├── blockers
├── side_effects
├── provider_calls
├── retryable
└── result_fingerprint
```

Agent 不允许只从自由文本 Tool Output 判断下一步。

---

## 10. Error Classification

至少区分：

| Error | 策略 |
|---|---|
| invalid tool params | 允许模型修正参数 1 次 |
| unknown tool | 重新规划 1 次，之后 fail |
| permission / release gate | fail closed / blocked |
| stale state | 中止旧 Run |
| transient network | bounded retry |
| Provider 429/503/504/timeout | existing bounded retry policy |
| workflow invariant | no retry，记录 Trace |
| user clarification required | interrupt / ask user |
| cost/effect approval required | PendingAction |
| context budget exceeded | compact / summarize refs，不丢事实 identity |

---

## 11. Context Budget

Agent Context 必须分层：

```text
P0: Run goal / current step / IDs / versions / blockers
P1: Job summaries / Ranking summary / Gap summary
P2: Relevant Evidence refs / Requirement refs
P3: 需要时按 Tool 重新读取的详细事实
```

禁止每轮反复塞：

- 20 个完整 JD；
- 完整 Resume；
- 全量 Requirement；
- 全量 Trace。

### 11.1 Compaction 原则

压缩时必须保留：

- entity IDs；
- version；
- fingerprint；
- pending human action；
- unresolved blocker；
- already executed Tool calls。

---

## 12. Clarification UX

Agent 只有在缺少关键事实时才询问。

好的 clarification：

> “你说‘这个岗位’，但当前没有选中的岗位。你想准备哪一个？”

不好的 clarification：

> “请告诉我更多信息。”

每次 clarification 应包含：

- 缺什么；
- 为什么必须知道；
- 用户可选的最小答案格式。

---

## 13. Human / Cost Gate

模型不能直接执行：

- Provider 成本动作；
- business write；
- external action。

必须生成：

```text
PendingAction
├── action_type
├── tool
├── normalized_params
├── why
├── cost_class
├── expected_provider_calls
├── business_writes
├── external_effects
├── fact_fingerprint
└── expires_at
```

由 Durable HITL Runtime 负责确认和 Resume。

---

## 14. Trace

每个 Agent turn 至少记录：

```text
thread_id
run_id
turn_index
model/provider/version
intent
selected_action
tool_name
tool_args_fingerprint
tool_result_fingerprint
error_class
retry_count
provider_calls
latency
terminal_reason
```

必须能回答：

- 为什么调用这个 Tool；
- 为什么又调用下一个 Tool；
- 哪里发生了 retry；
- 是否进入重复循环；
- 是否绕过人工门禁。

---

## 15. Eval 体系

### 15.1 Intent Eval：至少 60 Case

覆盖：

- 单目标 15；
- 多目标 15；
- current job / pronoun 10；
- clarification 10；
- unsupported / unsafe 10。

### 15.2 Tool Selection Eval：至少 40 Case

验证：

- correct Tool；
- forbidden Tool；
- unnecessary Tool；
- wrong Job scope；
- wrong argument；
- no-tool answer when facts sufficient。

### 15.3 Multi-turn Trajectory Eval：至少 30 Case

必须覆盖：

```text
Ranking → Finish
Ranking → HITL → Gap
Ranking → Gap → Preparation
Tool empty → clarification
invalid params → corrected retry
transient error → bounded retry
unknown tool → replan → recover/fail
same tool loop → stopped
stale → terminate
cost action → PendingAction
```

---

## 16. Release Gate

vNext 1.1 只有满足以下门槛才能进入主产品：

- Intent goal exact / acceptable accuracy ≥ 95%；
- unsafe / unsupported request 自动执行率 = 0；
- unknown tool unrecovered rate = 0；
- unauthorized business writes = 0；
- human decision auto-sign = 0；
- max turn violation = 0；
- infinite/repeated loop = 0；
- required grounding coverage = 100%；
- ≥30 trajectory cases 全通过；
- Provider / Tool Trace 可回放；
- P95 Tool Loop latency 有基线并可解释。

---

## 17. Web / Chat UX

vNext 1.1 才开始加入真正统一 Agent 对话入口。

最小界面：

```text
Career Agent Chat
├── User message
├── Agent current plan summary
├── Tool execution status
├── Blocker / clarification
├── Human approval card
├── Grounded result
└── “查看依据”
```

UI 不展示模型内部 Chain of Thought。

允许展示：

- “正在读取当前 Ranking”；
- “需要你确认目标岗位”；
- “正在分析共同 Skill Gap”；
- “当前信息不足，需要你选择一个岗位”。

---

## 18. 非目标

第一阶段明确不做：

- Multi-Agent；
- Autonomous Planner 长计划；
- long-term memory；
- background autonomous execution；
- auto-apply；
- recruiter messaging；
- Web browsing Agent；
- 把所有 Backend API 变成 Tool。

---

## 19. DoD

- [ ] Intent schema / router；
- [ ] 60+ Intent Eval；
- [ ] 动态 Tool Selection；
- [ ] bounded multi-turn loop；
- [ ] maxTurns / timeout / cancellation；
- [ ] unknown tool / invalid params / duplicate loop guard；
- [ ] context budget / compaction；
- [ ] PendingAction 与 Durable HITL 接通；
- [ ] 30+ trajectory eval；
- [ ] Trace / replay；
- [ ] 最小 Chat UI；
- [ ] 不破坏 JobLens evidence / release gate；
- [ ] 不引入 Multi-Agent。
