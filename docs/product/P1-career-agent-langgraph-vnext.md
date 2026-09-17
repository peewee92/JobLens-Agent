# P1 Career Agent Agent Runtime / LangGraph vNext 产品需求文档

- 状态：Planned / vNext 1.0 主 PRD / 需求已冻结到第一条 Vertical Slice
- 对应缺口：**1. 真正的 Agent Runtime —— 当前最大缺口**
- 目标阶段：vNext 1.0 Agent Runtime
- 核心目标：在不重写现有 Domain Workflow 的前提下，为 JobLens 增加可恢复、可中断、可评测的 Stateful Agent Runtime
- 版本前置：v0.2 Workflow Freeze Candidate
- 后续阶段：vNext 1.1 Natural Language + Bounded Tool Loop → vNext 1.2 Job Search Execution Layer → vNext 1.3 MCP
- 关联决策：`docs/decisions/0004-llm-workflow-agent-boundary.md`
- 关联实施方案：`docs/implementation/P1-Career-Agent-LangGraph-Runtime-Integration-Plan.md`
- 关联执行计划：`docs/implementation/P1-JobLens-LangGraph-Runtime-Execution-Plan.md`
- Durable HITL 专项需求：`docs/product/P1-career-agent-durable-hitl-prd.md`
- 自然语言 / 多轮 Tool Calling：`docs/product/P1-career-agent-natural-language-tool-loop-prd.md`
- 求职执行层：`docs/product/P1-job-search-execution-layer-prd.md`
- 关联架构：`docs/architecture/SYSTEM-ARCHITECTURE.md`
- 关联评测：`docs/architecture/EVAL-AND-TRACE.md`

> 本文档是四个 Agent 化缺口中的 **Runtime 主 PRD**。Durable HITL 是 Runtime 的强制组成部分，但其用户交互、幂等、恢复、stale 校验和 API 细节在独立 HITL PRD 中冻结；自然语言路由和多轮 Tool Calling 必须等 Runtime Release Gate 通过后再接入，禁止并行把两个不稳定变量一起引入主链。

---

## 1. 背景

JobLens 已经具备稳定的 Career Agent 基础能力：

```text
Governed Context Builder
→ CareerAgentEntrypoint
→ Tool Registry
→ Ranking / Gap / Preparation Workflow
```

当前入口仍然是“调用方明确 goal，再由代码确定性调用一个 Workflow”的结构化单轮编排。这种设计保证了事实、权限、成本与评测边界，但还不能完整覆盖以下长流程需求：

- 一次请求跨多个 Workflow；
- 中途需要人工确认；
- 用户确认后从原步骤继续，而不是全部重跑；
- 浏览器关闭 / 服务重启后恢复；
- Profile、SearchIntent 或 MatchReport 已变化时阻止旧状态继续执行；
- 对 Agent 的执行轨迹进行评测，而不只评最终回答。

因此 vNext 不把业务逻辑“迁移到 LangGraph”，而是在现有稳定 Workflow 上增加一个可插拔 Stateful / Durable Runtime。

---

## 2. 产品目标

### 2.1 一句话目标

> 用户可以让 JobLens 连续完成“岗位排序 → 选择目标岗位 → 人工确认 → 能力差距分析”，中途可暂停、恢复、取消，并且整个执行轨迹可追踪、可评测、可回归。

### 2.2 第一阶段只验证一个真实场景

```text
分析一批岗位
→ Ranking
→ 生成 Target Cohort 建议
→ Interrupt
→ 用户 Approve / Edit / Reject
→ Resume
→ Skill Gap
→ Final Result
```

第一阶段不以“自由聊天很聪明”为目标，而以以下 Runtime 能力为目标：

- State；
- Conditional Routing；
- Checkpoint；
- Interrupt / Resume；
- Human-in-the-loop；
- Runtime Limits；
- Trace；
- Trajectory Eval。

---

## 3. 核心设计原则

### 3.1 Agent 只编排，不实现业务能力

LangGraph Node 禁止复制以下逻辑：

- Eligibility；
- Semantic Match；
- Ranking；
- Gap 计算；
- Preparation；
- Requirement Extraction。

Node 只能：

1. 读取受治理的 Context；
2. 调用现有 Tool / Workflow；
3. 把结构化结果写入 Agent State；
4. 根据结果选择下一条 Edge。

### 3.2 第一阶段必须是零 Provider 成本的 Runtime 验证

第一条 Vertical Slice 只消费已经存在、已经发布的：

- Confirmed Profile / SearchIntent；
- current MatchReport；
- released JobRequirement；
- Gap / Preparation 可读事实。

如果缺少 MatchReport、Requirement 或 Release Gate 未通过，Graph 必须返回 blocker，不允许自动触发 Requirement Extraction、Semantic Match 或 MatchReport 生成。

> 第一阶段 Runtime 的 `provider_calls` 必须始终为 0。

### 3.3 用户决定不能由 Agent 代签

以下动作必须来自显式用户输入：

- Approve Target Cohort；
- Edit Target Cohort；
- Reject Target Cohort；
- UserFeedback；
- Requirement / Eval Final Decision。

Agent 只可以提出建议。

### 3.4 State 保存事实引用，不复制大文本

Checkpoint 中优先保存：

- ID；
- version；
- fingerprint；
- route；
- step；
- tool result summary；
- human decision。

不把完整 raw JD、完整 Resume、长 Tool Output 反复写入 State。

---

## 4. 用户故事

### US-LG-01：批量分析岗位

作为求职用户，我希望选择一批已有 MatchReport 的岗位，让系统给出排序并提出目标岗位集合建议。

### US-LG-02：人工确认目标岗位

作为用户，我希望在系统进入 Skill Gap 分析前确认、修改或拒绝目标岗位集合，避免 Agent 替我决定职业偏好。

### US-LG-03：暂停后继续

作为用户，我希望在等待确认时关闭页面，稍后可以继续原 Run，而不是重新执行 Ranking。

### US-LG-04：状态变化时拒绝旧 Run

作为用户，我希望当 Profile、SearchIntent 或关键 MatchReport 已更新时，旧 Run 不会使用过期事实继续给建议。

### US-LG-05：知道 Agent 做过什么

作为开发者 / 维护者，我希望每一步 Node、Tool、Interrupt、Resume 都能通过 Trace 定位，并能从 Eval 判断路线是否正确。

---

## 5. 第一阶段执行图

```text
START
  ↓
load_governed_context
  ↓
validate_release_gate
  ├─ blocked → BLOCKED_END
  ↓
validate_match_readiness
  ├─ missing current MatchReport → BLOCKED_END
  ↓
rank_jobs
  ↓
propose_target_cohort
  ↓
INTERRUPT(target_cohort_confirmation)
  ├─ reject → CANCELLED_END
  ├─ edit    → validate_human_selection
  └─ approve → validate_human_selection
                  ↓
             build_skill_gaps
                  ↓
              final_result
                  ↓
                 END
```

### 5.1 Target Cohort 建议规则

第一阶段 `propose_target_cohort` 不调用 LLM，也不增加新的职业判断模型。

规则冻结为：

1. `rank_jobs` 默认 `include_blocked=false`；
2. `top_n` 默认 5，允许 1..10；
3. proposed Target Cohort = Ranking 返回的前 `top_n` 个可用 Job；
4. 如果实际可用 Job 少于 `top_n`，使用全部可用 Job；
5. 如果可用 Job 为 0，直接进入 `match_not_ready / no_rankable_jobs` blocker，不产生空的人工确认；
6. 用户 `edit` 后的 Job 必须是本 Run `requested_job_ids` 中、且在 Resume 时仍有 current MatchReport 的子集，数量 1..10。

这样第一阶段只验证 Runtime / HITL，不把“Target Cohort 推荐策略”作为新的 LLM 变量。

### 5.2 暂不加入 LLM Natural Language Router

第一阶段入口继续使用结构化请求，例如：

```json
{
  "goal": "analyze_target_cohort_gaps",
  "jobIds": ["job_1", "job_2", "job_3"],
  "topN": 5
}
```

自然语言路由在 Runtime / HITL / Eval 已稳定后进入下一阶段，避免同时引入“路由质量”和“Durable Runtime”两个变量。

---

## 6. Agent State

建议最小状态模型：

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
│   ├── requested_job_ids
│   ├── current_match_report_ids
│   └── match_fingerprint
│
├── orchestration
│   ├── goal
│   ├── current_step
│   ├── route
│   ├── ranked_job_ids
│   ├── proposed_target_job_ids
│   └── pending_approval
│
├── human_decision
│   ├── decision
│   └── selected_target_job_ids
│
├── runtime
│   ├── node_count
│   ├── tool_call_count
│   ├── provider_call_count
│   ├── retry_count
│   └── last_error_class
│
└── result_refs
    └── gap_result_fingerprint
```

### 6.1 不允许进入 State 的数据

- API Key / token；
- raw Resume 文件；
-完整 raw JD；
- 超长 Tool Output；
- 未经发布的 Requirement 草稿；
- 未确认 Profile Proposal。

---

## 7. Context 与 Stale State 校验

### FR-LG-01：Run 创建时冻结事实身份

创建 Run 时记录：

- Profile ID + version；
- SearchIntent ID + version；
- 请求 Job 的 current MatchReport IDs / fingerprint。

### FR-LG-02：Resume 前必须重新校验

Resume 时如果发生任一变化：

- Profile version changed；
- SearchIntent version changed；
- selected Job current MatchReport changed / missing；

则不得继续旧 Checkpoint，返回：

```text
state_stale
```

并提示用户重新开始本次分析。

> 不允许悄悄把旧 State 与新事实拼起来继续运行。

---

## 8. Tool / Workflow 需求

### FR-LG-03：Ranking

复用现有 `rank_match_reports`，只能读取 current immutable MatchReport。

禁止：

- 自动执行 Match；
- 自动补 Requirement；
- 自动调用 Provider。

### FR-LG-04：Target Cohort Gap Tool 扩展

当前 HTTP `TargetCohortGapRequest` 已支持：

- `selected_job_ids`；或
- `selected_feedback_ids`。

但当前 `CareerAgentToolRegistry` 只支持 `selected_feedback_ids`。

vNext 必须将 Agent 层能力补齐为：

```text
TargetCohortGapsRequest
├── selected_job_ids        # Human Confirm 后的显式 Job 选择
└── selected_feedback_ids   # 现有 Feedback-driven 路径
```

规则：两者必须二选一，不可同时为空，不可同时提供。

第一条 LangGraph Slice 使用 `selected_job_ids`，因为 Target Cohort 是本 Run 中用户刚确认的 transient decision，不应为了继续 Graph 而伪造 UserFeedback。

### FR-LG-05：Tool Access

第一阶段所有业务 Tool 均为 read-only / transient computation：

- `business_state_writes = 0`；
- `provider_calls = 0`；
- `UserFeedback writes = 0`。

允许 Runtime 自己写入：

- LangGraph Checkpoint；
- Agent Trace / telemetry。

这些运行态写入不得修改 Profile、SearchIntent、JobRequirement、MatchReport、UserFeedback 等业务事实，因此评测与 Release Gate 必须区分 `business_state_writes` 和 `runtime_state_writes`，不能笼统使用 `DB writes`。
---

## 9. Human-in-the-loop

### FR-LG-06：Interrupt Payload

进入 Target Cohort 人工确认时必须返回：

- thread_id；
- run_id；
- proposed job IDs；
- 每个 Job 的 title / company；
- ranking position；
- recommendation / blocker summary；
- 继续执行后将发生什么。

### FR-LG-07：Decision 类型

只支持：

```text
approve
edit
reject
```

- `approve`：使用 proposed set；
- `edit`：用户显式提交 selected_job_ids；
- `reject`：结束 Run，不进入 Gap。

### FR-LG-08：Resume 幂等

同一个 interruption 只能成功消费一次。

重复提交同一个 decision 必须返回原结果或明确 `already_resumed`，不得重复执行下游 Workflow。

---

## 10. Checkpoint

### FR-LG-09：MVP Checkpointer

沿用项目 SQLite-first 原则，第一阶段采用本地持久化 Checkpointer。

Checkpoint 至少能够支持：

- FastAPI 进程重启后读取；
- 页面关闭后恢复；
- 通过 thread_id 查询当前状态；
- 清楚区分 `running / interrupted / completed / cancelled / blocked / failed / stale`。

### FR-LG-10：Checkpoint 不是业务事实源

业务事实仍来自现有 Repository / Domain Model。

Checkpoint 只保存 Agent 执行状态和事实版本引用。

---

## 11. API 需求

建议增加：

```text
POST /career-agent/runs
POST /career-agent/runs/{thread_id}/resume
GET  /career-agent/runs/{thread_id}
POST /career-agent/runs/{thread_id}/cancel
```

### Run 创建

输入：

- goal；
- job_ids；
- top_n。

输出可能为：

```text
completed
interrupted
blocked
failed
```

### Resume

输入：

- interruption_id；
- decision；
- selected_job_ids（edit 时必填）。

### State Query

只能返回 public / debug-safe snapshot，不返回 raw prompt、secret、raw resume 或内部敏感字段。

---

## 12. Runtime Limits

### FR-LG-11：硬限制

第一阶段默认：

```text
max_node_steps      = 12
max_tool_calls      = 6
max_provider_calls  = 0
max_retries         = 1
```

超过限制必须 fail-closed，并记录 Trace。

### FR-LG-12：错误分类

至少区分：

- `invalid_request`；
- `context_not_released`；
- `match_not_ready`；
- `state_stale`；
- `permission_denied`；
- `business_invariant`；
- `transient_infrastructure`；
- `runtime_limit_exceeded`；
- `cancelled`。

第一阶段只有 `transient_infrastructure` 可以有限重试；业务错误、权限、stale state 不重试。

---

## 13. Trace / Observability

每个 Run 必须记录：

```text
thread_id
run_id
request_id
profile_version
search_intent_version
match_fingerprint
node
route
tool
start/end/duration
interrupt_id
resume decision
error_class
node_count
tool_call_count
provider_call_count
```

需要能够回答：

- Agent 卡在哪一步；
- 为什么进入这个 Route；
- 是否重复调用 Tool；
- Resume 是否重复执行；
- 是否使用了过期事实；
- 是否违反零 Provider / 零写入边界。

---

## 14. Trajectory Eval

第一阶段必须在功能完成时同时交付至少 20 条 deterministic trajectory cases。

### 14.1 Case 分布

| 类别 | 最少数量 | 例子 |
|---|---:|---|
| Happy path | 5 | ranking → interrupt → approve → gaps |
| Context / readiness blocker | 5 | Profile 未 release、Match 缺失 |
| HITL | 4 | approve / edit / reject / invalid selection |
| Resume / stale / idempotency | 4 | version changed、double resume |
| Runtime limits / failures | 2 | step limit、transient failure |

### 14.2 每条 Case 至少声明

```text
input
initial facts
expected nodes
expected tools
forbidden tools
expected interruption
resume decision
expected terminal state
required grounding refs
expected provider_calls
expected business_state_writes
expected runtime_state_writes
```

### 14.3 Release Gate

第一阶段发布门槛：

- 20/20 trajectory cases 通过；
- forbidden tool violation = 0；
- provider calls = 0；
- business-state writes = 0（Checkpoint / Trace runtime writes 允许）；
- stale-state continuation = 0；
- duplicate resume side effect = 0；
- Context / Match release blocker 正确率 = 100%。

---

## 15. 非目标

第一阶段明确不做：

- Multi-Agent；
- 自由文本 Intent Router；
- Agent 自动生成 MatchReport；
- Agent 自动执行 Requirement Extraction；
- 自动投递；
- 自动修改 UserFeedback；
- 自动选择并提交用户职业偏好；
- Graph 内实现业务规则；
- 为了展示 LangGraph 把所有简单 GET 请求改成 Graph。

---

## 16. 完成标准

只有同时满足以下条件才可在简历中写“JobLens 使用 LangGraph 构建可恢复 Agent Runtime”：

1. 至少一个真实业务 Vertical Slice 跑通；
2. State 显式建模，不只是 `messages`；
3. Checkpoint 真实持久化；
4. Interrupt / Resume 可跨请求工作；
5. Human edit / reject 有实际行为；
6. Resume 前有 stale-state 校验；
7. 20+ trajectory eval 通过；
8. Trace 能重建执行路径；
9. Runtime limit 与 error classification 生效；
10. README / 架构图 / Demo 更新；
11. 最小 Web 演示入口可完成 Run → Interrupt → Approve/Edit/Reject → Resume → Gap，不要求先做自由聊天 UI。

---

## 17. Grill-me 需求澄清结论

按照 `grill-me` 的 goal / behavior / inputs-outputs / scope / success criteria / constraints / edge cases 维度对方案进行压力检查后，冻结以下容易含糊的决策：

1. **为什么要 LangGraph？** 不是为了框架关键词，而是解决长流程 State、Checkpoint、Interrupt / Resume 和 Trajectory Eval。
2. **第一阶段是否使用 LLM Router？** 不使用。先隔离 Runtime 变量。
3. **第一阶段是否允许 Provider 调用？** 不允许，必须为 0。
4. **是否允许 Graph 自动补 MatchReport？** 不允许；缺失即 blocker。
5. **Target Cohort 是 Feedback 还是 Run 内人工决策？** 第一条 Slice 使用显式 `selected_job_ids`，不伪造 UserFeedback。
6. **Checkpoint 是否成为事实数据库？** 不是，只保存运行状态与事实引用。
7. **旧 Run 是否自动迁移到新 Profile？** 不允许；版本变化直接 `state_stale`。
8. **重复 Resume 怎么处理？** 必须幂等，不能重复执行下游 Workflow。
9. **什么叫 LangGraph 做完？** 不是图能运行，而是至少 20 条 trajectory eval + 持久化恢复 + HITL + Trace 全部成立。
10. **“零写入”和 Checkpoint 是否冲突？** 不冲突；冻结为“业务事实零写入”，Checkpoint / Trace 属于 Runtime 写入，指标必须分别统计。
11. **Target Cohort 建议由谁决定？** 第一阶段完全由现有 Ranking 的 Top-N 确定，不引入新的 LLM 决策。
12. **Portfolio Demo 是否只提供 API？** 不够。Release-ready 版本至少提供一个最小 Web HITL 入口展示真实 pause / resume，但不要求先做聊天界面。

这些决定优先保护 JobLens 现有 Evidence / Release Gate / Eval 体系，不以增加“Agent 自主性”为理由破坏事实治理。
