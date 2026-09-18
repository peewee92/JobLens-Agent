# P1 JobLens LangGraph Runtime：面试驱动执行计划

> 文档类型：Implementation Execution Plan
> 状态：Planned / vNext 1.0 第一执行计划 / Not Implemented
> 目标：**不要再做 LangGraph Demo，直接在 JobLens 现有 Career Agent 上补一条真实、可恢复、可评测的 Runtime Slice。**
> 关联 Runtime PRD：`docs/product/P1-career-agent-langgraph-vnext.md`
> Durable HITL PRD：`docs/product/P1-career-agent-durable-hitl-prd.md`
> 后续 Natural Language / Tool Loop PRD：`docs/product/P1-career-agent-natural-language-tool-loop-prd.md`
> 后续 Job Execution PRD：`docs/product/P1-job-search-execution-layer-prd.md`
> 关联架构：`docs/implementation/P1-Career-Agent-LangGraph-Runtime-Integration-Plan.md`

---

## 1. 为什么这不是一个 LangGraph Demo

JobLens 当前已经有真实业务能力：

```text
Governed Career Context
→ Ranking Workflow
→ Target Cohort / Gap Workflow
→ Job Preparation Workflow
→ Eval / Review / Release Gate
```

当前 `CareerAgentEntrypoint` 还是结构化单轮入口：

```text
explicit goal
→ Governed Context Builder
→ Tool Registry
→ mature Workflow
```

它明确 **不解释 free-form language**，这是当前正确边界，不需要为了“看起来像 Agent”立刻重写。

LangGraph vNext 要解决的是 JobLens 已经真实存在但当前缺失的 Runtime 问题：

- 一次 Career Agent 请求跨多个步骤；
- 中间需要用户确认 Target Cohort；
- 确认前后要保存状态；
- 浏览器关闭 / 服务重启后可以继续；
- Profile / SearchIntent / Match 变化后旧 Run 不能继续污染新事实；
- Resume 不能重复执行副作用；
- Agent Runtime 自身需要 trajectory eval，而不是只看最终文本。

因此：

> **LangGraph 只负责 State / Routing / Checkpoint / Interrupt / Resume / Runtime Control，现有业务 Workflow 不迁进 Graph。**

---

## 2. 第一条 Vertical Slice

只做这一条：

```text
User asks to analyze one prepared Job batch
        ↓
Load Governed Context
        ↓
Validate Release Readiness
        ↓
Rank Jobs
        ↓
Take deterministic Top-N as Target Cohort Proposal
        ↓
interrupt()
        ↓
Human Approve / Edit / Reject
        ↓
resume()
        ↓
Build Skill Gap for confirmed selected_job_ids
        ↓
Return grounded result
```

### P1 第一阶段不做

- 不做 Multi-Agent；
- 不做 Planner Agent；
- 不做长期 Memory；
- 不自动重新跑 Requirement Extraction；
- 不自动生成缺失 Match；
- 不让 LLM 决定 Target Cohort；
- 不自动修改 UserFeedback；
- 不做 Job Application / Recruiter Messaging；
- 不把 GET / simple query 全部改成 Graph；
- 不为了简历先写“熟练 LangGraph”。

---

## 3. Runtime Boundary

### 3.1 目标接口

建议先定义框架无关 Runtime Port：

```python
class CareerAgentRuntime(Protocol):
    def run(self, request: CareerAgentRunRequest) -> CareerAgentRunResult: ...
    def resume(self, request: CareerAgentResumeRequest) -> CareerAgentRunResult: ...
    def get_state(self, thread_id: str) -> CareerAgentRuntimeState: ...
```

实现：

```text
CareerAgentRuntime
├── WorkflowCareerAgentRuntime
└── LangGraphCareerAgentRuntime
```

### 3.2 为什么保留 Workflow Runtime

简单路径例如：

```text
查看一个岗位 Preparation
查看当前 Ranking
读取 MatchReport
```

不需要 State Machine。

只有：

```text
跨步骤
+ Human Interrupt
+ Persistence
+ Resume
```

才走 LangGraph。

这也是面试必须能回答的：

> **不是“用了 LangGraph 就高级”，而是它只负责适合 Graph 的 long-running orchestration。**

---

## 4. State 设计

建议新增：

`services/backend/app/agent/graph/state.py`

第一阶段 State 只保存 **引用、版本、执行控制字段**，不复制大块业务数据。

```text
thread_id
run_id
status
current_step

profile_id
profile_version
search_intent_id
search_intent_version

input_job_ids
ranked_job_ids
proposed_job_ids
confirmed_job_ids

match_report_refs / fingerprints
pending_approval

retry_count
last_error
started_at
updated_at
```

### 不应该塞进 State

- raw resume；
- raw JD；
- 完整 JobRequirement 列表；
- 完整 Match Report payload；
- 大段 Tool output；
- API Key / Provider Secret。

这些属于业务事实或外部资源，State 应保存 reference / version / fingerprint，并在需要时重新读取。

---

## 5. Checkpoint 与业务数据库边界

第一阶段需要明确两类写入：

```text
business_state_writes = 0
runtime_state_writes  = allowed
```

### Business State

不能因为运行 Graph 自动修改：

- Profile；
- SearchIntent；
- JobRequirement；
- MatchReport；
- UserFeedback；
- Target Cohort 的正式业务事实。

### Runtime State

允许保存：

- thread / run；
- current node；
- pending interrupt；
- checkpoint state；
- runtime trace / error；
- resume metadata。

### Checkpoint 的目的

不是“缓存”。

它解决：

```text
process crash
browser close
human approval after N minutes
resume from known state
```

---

## 6. Human Interrupt / Resume

### 6.1 interrupt payload

Rank 完成后产生：

```json
{
  "type": "target_cohort_review",
  "threadId": "...",
  "runId": "...",
  "rankedJobIds": ["job_1", "job_2", "job_3"],
  "proposedJobIds": ["job_1", "job_2"],
  "reason": "Top-N released ranking results",
  "allowedActions": ["approve", "edit", "reject"]
}
```

### 6.2 resume actions

#### approve

```text
proposed_job_ids
→ confirmed_job_ids
→ Gap Workflow
```

#### edit

```text
user_selected_job_ids
→ validate all IDs belong to original ranked batch
→ confirmed_job_ids
→ Gap Workflow
```

#### reject

```text
status = rejected
→ END
```

### 6.3 幂等

同一个：

```text
thread_id + interrupt_id + resume_action_id
```

重复 Resume 必须返回已有结果或明确 conflict，不得重复执行后续业务动作。

---

## 7. Stale State Protection

Resume 前必须重新验证：

```text
profile version unchanged?
search intent version unchanged?
job still exists?
match report still current?
release gate still valid?
```

任一关键输入变化：

```text
RUN_STALE
→ block resume
→ tell client to start a new run
```

不能：

> “反正有 checkpoint，就继续用旧事实完成 Gap。”

Checkpoint 保存的是执行历史，不是绕过 current facts 的权限。

---

## 8. Routing

第一阶段路由保持 deterministic：

```text
START
→ load_context
→ validate_inputs
→ rank_jobs
→ propose_target_cohort
→ human_review
    ├── reject → END
    ├── approve → analyze_gap
    └── edit → validate_selection → analyze_gap
→ final
```

第一阶段不加入 LLM Router。

为什么：

> 先验证 State / Checkpoint / HITL / Resume 的 Runtime 正确性，避免把 Routing Model 的随机性与 Runtime Bug 混在一起。

Natural-language routing 是第二阶段能力。

---

## 9. Error Classification

Graph 不应该变成无限 Retry Engine。

至少分：

| Error | Policy |
|---|---|
| invalid input | fail fast，返回 4xx / structured blocker |
| stale domain state | block resume，要求 new run |
| permission / release gate | fail closed |
| transient network/provider | bounded retry，仅后续 Provider 节点适用 |
| workflow invariant violation | no retry，记录 trace |
| checkpoint persistence failure | runtime failed，不得假装完成 |
| user reject | normal terminal state，不是 error |

第一阶段 Slice 目标：

```text
provider_calls = 0
```

因此任何 Provider Call 都应该被 trajectory eval 视为异常。

---

## 10. 建议代码结构

```text
services/backend/app/agent/
├── context.py
├── entrypoint.py
├── tool_registry.py
│
├── runtimes/
│   ├── base.py
│   ├── workflow_runtime.py
│   └── langgraph_runtime.py
│
└── graph/
    ├── state.py
    ├── nodes.py
    ├── routing.py
    ├── checkpoint.py
    └── builder.py
```

API 可新增独立 Runtime Endpoint，不破坏当前 `/career-agent` structured entrypoint：

```text
POST /career-agent/runs
GET  /career-agent/runs/{thread_id}
POST /career-agent/runs/{thread_id}/resume
```

实际路径以现有 API versioning 规范为准。

---

## 11. 20 条 Trajectory Eval 最小集

至少覆盖：

### Happy Path

1. Rank → interrupt；
2. Approve → Gap → complete；
3. Edit → Gap → complete；
4. Reject → END；

### State / Checkpoint

5. interrupt 后 state 可查询；
6. 新 Runtime instance 能从 persisted checkpoint resume；
7. Resume 后不重新执行 Rank；
8. completed run 不可继续 resume；

### Stale

9. Profile version changed；
10. SearchIntent changed；
11. MatchReport stale/missing；
12. selected job 不属于原 batch；

### Idempotency

13. duplicate approve；
14. duplicate edit；
15. same action_id replay；

### Guardrails

16. provider_calls == 0；
17. business_state_writes == 0；
18. forbidden tool not invoked；
19. max runtime transition 不超预算；
20. Trace 包含 expected nodes + terminal state。

每条 Eval 至少有：

```text
case_id
initial_facts
input
expected_nodes
forbidden_nodes/tools
expected_interrupt
resume_payload
expected_terminal_state
expected_business_writes
expected_provider_calls
```

---

## 12. 面试驱动 Work Packages

### LG-0：Runtime Boundary

**状态：COMPLETE**

已完成工程证据：框架无关 `CareerAgentRuntime.run()` Protocol、`WorkflowCareerAgentRuntime` adapter、FastAPI `/career-agent/turn` Runtime 注入；现有 `CareerAgentEntrypoint` 行为保持不变。专项回归 11 passed，Backend 全量 1035 passed，compileall 通过；零 Provider、零业务状态写入、未引入 LangGraph 类型到 API。

**预计：2～3h**

产出：

- Runtime Protocol；
- Workflow Runtime adapter；
- 当前 CareerAgentEntrypoint 行为不变；
- unit tests。

Done：

> 上层不依赖 LangGraph 类型，现有测试全部通过。

---

### LG-1：State + Graph + Checkpoint

**状态：COMPLETE**

第一纵向切片新增显式、框架无关 `CareerAgentState` 与 SQLite-first checkpoint store；State 只保存 released fact identity/version/fingerprint 和 runtime control fields。专项回归证明使用同一 SQLite 文件重新创建 Store 后仍可恢复 interrupted thread，并锁定 checkpoint 不复制 raw resume/raw JD/完整 Requirement payload。

第二纵向切片冻结真实前半图合同：复用 `CareerAgentToolRegistry.rank_match_reports`，按请求范围执行 read-only Ranking，确定性取 Top-N 形成 Target Cohort Proposal，保存 current MatchReport IDs + fingerprint 后进入 `target_cohort_confirmation` interrupted state；没有 current Ranking 时 fail-closed 为 `match_not_ready`，不自动补 Match/Requirement。

第三纵向切片正式加入 `langgraph` 依赖与 lockfile，并新增 `LangGraphRankToTargetCohortInterrupt`：真实 `StateGraph` 现在负责 `rank_jobs` node、ranking readiness conditional edge 和 `persist_interrupt` node，业务 Ranking 仍只通过 Tool Registry 执行。专项回归锁定 Graph 结果可从 SQLite checkpoint 恢复，且 `provider_calls=0 / business_state_writes=0`。因此 LG-1 的 State / Graph / Persistent Checkpoint / rank→interrupt 四项已全部关闭，下一阶段进入 LG-2 Durable HITL。

**预计：5～8h**

产出：

- CareerAgentState；
- deterministic nodes / edges；
- persistent checkpoint；
- rank → interrupt。

Done：

> Server / Runtime restart 后能够读取同一 thread 的 pending state。

---

### LG-2：HITL + Resume + Stale Guard

**状态：COMPLETE**

第一纵向切片已关闭“人工决定本身不是 durable runtime contract”的缺口：Rank→Interrupt 现在生成并持久化稳定 `interrupt_id`；`TargetCohortDecisionHandler` 显式消费 Approve/Edit/Reject，Approve 固定采用 proposal，Edit 只允许本 Run requested scope 内 1..10 个岗位，Reject 正常进入 cancelled 且不执行下游 Tool。成功消费会冻结 `decision_action_id`；相同 action replay 幂等返回原 checkpoint，不同 action 在已消费 interrupt 上 fail-closed 为 conflict。

第二纵向切片关闭 Resume 前 stale validation：LG-1 interrupt 快照从“仅 Top-N proposal reports”扩展为“本 Run 全部可排序 current MatchReport IDs/fingerprint + Top-N proposal”，确保用户 Edit 加入 run scope 内非 proposal 岗位时仍有 frozen fact identity 可比。`ResumeStaleGuard` 只接受 `resuming / target_cohort_resume`，重新读取 Governed Profile/SearchIntent 与 current immutable MatchReports；Profile/SearchIntent identity/version、MatchReport IDs/order/fingerprint 任一变化都持久化为明确 `STALE`，不调用 Gap。完全一致时只推进到 `skill_gap_ready`；VALID/STALE 后重复 validate 直接返回 checkpoint，不重复读取或执行 Tool。该 slice 仍为 `provider_calls=0 / business_state_writes=0`。

第三纵向切片关闭 stale-safe Resume 到业务结果的最后一跳：`SkillGapResumeExecutor` 只消费 `resuming / skill_gap_ready` checkpoint，把 `confirmed_target_job_ids` 作为显式人工 Job selection 交给 Tool Registry；Registry 复用既有 `CreateManualTargetCohortCommand → Target Cohort Gap` 确定性 pipeline，不新增 Gap 算法或职业事实。成功结果只冻结 compact `gap_result_fingerprint` 后进入 `completed`；重复 execute 直接返回 completed checkpoint，不再次读取 Context 或调用 Gap Workflow。执行前再次校验 Profile identity/version，防止 stale guard 与 Gap 调用之间的 Profile 变化；任何 Provider call / business DB write 都 fail-closed。

最终 restart regression 关闭 LG-2 的 durable recovery 验收：同一 SQLite checkpoint 文件在 `Ranking → interrupt`、Human Decision、stale validation、Gap resume 以及 completed replay 之间逐次重建 `SQLiteCareerAgentCheckpointStore`，不依赖旧 Runtime/Store 内存即可恢复 thread；重建后的 duplicate resume 仍直接返回 completed checkpoint，Gap Workflow 只执行一次。由此 `Browser close / Runtime or process restart / duplicate resume / stale facts` 四类行为均已有确定性证据，LG-2 正式 COMPLETE，主线进入 LG-3。

**预计：6～8h**

产出：

- approve / edit / reject；
- resume API；
- stale state validation；
- idempotent resume；
- gap workflow execution。

Done：

> Browser close / new process / duplicate resume / stale facts 都有确定行为。

---

### LG-3：Trajectory Eval + Trace

**状态：COMPLETE**

第一纵向切片已建立 Runtime Release Gate 的确定性 grader foundation：新增 `CareerAgentTrajectorySnapshot / Case / EvalReport`，以显式 Runtime State、visited node sequence、Provider call counter 与 business-state-write counter 为输入；Release Gate 强制至少 20 个唯一 Case ID，并支持 expected status、expected node ordering、forbidden node、`max_provider_calls`、`max_business_state_writes` 断言。测试先证明模块缺失，再验证 20-case all-pass gate，以及注入 forbidden Provider node + Provider call + business write 后能精确指出三类 guardrail failure。

第二纵向切片把 Trace 从测试手写数组接到真实 durable checkpoint：`SQLiteCareerAgentCheckpointStore.save()` 除维护 latest checkpoint 外，还会 append-only 保存去重后的状态转换事件；`build_persisted_trajectory_snapshot()` 可在 Runtime/Store 重建后仅凭 SQLite history 还原 final state 与 visited step sequence，重复保存同一状态不会制造重复 Trace event。该 history 仍只保存原有 compact `CareerAgentState` payload，不复制 raw Resume/JD/Secret/大 Tool Output，也不新增业务状态写入。

第三纵向切片用 `career_agent_runtime_dataset.py` 冻结正式 20-case cohort，替换原先 20 个重复 happy-path fixture。Case 覆盖 approve 单/多岗位、edit 单/重排、reject、Profile identity/version stale、SearchIntent identity/version stale、Match fingerprint/order stale、missing Match、empty Ranking、invalid target selection、pending/restart interrupt、duplicate approve/edit/reject replay、restart completed 等控制路径，至少产生 8 种不同 persisted trace shape。每条 Case 都通过 `SQLiteCareerAgentCheckpointStore` 写入 durable history，再由 `build_persisted_trajectory_snapshot()` 回读进入同一 Release Gate，统一断言 forbidden Provider/Requirement/Semantic Match/business-write node、`provider_calls=0` 与 `business_state_writes=0`。

第四纵向切片关闭最后的“合成 checkpoint transitions”缺口：新增 `CareerAgentRuntimeTrajectoryRunner`，代表性 approve + duplicate resume、reject、missing Match、stale Profile Case 直接驱动现有 `LangGraphRankToTargetCohortInterrupt → TargetCohortDecisionHandler → ResumeStaleGuard → SkillGapResumeExecutor`，最终只从 SQLite persisted history 构建 snapshot。真实 Ranking node 现在也保存允许的 runtime trace checkpoint，因此 happy path 的 persisted trajectory 可明确看到 `rank_jobs → target_cohort_confirmation → target_cohort_resume → skill_gap_ready → skill_gap_completed`，而不是由 Eval 层补写节点。代表性真实 handler trajectories 与冻结 20-case release cohort 共同证明 route/state/resume/guardrail 均可重复验证；LG-3 正式 COMPLETE。

**预计：5～7h**

产出：

- 20 case dataset；
- trajectory runner；
- deterministic graders；
- expected / forbidden node assertion；
- provider/write guard；
- trace snapshot。

Done：

> 20 条全部可重复运行，失败时能指出错的是 route、state、resume 还是 guardrail。

---

### LG-4：Minimal Web HITL Demo / Evidence

**状态：IN PROGRESS**

第一纵向切片已完成最小 durable HTTP seam：`POST /career-agent/runs` 创建并执行到真实 Target Cohort interrupt，`GET /career-agent/runs/{thread_id}` 从 SQLite checkpoint 恢复 compact pending/terminal state，`POST /career-agent/runs/{thread_id}/resume` 显式消费 Approve/Edit/Reject 后执行 stale guard，并仅在事实仍 current 时进入现有 Skill Gap Workflow。API 通过框架无关 `CareerAgentHitlService` 组合现有 LG-1/LG-2 handlers，不向 FastAPI 暴露 LangGraph 类型；重复 Start 的相同 thread/run/request 幂等返回已有 checkpoint，不重复 Ranking。公开状态只包含 Runtime status/step、Job IDs、interrupt/decision 与 Gap fingerprint，不复制 raw Resume/JD/Requirement/大 Tool Output。专项 API + Runtime 回归 21 passed。下一 slice 是最小 Web Run/Interrupt/Decision/Resume UI 与页面刷新后的 pending thread 恢复。

**预计：2～3h**

产出：

- 最小 Web `Run → Interrupt → Approve/Edit/Reject → Resume → Gap` Demo；
- one reproducible demo；
- one failure/recovery example；
- architecture / interview evidence；
- README 仅在现有用户修改可安全合并时更新；
- Evidence Ledger J6 从 L0 升级到 L3。

---

## 13. 总工时与停止条件

第一版目标：

```text
20～29 小时
≈ 2～3 周业余时间
```

达到下面条件立即停止继续堆功能：

- [ ] State 不是 messages-only；
- [ ] Checkpoint 真持久化；
- [ ] Approve/Edit/Reject 都可 Resume；
- [ ] Runtime 重启可恢复；
- [ ] stale fact 会阻断旧 Run；
- [ ] duplicate resume 幂等；
- [ ] ≥20 trajectory eval；
- [ ] provider_calls = 0；
- [ ] business_state_writes = 0；
- [ ] Trace 可说明执行路径。

LG-4 完成后，**不得直接跳到 MCP，也不得继续把 Runtime 横向扩成 Multi-Agent 平台**。后续开发顺序冻结为：

```text
vNext 1.1 Natural Language + Bounded Tool Loop
  Career Intent
  → Dynamic Tool Selection
  → Multi-turn Tool Calling
  → Effect / Cost / Human Gate

vNext 1.2 Job Search Execution Layer
  Application Workspace
  → Resume Variant
  → Interview / Mock
  → Action / Evidence
  → Application Status
  → Re-match / Ranking 回流

vNext 1.3 MCP / External Agent Integration
  MCP Server
  → Pi / Claude / 其他 Consumer

vNext 2.0 Continuous Career Agent
```

原因：

1. Runtime 先解决“能不能可靠运行和恢复”；
2. Natural Language / Tool Loop 再解决“Agent 能不能自己决定下一步”；
3. Execution Layer 再解决“分析结果能不能转成真实求职行动”；
4. MCP 最后解决“这些成熟能力能不能被外部 Agent 复用”。

这样每一层都能独立 Eval，避免同时引入 Runtime、LLM 路由、业务写入和外部协议四类变量。

---

## 14. 完成后才能使用的简历表述

完成 DoD 之前只能说：

> JobLens 当前采用 Workflow-first 的受治理 Career Agent，正在用 LangGraph 补 long-running State / Checkpoint / HITL / Resume Runtime。

完成 DoD 后才能说：

> **基于 LangGraph 构建可恢复 Career Agent Runtime，将 Ranking / Skill Gap 等成熟 Workflow 编排为显式状态图，实现持久化 Checkpoint、Interrupt / Resume、Human-in-the-loop、stale-state guard 与幂等恢复，并建立 20+ trajectory eval 验证执行轨迹和副作用边界。**

---

## 15. 面试必须能回答的问题

1. 为什么 JobLens 需要 LangGraph，而 Ahoy 用 Agents SDK？
2. 为什么不是所有 API 都进 Graph？
3. State 和 Context 有什么区别？
4. State 和业务数据库有什么区别？
5. Checkpoint 是缓存吗？
6. 浏览器关掉以后为什么还能 Resume？
7. Resume 如何防重复执行？
8. Profile 变了，旧 Checkpoint 怎么办？
9. 为什么第一阶段不用 LLM Router？
10. 怎么 Eval 一个 Agent Runtime，而不是只评最终文本？
11. 什么叫 `business_state_writes = 0`？
12. 什么时候才值得引入 Multi-Agent？
