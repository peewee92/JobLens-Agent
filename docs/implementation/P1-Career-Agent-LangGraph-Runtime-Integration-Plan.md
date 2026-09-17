# JobLens Career Agent：LangGraph Runtime 融合与演进方案

> 文档类型：P1 Career Agent 实施规划 / 架构演进方案
> 状态：Planned，尚未表示 LangGraph 已在 JobLens 生产路径中完成
> 适用范围：`services/backend/app/agent` 及 Career Agent 相关 Eval / Trace
> 关联文档：
> - `docs/product/P1-career-agent-langgraph-vnext.md`（vNext 1.0 Agent Runtime 主 PRD）
> - `docs/product/P1-career-agent-durable-hitl-prd.md`（vNext 1.0 Durable HITL 专项 PRD）
> - `docs/product/P1-career-agent-natural-language-tool-loop-prd.md`（vNext 1.1 自然语言 + 多轮 Tool Calling PRD）
> - `docs/product/P1-job-search-execution-layer-prd.md`（vNext 1.2 求职执行层 PRD）
> - `docs/implementation/P1-JobLens-LangGraph-Runtime-Execution-Plan.md`（LG-0～LG-4 实施顺序、工时、DoD 与 trajectory eval 最小集）
> - `docs/product/P1-joblens-mcp-pi-extension.md`（vNext 1.3 MCP / Pi 外部 Agent 集成需求）
> - `docs/decisions/0004-llm-workflow-agent-boundary.md`
> - `docs/implementation/P1-Career-Agent-Workflow-First-to-Governed-Agent-Evolution-Plan.md`
> - `docs/architecture/SYSTEM-ARCHITECTURE.md`
> - `docs/architecture/EVAL-AND-TRACE.md`

---

## 1. 目标与结论

JobLens 不应为了招聘关键词把整个系统“改造成 LangGraph”。

当前已经形成的架构边界是正确的：

```text
LLM Capability
    ↓
Domain Workflow
    ↓
Career Agent
```

其中：

- Profile Extraction、Requirement Extraction、Semantic Match 等能力保持独立可评测；
- Eligibility、Ranking、Gap、Preparation 等确定性或半确定性业务逻辑继续由 Domain Workflow / Application Service 实现；
- Career Agent 只负责理解目标、组织上下文、选择 Workflow、控制执行状态、处理中断与恢复、汇总结果；
- Agent 不绕过 `JobRequirement`、Profile Evidence、UserFeedback 等事实底座重新自由解释业务事实。

LangGraph 在 JobLens 中最合适的定位不是“新的业务框架”，而是：

> **Career Agent 的可插拔 Stateful / Durable Runtime，实现显式 State、Conditional Routing、Checkpoint、Interrupt / Resume、Human-in-the-loop 和执行轨迹评测。**

目标架构：

```text
                         User
                           │
                           ▼
                  Career Agent API
                           │
                           ▼
                 Governed Context Builder
                           │
                           ▼
                    AgentRuntime
                           │
             ┌─────────────┴─────────────┐
             │                           │
             ▼                           ▼
      Workflow Runtime            LangGraph Runtime
   （简单/确定性路径）          （长流程/可恢复路径）
             │                           │
             └─────────────┬─────────────┘
                           ▼
                    Tool Registry
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   Ranking Workflow   Gap Workflow      Preparation Workflow
        │                  │                  │
        └──────────────────┴──────────────────┘
                           ▼
             Versioned Domain Facts / DB
```

核心原则：

> **能确定性执行的地方继续使用 Workflow；只有当任务需要长流程状态、条件路由、人工中断和恢复时才进入 LangGraph Runtime。**

---

## 2. 为什么 JobLens 适合引入 LangGraph

JobLens 已经不是单轮聊天问题，而是存在真实的长流程状态：

```text
Confirmed Profile
→ SearchIntent
→ Job Pool
→ Released JobRequirement
→ MatchReport
→ Ranking
→ UserFeedback
→ Target Cohort
→ Skill Gap
→ Action Plan
→ Job Preparation
```

如果统一入口要支持用户自然表达：

> “帮我分析这批 AI Agent 岗位，先告诉我最值得投哪些，再帮我看看主要能力差距。”

Agent 需要解决的不只是 Tool Calling，而是：

1. 当前 Profile / SearchIntent 是否已经达到 Release Gate；
2. 目标岗位是否已经具备 current Requirement / MatchReport；
3. 当前请求应该走 Ranking、Gap 还是 Preparation；
4. 中间是否需要用户确认 Target Cohort；
5. 用户确认以后能否从原状态继续，而不是全部重跑；
6. Provider / 网络 / 参数 / 权限 / 业务不变量错误如何分流；
7. 浏览器关闭或服务重启后是否可以恢复；
8. 如何评测 Agent 是否走了正确执行轨迹，而不只看最后一句话。

这些问题正好属于 Runtime，而不是业务 Workflow 本身。

---

## 3. 明确不做什么

### 3.1 不重写现有成熟 Workflow

禁止把现有：

```text
rank_match_reports()
target_cohort_gaps()
job_preparation()
Eligibility
Semantic Match
Requirement Extraction
```

复制到 LangGraph Node 中重新实现。

LangGraph Node 只负责：

- 读取受治理上下文；
- 调用现有 Tool / Workflow；
- 根据结构化结果更新 Agent State；
- 决定下一步状态转换。

### 3.2 不绕过事实与 Release Gate

Agent 不能：

- 绕过 current confirmed Profile；
- 绕过 released JobRequirement 直接把 raw JD 塞给模型重新解释；
- 绕过 accepted baseline / release eligibility；
- 在 Evidence 不完整时假装已经有事实；
- 把 Match Score 描述成录用概率。

### 3.3 不因 LangGraph 引入 Multi-Agent

P1 第一阶段仍然是：

```text
Single Career Agent
+
Stable Workflows
+
Governed Tool Registry
+
LangGraph Runtime
```

不新增：

```text
Planner Agent
Research Agent
Resume Agent
Critic Agent
```

除非未来某个角色真正拥有独立生命周期、Context、Tool、Eval 和资源隔离需求。

### 3.4 不让 Agent 自主提交用户职业决策

以下状态必须继续属于用户：

```text
interested
maybe
not_interested
Target Cohort confirmation
Final Review decision
```

Agent 可以建议，不能代签。

---

## 4. Runtime 分层设计

建议先抽象统一 Runtime 协议，再增加 LangGraph 实现，而不是让上层 API 直接依赖 LangGraph 类型。

概念接口：

```python
class AgentRuntime(Protocol):
    def run(self, request: AgentRunRequest) -> AgentRunResult: ...
    def resume(self, thread_id: str, decision: HumanDecision) -> AgentRunResult: ...
    def get_state(self, thread_id: str) -> AgentStateSnapshot: ...
    def cancel(self, thread_id: str) -> None: ...
```

实现：

```text
AgentRuntime
├── WorkflowCareerAgentRuntime
│   └── 适合简单、确定性、无需 checkpoint 的单轮路径
└── LangGraphCareerAgentRuntime
    └── 适合长流程、条件路由、HITL、暂停恢复
```

这样可以保留一个非常重要的工程能力：

> **不是所有 Agent 请求都必须经过 Graph。**

例如“查看这个岗位当前 MatchReport”可以走简单 Workflow Runtime；“分析一批岗位 → 选 Target Cohort → 人工确认 → 分析 Gap”才进入 LangGraph。

---

## 5. Agent State 设计

LangGraph State 不应只是 `messages`。

建议显式建模 Career Agent 执行需要的最小事实引用和运行状态：

```text
CareerAgentState
├── identity
│   ├── thread_id
│   ├── run_id
│   └── request_id
│
├── released_context
│   ├── profile_id
│   ├── profile_version
│   ├── search_intent_id
│   └── search_intent_version
│
├── job_scope
│   ├── job_ids
│   ├── current_job_id
│   ├── requirement_versions
│   └── match_report_ids
│
├── orchestration
│   ├── user_goal
│   ├── current_step
│   ├── selected_route
│   ├── tool_results
│   └── pending_approval
│
├── user_decisions
│   ├── selected_target_job_ids
│   └── explicit_feedback_ids
│
├── reliability
│   ├── retry_count
│   ├── last_error_class
│   ├── last_error_code
│   └── cancelled
│
└── trace
    ├── trace_id
    ├── started_at
    └── checkpoint_version
```

### State 只保存引用，不复制事实源

例如：

```text
profile_id + version
```

优于：

```text
把完整 Profile JSON 永久复制进每个 checkpoint
```

原因：

- 避免状态无限膨胀；
- 避免复制出第二套事实源；
- Resume 时可以重新验证 released identity 是否仍然有效；
- Profile / Requirement 已版本化，引用版本即可审计。

### Resume 前必须做 stale check

如果暂停期间：

```text
Profile v8 → v9
```

旧 Thread 不得默认继续使用 v8 做新的职业建议。

恢复时必须：

```text
checkpoint identity
vs
current released identity
```

若不一致：

```text
fail closed
→ state_stale
→ 要求用户重新确认或新建 Run
```

---

## 6. 第一条 LangGraph Vertical Slice

第一版不要覆盖整个 Career Agent。

只实现一个真正能证明 LangGraph 价值的端到端 Slice：

> **“分析一批岗位哪些最值得投，并基于用户确认的目标岗位分析主要 Skill Gap。”**

Graph：

```text
START
  ↓
load_context
  ↓
validate_release_gate
  ↓
context usable?
  ├── NO → blocked_response → END
  │
  └── YES
        ↓
validate_job_scope
        ↓
match reports ready?
  ├── NO → readiness_response → END
  │
  └── YES
        ↓
rank_jobs
        ↓
propose_target_cohort
        ↓
interrupt_for_target_confirmation
        ↓
     HUMAN
    /  |   \
approve edit reject
   │     │    │
   └──┬──┘    └→ cancelled_response → END
      ↓
resume
      ↓
validate_confirmed_target_cohort
      ↓
analyze_skill_gap
      ↓
build_grounded_final_answer
      ↓
END
```

### 为什么选这条 Slice

它同时覆盖：

- Governed Context；
- Conditional Routing；
- Existing Workflow Tool；
- State；
- Checkpoint；
- Interrupt；
- Resume；
- Human-in-the-loop；
- Fail-closed；
- Grounded Final Answer；
- Trajectory Eval。

而且直接对应 JobLens 用户价值，不是为了演示框架而构造的玩具场景。

---

## 7. Node 与 Workflow 的职责边界

建议 Node 设计：

| Node | 只负责什么 | 不负责什么 |
|---|---|---|
| `load_context` | 调用现有 Context Builder | 不重新提取简历 |
| `validate_release_gate` | 检查 current released context | 不修改 Profile |
| `validate_job_scope` | 确认 job IDs 与当前事实可用 | 不重新抓取岗位 |
| `rank_jobs` | 调用 Ranking Workflow | 不自己计算 Match |
| `propose_target_cohort` | 根据 Ranking 结果形成候选建议 | 不替用户提交 Feedback |
| `interrupt_for_target_confirmation` | 创建人工确认边界 | 不默认 approve |
| `validate_confirmed_target_cohort` | 验证人类选择是否合法且 current | 不扩张用户选择范围 |
| `analyze_skill_gap` | 调用 Target Cohort Gap Workflow | 不重新读 raw JD |
| `build_grounded_final_answer` | 汇总已经存在的结构化事实 | 不创造缺失 Evidence |

---

## 8. Human-in-the-loop 设计

LangGraph 的 interrupt / resume 适合解决 JobLens 已存在但此前由页面 / API 分散承载的“人工决策边界”。

### 第一版审批对象

```text
Target Cohort Proposal
```

Agent 可以建议：

```text
推荐将以下 5 个岗位作为当前目标岗位：
- A
- B
- C
- D
- E
```

用户可以：

```text
Approve
Edit selection
Reject
```

### Human Decision 必须结构化

禁止只保存：

```text
"looks good"
```

建议结构：

```json
{
  "decision": "approve | edit | reject",
  "selectedJobIds": ["..."],
  "actor": "user",
  "decidedAt": "...",
  "checkpointVersion": 3
}
```

### 防重复 Resume

同一人工 Decision 必须具备幂等约束。

例如：

```text
(thread_id, checkpoint_version, decision_id)
```

已经消费过的 decision 再次提交：

```text
→ return existing result / conflict
→ 不重复执行后续写操作
```

---

## 9. Checkpoint / Durable Execution

第一阶段至少验证三个恢复场景：

### Case A：等待用户确认时浏览器关闭

```text
rank_jobs
→ interrupt
→ 浏览器关闭
→ 重新打开
→ thread_id 恢复
→ 显示待确认 Target Cohort
```

不得重新运行 Ranking。

### Case B：服务进程重启

```text
checkpoint persisted
→ backend restart
→ resume(thread_id)
→ 从最近 durable boundary 继续
```

### Case C：事实版本变化

```text
interrupt at Profile v8
→ 用户修改 Profile → v9
→ resume old thread
→ stale check fails
→ 不继续 Gap 分析
```

这比“能保存聊天记录”更能证明真正的 Agent Runtime 能力。

---

## 10. Error Classification 与 Retry

LangGraph 不应该被用成无限循环重试器。

统一错误分类：

```text
AgentRuntimeError
├── transient_network
├── provider_rate_limit
├── provider_unavailable
├── invalid_model_output
├── invalid_tool_arguments
├── permission_denied
├── release_gate_blocked
├── stale_state
├── business_invariant_violation
└── cancelled
```

策略：

| 错误 | 策略 |
|---|---|
| transient network | bounded retry + backoff |
| provider rate limit | bounded retry / defer |
| provider unavailable | fail / defer，不能无限重试 |
| invalid model output | 允许有限 repair retry |
| invalid tool arguments | 返回结构化错误给路由层重新决策，限制次数 |
| permission denied | 立即 fail-closed |
| release gate blocked | 立即停止，返回明确 blocker |
| stale state | 禁止继续旧 Run |
| business invariant violation | 立即停止并记录 Trace |
| cancelled | 终止，不执行后续节点 |

默认要求：

```text
max_turns
max_tool_calls
max_retries_per_error_class
max_provider_calls
```

全部可配置且进入 Trace。

---

## 11. 自然语言与多轮 Tool Calling 必须在 Runtime Release Gate 之后加入

第一条 Slice 只证明 Runtime，不让 LLM 同时控制路由和长流程状态。开发顺序固定为：

### vNext 1.0

入口仍使用结构化 Goal：

```text
ANALYZE_BATCH_AND_GAPS
```

重点验证：

```text
State
Checkpoint
Interrupt / Resume
Durable HITL
Stale Guard
Idempotency
Trajectory Eval
```

### vNext 1.1

只有 vNext 1.0 Release Gate 通过后，再增加：

```text
Natural Language Query
        ↓
Career Intent
        ↓
Dynamic Tool Selection
        ↓
Bounded Multi-turn Tool Loop
        ↓
Workflow Runtime / LangGraph Runtime
        ↓
Tool Result
        ↓
Tool / Ask Human / Finish
```

例如：

```text
“这个岗位值不值得投？”
→ INSPECT_SINGLE_JOB
→ Simple Workflow Runtime

“帮我分析这 20 个岗位，选最值得投的并看看主要差距”
→ ANALYZE_BATCH_AND_GAPS
→ LangGraph Runtime
→ HITL
→ Skill Gap
```

路由结果必须结构化，Tool Loop 也必须受 `maxTurns / maxToolCalls / timeout / duplicate-call / unknown-tool` 约束。不要让路由 Prompt 直接执行业务，也不要在 Runtime 稳定前同时引入 LLM Router 变量。

详细需求见：`docs/product/P1-career-agent-natural-language-tool-loop-prd.md`。

---

## 12. Agent Eval：评测执行轨迹，而不只评最终答案

LangGraph 集成的真正价值之一，是把 Agent Runtime 本身变成可评测对象。

建议新增：

```text
services/backend/app/evals/career_agent_trajectory.py
services/backend/tests/test_career_agent_trajectory_eval.py
data/evals/career-agent/
```

### Case 示例 1：正常批量分析

输入：

```text
“帮我从这 10 个岗位中选最值得投的 3 个，再分析能力差距。”
```

Expected Trajectory：

```text
load_context
→ validate_release_gate
→ validate_job_scope
→ rank_jobs
→ propose_target_cohort
→ interrupt
→ resume
→ analyze_skill_gap
→ final
```

Forbidden：

```text
profile_extraction
raw_jd_semantic_match
write_user_feedback_without_confirmation
```

### Case 示例 2：Profile 未发布

Expected：

```text
load_context
→ validate_release_gate
→ blocked_response
→ END
```

Forbidden：

```text
rank_jobs
analyze_skill_gap
```

### Case 示例 3：Resume 时 Profile 已变更

Expected：

```text
resume
→ stale_check
→ state_stale
→ END
```

不得继续执行 Gap。

### 关键指标

至少统计：

```text
Route Accuracy
Tool Selection Accuracy
Trajectory Pass Rate
Forbidden Tool Call Rate
Grounding Reference Pass Rate
HITL Boundary Pass Rate
Resume Correctness
Stale-state Block Rate
Max-turn Violation Rate
Provider Call Count
P50 / P95 Latency
Token / Cost per Run
```

Release Gate 第一阶段可以要求：

```text
Forbidden Tool Call Rate = 0
HITL Boundary Pass Rate = 100%
Stale-state Block Rate = 100%
Deterministic trajectory cases = 100%
```

语义路由上线后再增加容许阈值，而不是一开始伪造一个“95% Agent Accuracy”。

---

## 13. Trace 与 Observability

每个 Runtime Run 需要统一 Trace Identity：

```text
request_id
→ thread_id
→ run_id
→ trace_id
→ node span
→ tool / workflow span
→ provider span
```

建议每个 Node 至少记录：

```text
node_name
state_version_before
state_version_after
started_at
finished_at
latency_ms
workflow/tool name
provider_calls
retry_count
error_class
checkpoint_written
human_interrupt_created
```

面试和工程排障都应能够回答：

```text
慢在哪里？
贵在哪里？
失败在哪个 Node？
用了哪个事实版本？
为什么走这条 Route？
为什么暂停？
Resume 从哪里开始？
有没有重复调用 Tool？
```

---

## 14. 推荐目录结构

目标结构建议：

```text
services/backend/app/agent/
├── context.py
├── entrypoint.py
├── tool_registry.py
│
├── runtime/
│   ├── base.py
│   ├── workflow_runtime.py
│   └── langgraph_runtime.py
│
├── graph/
│   ├── state.py
│   ├── nodes.py
│   ├── routing.py
│   ├── checkpoint.py
│   └── career_graph.py
│
└── policies/
    ├── retry.py
    ├── limits.py
    └── stale_state.py

services/backend/app/evals/
└── career_agent_trajectory.py

services/backend/tests/
├── test_career_agent_langgraph_runtime.py
├── test_career_agent_resume.py
├── test_career_agent_human_interrupt.py
└── test_career_agent_trajectory_eval.py
```

具体落地时应优先复用当前 `app/agent/context.py`、`entrypoint.py` 和 `tool_registry.py`，不要为了目录“好看”一次性移动大量已稳定代码。

---

## 15. 分阶段实施计划

### 15.0 面试 / 求职 ROI 版执行约束

这份计划不再按“先把 LangGraph 功能做全”推进，而按一个可验证 Vertical Slice 收敛。第一阶段只证明四件事：

```text
Workflow 仍是业务事实层
→ LangGraph 只增加显式 State / Routing
→ Human Interrupt 后可以 Checkpoint / Resume
→ 整条路径可以用 Trajectory Eval 回归
```

第一阶段唯一主链：

```text
Rank Jobs
→ deterministic Top-N Target Cohort Proposal
→ interrupt
→ Human Approve / Edit / Reject
→ resume
→ Skill Gap
```

明确不在第一阶段顺手增加：

- free-form natural-language planner；
- Multi-Agent；
- 自动重新 Match / Requirement Extraction；
- 自动写 `UserFeedback`；
- 长期 Memory；
- Playwright / MCP / Pi 等其他求职加分项。

建议业余时间预算：

| Slice | 目标 | 预算 |
|---|---|---:|
| LG-0 | Runtime Boundary，行为不变 | 2–3h |
| LG-1a | `CareerAgentState` + Graph Nodes / Routing | 4–6h |
| LG-1b | Persistent Checkpoint + Interrupt / Resume | 4–6h |
| LG-1c | approve / edit / reject + stale-state / idempotency | 4–6h |
| LG-2 | Error Policy + Runtime Limits | 3–4h |
| LG-4 | 20+ deterministic trajectory eval | 5–7h |
| Docs / demo / regression | README、架构图、验证命令 | 3–4h |

目标总投入：约 **25–36 小时**。对在职开发者按每周 10–13 小时估算，为 2–3 周。

### 第一阶段面试可证明的 Done

只有同时满足下面条件，才可以在简历中把 LangGraph 从“规划中”改成“项目实战”：

1. 至少一条真实 Career Workflow 使用 LangGraph 运行，而不是单独教程 Demo；
2. State 保存的是版本化事实引用和运行态，不复制第二套 Profile / JD 事实源；
3. Checkpoint 可以跨页面关闭 / Backend 重启恢复；
4. Target Cohort 有真实 `interrupt`，用户可 approve / edit / reject；
5. Resume 前重新校验 Profile / SearchIntent / Match 版本，stale 时 fail closed；
6. duplicate resume 不产生重复业务副作用；
7. 原有 Ranking / Gap Workflow 没有复制进 Graph Node；
8. 至少 20 条 trajectory case，覆盖 expected route、forbidden route、HITL、resume、stale、limits；
9. 原有 Career Agent / Ranking / Gap regression 全部继续通过；
10. README 只描述已经验证过的能力。

---

## LG-0：建立 Runtime Boundary

目标：在不引入 LangGraph 行为的情况下先把框架依赖隔离。

完成：

- 定义 `AgentRuntime` 协议；
- 当前 `CareerAgentEntrypoint` 通过 Runtime 接口执行；
- 保留现有 deterministic behavior；
- 现有 Career Agent tests 全部通过；
- 不新增 Provider 调用。

Done：

> Runtime 可替换，但用户行为完全不变。

---

## LG-1：第一条 LangGraph Vertical Slice

目标：实现 `Ranking → Target Cohort → HITL → Skill Gap`。

完成：

- `CareerAgentState`；
- graph nodes / conditional edges；
- persistent checkpoint；
- target cohort interrupt；
- approve / edit / reject；
- resume；
- stale-state validation；
- deterministic trajectory tests。

Done：

> 浏览器关闭或 Backend 重启后，能够从人工确认 checkpoint 恢复；不会重复执行 Ranking，也不会在事实版本过期后继续执行。

---

## LG-2：Error Policy + Runtime Limits

目标：把可靠性策略从隐式异常处理升级为显式 Runtime Policy。

完成：

- error classification；
- bounded retry；
- `max_turns`；
- `max_tool_calls`；
- `max_provider_calls`；
- cancel；
- duplicate resume / idempotency tests。

Done：

> 网络故障、参数错误、权限错误、业务不变量错误进入不同处理路径，不存在统一“重试三次”。

---

## LG-3：Natural Language Routing

目标：让用户不再手工传固定 Goal，但继续保持受治理边界。

完成：

- free-form query → structured route；
- route confidence / unsupported goal；
- simple Workflow Runtime 与 LangGraph Runtime 选择；
- forbidden route tests；
- routing eval dataset。

Done：

> 用户自然语言可以进入正确的粗粒度 Workflow，而不是让模型自由调用底层 CRUD。

---

## LG-4：Agent Trajectory Eval + Release Gate

目标：把 Runtime 质量纳入现有 Eval-first 体系。

完成：

- trajectory dataset；
- route / tool / HITL / resume graders；
- baseline；
- regression；
- release gate；
- trace report。

Done：

> Runtime 或 Prompt 修改后，可以回答“哪条执行路径变好了、哪条回归了、是否允许发布”。

---

## LG-5：可选扩展——MCP / Pi Integration

这不是 LangGraph 第一阶段完成条件。

当 JobLens Tool Registry 稳定后，再考虑：

```text
JobLens MCP Server
├── search_jobs
├── get_match_report
├── rank_jobs
├── analyze_skill_gaps
└── prepare_job
```

然后允许 Pi / Claude / OpenAI Agent 等外部 Harness 使用 JobLens 能力。

这一步用于证明：

> Tool 能力与某个 Agent Framework 解耦。

不要为了 MCP 提前破坏现有业务权限与 Release Gate。

---

## 16. Definition of Done

LangGraph 不能因为“代码中 import 了 langgraph”就算完成。

第一阶段完成必须同时满足：

- [ ] LangGraph 只负责编排，不重新实现 Ranking / Gap 等业务规则；
- [ ] 有显式、版本化的 `CareerAgentState`；
- [ ] 至少一个真实用户价值 Vertical Slice 跑通；
- [ ] 有 persistent checkpoint；
- [ ] 有 Human Interrupt / Resume；
- [ ] Resume 能检测 stale Profile / SearchIntent；
- [ ] 重复 Resume 不产生重复副作用；
- [ ] 权限 / Release Gate 失败时 fail-closed；
- [ ] Retry 按错误类型处理，不使用统一盲重试；
- [ ] 有 `max_turns / max_tool_calls / max_provider_calls`；
- [ ] 有 deterministic trajectory eval；
- [ ] forbidden tool call 有明确测试；
- [ ] Trace 能串联 request → graph node → workflow/tool → provider；
- [ ] 原有 Backend / Web 测试继续通过；
- [ ] README / 架构文档只描述真实已经实现的能力。

---

## 17. 求职与简历包装边界

这一节用于约束“技术实现”和“求职表达”一致，避免为了招聘关键词提前包装。

### 当前尚未实现 LangGraph Runtime 时

可以说：

> JobLens 当前采用 Workflow-first 的受治理 Career Agent 架构，已完成 Context Builder、Tool Registry 和结构化统一入口；下一阶段计划引入 LangGraph，重点解决长流程 State、Checkpoint、HITL 和 Resume，而不是重写既有业务 Workflow。

不要写：

> 熟练 LangGraph / JobLens 基于 LangGraph 构建。

### LG-1 完成以后

简历可以增加：

> **构建可恢复 Career Agent Runtime：**基于 LangGraph 将 Ranking、Skill Gap 等成熟 Workflow 组织为有状态执行图，设计显式 Agent State、Conditional Routing、Checkpoint、Interrupt / Resume 与 Human-in-the-loop；业务能力仍通过受治理 Tool Registry 调用，避免把确定性业务规则迁入 LLM。

### LG-4 完成以后

可以进一步增加：

> **建立 Agent Runtime Eval：**使用固定 Profile / Job 数据集评测 Tool Routing、执行轨迹、Grounding、Forbidden Tool Call、最大轮次、HITL 和 Resume 正确性，并将真实 Bad Case 固化为 Regression / Release Gate。

### 面试中的技术选型表达

推荐回答：

> Ahoy 的主要需求是 Tool Calling、Streaming、Session、HITL 与 Trace，生产系统使用 OpenAI Agents SDK，抽象更轻且和现有 Python Runtime 集成成本低。JobLens 则存在跨步骤状态、人工中断、Checkpoint 和恢复需求，所以我在个人开源项目中引入 LangGraph 作为 Stateful / Durable Runtime。两边复用的思想是一致的：业务能力放在可独立评测的 Workflow 中，Agent Runtime 只负责编排和执行控制，而不是为了框架把所有业务 Agent 化。

这比“所有项目都用了 LangGraph”更真实，也更能体现技术选型能力。

---

## 18. 对外技术故事

JobLens 的技术演进可以形成以下求职叙事：

```text
Phase A
真实岗位 + Profile Evidence
→ 先解决事实不可信

Phase B
Requirement / Match / Ranking / Gap
→ 建立稳定 Domain Workflow

Phase C
Eval / Human Review / Release Gate
→ 解决模型改动不可验证

Phase D
Governed Career Agent
→ 用 Tool Registry 编排成熟 Workflow

Phase E
LangGraph Runtime
→ 解决长流程 State / Checkpoint / HITL / Resume

Phase F
Trajectory Eval
→ 解决 Agent 路径不可验证

Phase G（可选）
MCP / Pi Integration
→ 证明 Tool 与具体 Agent Harness 解耦
```

最终作品不应被包装成：

> “一个使用 LangGraph 的求职聊天机器人。”

而应该是：

> **一个 Evidence-grounded、Eval-driven、可恢复、有人类决策边界的 Career Agent；LangGraph 是其中用于 long-running orchestration 的 Runtime，而不是产品价值本身。**

---

## 19. 推荐开发顺序

若以求职 ROI 和工程风险共同排序：

```text
1. LG-0 Runtime Boundary
2. LG-1 Ranking → HITL → Gap Vertical Slice
3. LG-2 Error / Retry / Limits
4. LG-4 Trajectory Eval / Release Gate
5. LG-3 Natural Language Routing
6. MCP Server
7. Pi Extension / OSS Integration
8. Multi-Agent（暂不做）
```

注意：这里故意把 Trajectory Eval 提前到自然语言路由附近，而不是等 Agent 做得很复杂以后再补评测。

JobLens 的长期差异化仍然是：

> **事实可追溯 + Workflow 可评测 + Agent Runtime 可控制 + Human Decision 不越权。**
