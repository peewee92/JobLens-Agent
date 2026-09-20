# JobLens 双电脑双 Agent 分工执行文档

- 状态：Active
- 当前本地共享基线：Agent B 确定性 A 门、Durable HITL Dispatch Trajectory 与 Agent A latency/deadline evidence 已收敛到本地 `main`；`origin/main` 仍待 Integration Owner 后续显式同步
- 当前主线：`vNext 1.1 Natural Language + Bounded Multi-turn Tool Calling`
- 目标：两台电脑并行推进同一 Milestone，但避免重复开发、互相覆盖和跨阶段抢跑。
- 上位协作方案：`docs/implementation/P1-JobLens-Multi-Agent-Development-Collaboration-Plan.md`
- 当前阶段 PRD：`docs/product/P1-career-agent-natural-language-tool-loop-prd.md`

---

## 0. 当前 Core → Eval Handoff（2026-09-20）

Agent A 与 Agent B 的 vNext 1.1 确定性主链现已在本地 `main` 收敛：Intent 60-case、Tool Selection 44-case、Loop Guard 26-case 与 Trajectory 38-case 已和最新 Core 同树验证。Agent B Cycle 4 v2 已确认 GAP-5 / GAP-7 / GAP-8 / GAP-3 修复真实生效，四个 A 门合计 69 tests 全绿。

当前新的 Core → Eval 边界为：

```text
CareerIntentRouter / CareerIntentResolver
→ CareerAgentRuntimeDispatcher
   ├─ simple / read-only intent
   │    → CareerAgentGovernedLoopRuntime
   │    → Tool Selector → Execution Gate → Registry → AgentToolResult → LoopGuard / Trace
   └─ rank_jobs → review_gaps
        → existing CareerAgentHitlService
        → Ranking → durable Target Cohort interrupt
        → approve / edit / reject
        → stale validation
        → Skill Gap resume
```

`CareerAgentRuntimeDispatcher` 不重新解释自然语言，只接收已经结构化的 `CareerIntent`，并再次执行 deterministic Job-scope resolution。显式 Job refs 只能缩小当前 frozen run scope；scope 外 Job 必须在任何 Durable Runtime / Workflow 执行前拒绝。`rank_jobs → review_gaps` 必须携带显式 thread/run/request identity，并直接复用 vNext 1.0 Durable HITL，禁止在 governed loop 内复制第二套 interrupt/resume。其他 Intent 通过 `resolved_intent` seam 进入 governed loop，避免模型 Router 被重复调用，同时保留 resolver / stale / Tool Registry / Human Gate 边界。

Agent B 已把 Dispatcher 纳入 Trajectory Gate，并以真实 SQLite durable path 证明 `Ranking → HITL → Gap`，GAP-6 已从 partial 收敛为 covered。当前确定性 Trajectory 为 9 covered / 0 partial / 1 blocked；唯一剩余 GAP-1 `cost action → PendingAction` 不是 Core 治理能力缺失：Execution Gate 已对 `provider_compute / business_write / external_action` 生成 PendingAction 并阻止 Workflow 自动执行，但当前 v1.1 Registry 按产品边界只注册成熟 read-only Workflow，因此不得为了 Eval 伪造收费 Tool。未来首个真实 cost-gated Workflow 进入 Registry 时必须重新激活该轨迹 Gate。

Agent A 随后补齐 Release Gate 所需的 Runtime 可观测与总时限 seam：`CareerAgentGovernedLoopResult` 暴露总 `runtime_latency_ms` 与统一 `terminal_reason`，计时使用可注入 monotonic clock，并刻意不进入 deterministic trace fingerprint；同时 `max_runtime_seconds` 现在会建立单一 deadline，并在每次 Tool attempt（含 retry/replan 后的下一次执行）开始前强制检查，耗尽即 `failed/runtime_timeout`，不得再启动新的 Workflow 调用。因此 Agent B 可以直接聚合 P95 Tool Loop latency 基线，也能验证 runtime timeout 不被绕过。剩余 vNext 1.1 Gate/DoD 集中为：1) Provider B 门的 Intent / Tool Selection 模型层准确率（目标 >=95%）；2) Agent B 基于真实运行样本产出 P95 latency 基线并解释；3) Integration Owner 对 GAP-1 当前 Registry 范围作最终 Release Gate 裁决；4) 主动 cancellation 与最小 Chat UI 仍需 Agent A 独立收口。Agent A 不因这些剩余项提前进入 vNext 1.2。

---

## 1. 总原则

两台电脑不是两条产品主线。

始终只有一个产品顺序：

```text
vNext 1.1 Natural Language + Bounded Tool Calling
→ vNext 1.2 Job Search Execution Layer
→ vNext 1.3 MCP / External Agent Integration
→ vNext 2.0 Continuous Career Agent
```

当前两台电脑只允许在 `vNext 1.1` 内并行。

禁止：

- 一台做 vNext 1.1，另一台提前做 vNext 1.2；
- 两台电脑同时直接开发同一个 Runtime 核心模块；
- 两个 Agent 同时修改 `main`；
- Multi-Agent 架构；
- 漂亮 Dashboard；
- 无关平台化；
- 低价值重构；
- 为追求 commit 数量而制造工作。

核心指标只有：

> **Milestone Advancement**

---

# 2. Agent A：主电脑 / 当前每小时自动推进任务

## 2.1 角色

**Core Builder**

负责 vNext 1.1 的核心产品能力与 Runtime 主实现。

当前每小时 `JobLens 里程碑主线推进` 自动任务归属于 Agent A。

---

## 2.2 严格开发顺序

Agent A 只能按下面顺序推进：

```text
A1 CareerIntent Contract
→ A2 Intent Router
→ A3 Grounded Entity Resolution / Clarification / Unsupported Request
→ A4 Dynamic coarse-grained Tool Selection
→ A5 Bounded Multi-turn Tool Loop
→ A6 Context Budget / Error Classification
→ A7 PendingAction / Cost / Durable HITL Integration
```

在前一个 Slice 未达到可验证完成标准前，不进入下一个 Slice。

---

## 2.3 当前第一任务

当前 Agent A 第一任务固定为：

```text
CareerIntent Contract
+ Intent Router
+ Grounded Job Reference Resolution
+ Clarification / Unsupported Request Contract
```

对应 PRD：

`docs/product/P1-career-agent-natural-language-tool-loop-prd.md`

需要实现的正式结构至少覆盖：

```text
CareerIntent
├── goals[]
├── referenced_job_ids[]
├── current_job_required
├── needs_clarification
├── clarification_question
├── unsupported_request
├── confidence
└── reasoning_summary
```

必须遵守：

- 不保存 Chain of Thought；
- `reasoning_summary` 只允许短的可审计理由；
- Job 引用只能来自显式 Job ID、current job、当前 Run scope；
- 不允许根据模糊岗位标题猜 Job；
- 不支持的自动投递/联系 HR/绕过人工门禁必须 structured reject；
- 不自动写 Profile/UserFeedback/Requirement/MatchReport；
- 不引入 Multi-Agent。

---

## 2.4 Agent A 默认文件所有权

优先修改：

```text
services/backend/app/agent/**
services/backend/app/application/**
services/backend/app/api/**              # 仅当前 Slice 必须时
核心 Runtime / Contract tests
```

Agent A 不主动承担大规模 Eval Dataset 建设。

尤其不要和 Agent B 同时大面积修改：

```text
services/backend/app/evals/**
data/evals/**
```

---

## 2.5 Agent A 每轮完成标准

每轮必须：

1. 读取 `AGENTS.md`；
2. 读取当前 PRD / ROADMAP；
3. 检查 branch / status / diff / log；
4. 保护用户未提交修改；
5. 先建立失败回归；
6. 再实现最小纵向 Slice；
7. 运行 targeted tests；
8. 重要 Backend 修改运行相关全量 pytest / compileall / diff-check；
9. 不自动进入下一 Milestone；
10. 输出 Handoff。

进入双电脑正式并行后，Agent A 应在自己的 feature branch 开发，而不是长期直接修改 `main`。

推荐分支：

```text
agent-a/vnext11-intent
agent-a/vnext11-tool-selection
agent-a/vnext11-tool-loop
agent-a/vnext11-context-hitl
```

---

# 3. Agent B：第二台电脑 / Eval + Safety Builder

## 3.1 角色

**Eval / Safety Builder**

Agent B 的职责不是再实现一套 Career Agent Runtime。

它负责把 Agent A 的正式 Contract 和 PRD 验收标准变成：

```text
Dataset
→ Eval
→ Bad Case
→ Guard
→ Regression
→ Trace / Release Gate
```

---

## 3.2 Agent B 当前第一任务

Agent B 第一任务固定为：

> **建立并冻结 vNext 1.1 的 60+ Intent Eval Dataset + Intent Eval Runner。**

先读取：

1. `AGENTS.md`
2. `docs/product/P1-career-agent-natural-language-tool-loop-prd.md`
3. `docs/implementation/P1-JobLens-Multi-Agent-Development-Collaboration-Plan.md`
4. 本文档中的 `Agent B` 全部章节
5. 当前 `main` 最新提交和 Agent A 已合入/已冻结的 Intent Contract

---

## 3.3 60+ Intent Eval Dataset 最低组成

至少包含：

```text
15 single-goal
15 multi-goal
10 current-job / pronoun
10 clarification
10 unsupported / unsafe
```

### single-goal 示例类别

- 哪些岗位最值得投；
- 看共同技能差距；
- 准备某个明确 Job；
- 查看当前 Ranking；
- 当前岗位是否值得继续。

### multi-goal 示例类别

必须验证顺序：

```text
先 Ranking，再 Gap
先 Ranking，再 Preparation
先选择目标岗位，再看 Gap
```

不能把多个 goal 压成一个。

### current-job / pronoun

例如：

```text
“这个岗位怎么样？”
“这个我面试前应该准备什么？”
```

若存在合法 current job，可以解析；不存在时必须 clarification。

### clarification

至少覆盖：

- 没有 current job；
- 请求过于模糊；
- 多个候选实体无法唯一确定；
- 缺少执行所需的 Job scope。

### unsupported / unsafe

至少覆盖：

- 自动批量投递；
- 自动联系招聘者；
- 自动修改人工 Review；
- 绕过 evidence gate；
- 绕过 Human Gate；
- 要求执行不存在的业务能力。

必须验证：

> unauthorized execution = 0

---

## 3.4 Agent B 当前允许做什么

允许：

- 设计 Eval case schema；
- 新增 60+ Intent cases；
- 建立 deterministic Eval runner；
- 建立 expected goal / clarification / unsupported assertions；
- 建立 grounded entity resolution regression；
- 建立 forbidden action regression；
- 发现真实 Bad Case 后冻结 regression；
- 对已经冻结的 Core Contract 写测试；
- 使用 fixture / replay / isolated SQLite；
- 提供 Agent A 可消费的失败证据。

---

## 3.5 Agent B 当前禁止做什么

禁止：

- 自己实现第二套 Intent Router；
- 自己实现第二套 Tool Registry；
- 自己改写 Agent Runtime 架构；
- 提前实现 Bounded Multi-turn Loop；
- 提前进入 vNext 1.2；
- 开始 MCP；
- Multi-Agent；
- 修改人工 Final Decision；
- 写真实业务事实；
- 修改真实 SQLite Runtime DB；
- 为让 Eval 通过而私自改变正式产品 Contract。

若发现 Core Contract 不足：

```text
先写 failing regression
→ 记录 Contract Gap
→ 在 Handoff 中交给 Agent A / Integration Owner
```

不要自己绕开正式 Contract。

---

## 3.6 Agent B 默认文件所有权

优先修改：

```text
services/backend/app/evals/**
data/evals/**
Eval fixtures
Eval / guard / trajectory tests
```

若仓库现有 Eval 目录命名不同，以当前真实结构为准，但原则不变：

> Eval Builder 优先修改 Eval / fixture / regression，不抢 Runtime 核心实现。

推荐分支：

```text
agent-b/vnext11-intent-eval
```

后续：

```text
agent-b/vnext11-tool-selection-eval
agent-b/vnext11-tool-loop-eval
agent-b/vnext11-trajectory-eval
```

---

# 4. Agent B 第一轮明确 DoD

第一轮只做到以下范围：

```text
60+ Intent Dataset
+ Intent Eval Runner
+ failing/pass assertions
+ grounded/clarification/unsupported coverage
+ targeted tests
```

完成标准：

- Case 数量 ≥ 60；
- 五类最低数量满足 PRD；
- 每个 Case 有稳定唯一 ID；
- 每个 Case 至少包含输入、上下文条件、expected intent/action；
- unsupported / unsafe 自动执行率必须为 0；
- current-job 缺失时不能猜实体；
- multi-goal 顺序可以验证；
- Eval runner 能产生结构化 pass/fail；
- 新失败能够定位到具体 Case；
- 不调用真实 Provider，除非 Integration Owner 另行明确授权该 Eval；
- 不写业务状态；
- `git diff --check` 通过；
- 提交一个 cohesive commit；
- push 只推自己的 Agent B branch；
- 不 merge `main`。

---

# 5. Agent B 第一轮结束后的 Handoff

Agent B 必须输出：

```text
Base SHA:
Head SHA:
Branch:

Milestone:
vNext 1.1

Slice:
Intent Eval Dataset + Runner

Changed paths:

Dataset summary:
- total:
- single-goal:
- multi-goal:
- current-job/pronoun:
- clarification:
- unsupported/unsafe:

Eval runner capability:

Tests:
- targeted:
- backend full:
- compileall:
- diff-check:

Provider attempts/completed:
Business writes:

Contract gaps found:

Known blockers:

Files intentionally not touched:

Recommended next Agent B slice:
```

Integration Owner 根据 Handoff 决定是否合并，以及是否进入下一轮 `Tool Selection Eval`。

Agent B 不自行宣布 vNext 1.1 Intent COMPLETE。

---

# 6. 两台电脑之间的同步方式

唯一共享真相源：

```text
origin/main
+ feature branch
+ commit SHA
+ Handoff
```

禁止依赖聊天记忆同步工程事实。

第二台电脑每次开始工作前：

```text
git fetch origin
```

然后确认：

```text
origin/main
```

是否发生变化。

如果 Agent A 已把新的 Contract 合入 `main`：

Agent B 应先同步最新基线，再继续 Eval。

不要在两台电脑之间同步：

- `.env`；
- API Key；
- 本地 SQLite DB；
- Runtime checkpoint DB；
- 私有 Profile / Resume；
- 未脱敏的真实数据。

---

# 7. 合并责任

Agent A 与 Agent B 都不负责最终双向合并。

最终由 Integration Owner：

```text
fetch Agent A branch
fetch Agent B branch
→ 审 Core Contract
→ 审 Eval contract
→ 先合 Core
→ 再合 Eval
→ 跑全量验证
→ 更新 ROADMAP
→ 合入 main
```

冲突优先级：

```text
AGENTS.md
→ 当前 PRD
→ Frozen Contract
→ Integration Owner decision
→ Eval fixture
```

原则：

> Eval 适配正式 Contract；不能为了让 Eval 变绿而偷偷改变产品边界。

---

# 8. 当前立即执行分工

## Agent A / 当前主电脑自动任务

立即做：

```text
CareerIntent Contract
→ Intent Router
→ Grounded Job Reference Resolution
→ Clarification / Unsupported Request
```

之后再进入：

```text
Tool Selection
→ Bounded Tool Loop
→ Context/Error
→ PendingAction/HITL
```

---

## Agent B / 第二台电脑

立即做：

```text
60+ Intent Eval Dataset
→ Intent Eval Runner
```

本轮不要做：

```text
Tool Loop
MCP
vNext 1.2
Multi-Agent
Web Chat UI
```

完成第一轮并提交 Handoff 后停止，由 Integration Owner 判断下一任务。

---

# 9. 给第二台电脑 Agent 的一句话任务定义

> 你是 JobLens vNext 1.1 的 Agent B / Eval + Safety Builder。严格读取本文件的 Agent B 章节，当前只负责 60+ Intent Eval Dataset + Intent Eval Runner，不实现第二套 Intent Router，不进入 Tool Loop/vNext 1.2/MCP/Multi-Agent；基于最新 `origin/main` 创建 `agent-b/vnext11-intent-eval`，完成 tests、commit、push 自己分支，并按 Handoff Contract 汇报。
