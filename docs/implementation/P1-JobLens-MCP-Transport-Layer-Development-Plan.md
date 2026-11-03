# JobLens MCP 传输层开发计划

- 状态：Design Ready / Implementation Gated
- 目标阶段：vNext 1.3 MCP / External Agent Integration
- 当前建议切片：`P2-T0 Registry-backed MCP Transport Proof`
- 关联 PRD：`docs/product/P1-joblens-mcp-pi-extension.md`
- 真实实现来源：`services/backend/app/agent/tool_registry.py`
- 当前阶段约束：vNext 1.1 Release Gate 尚未正式 COMPLETE；本文件先冻结设计和验收边界，不把设计完成冒充 vNext 1.3 已开始或已完成。

---

## 1. 目标

第一切片不做完整 vNext 1.3，也不一次实现 PRD 中全部 6 个 MCP Tool。

本切片只证明一件事：

> 将现有 `CareerAgentToolRegistry` 中已经成熟、受治理、零 Provider 成本的 3 个只读 Workflow，通过官方 MCP Python SDK 的 STDIO Transport 暴露为标准 MCP Tool，并证明 MCP 适配层不会绕过 JobLens 原有 fail-closed 治理边界。

当前 Registry 已冻结的 3 个 Tool：

```text
rank_match_reports
├─ READ_ONLY
├─ side_effect = read_only
├─ provider_cost = none
├─ human_gate = none
└─ idempotency = read_only

target_cohort_gaps
├─ READ_ONLY
├─ side_effect = read_only
├─ provider_cost = none
├─ human_gate = none
├─ idempotency = read_only
└─ requires_explicit_feedback_selection = true

job_preparation
├─ READ_ONLY
├─ side_effect = read_only
├─ provider_cost = none
├─ human_gate = none
├─ idempotency = read_only
└─ requires_current_job = true
```

这 3 个 Tool 已经有真实 Workflow 委托和 fail-closed 检查，因此 MCP 层不得复制 Ranking / Gap / Preparation 业务规则。

---

## 2. 为什么先做 3 Tool，而不是直接做正式 PRD 的 6 Tool

正式 MCP PRD 第一阶段定义 6 个 Tool：

```text
search_jobs
get_job
get_match_report
rank_jobs
get_skill_gaps
prepare_job
```

其中只有后 3 类已经可以直接复用现有 Career Agent Registry 的成熟能力。

另外 3 个能力还需要独立只读查询边界：

- `search_jobs`：复用 `ListJobsUseCase`；
- `get_job`：复用 `GetJobUseCase`；
- `get_match_report`：PRD 明确要求新增真正 read-only 的 current MatchReport Query，不能复用可能触发生成的 POST 路径。

因此第一切片命名为：

```text
P2-T0 Registry-backed MCP Transport Proof
```

它是 MCP 传输与治理边界的纵向证明，不是整个 vNext 1.3 Release Gate。

完成 P2-T0 后，再进入：

```text
P2-T1 Read-only Query Tools
→ search_jobs / get_job / get_match_report

P2-T2 Full 6-tool MCP Release Gate

P2-T3 Pi Extension Consumer
```

---

## 3. 关键架构原则

### 3.1 MCP 是 Transport Adapter，不是第二套 Agent Runtime

目标调用链：

```text
MCP Client
   ↓ stdio
JobLens MCP Server
   ↓
MCP Tool Adapter
   ↓
CareerAgentContextBuilder
   ↓
CareerAgentToolRegistry.invoke()
   ↓
Existing Application Workflow
   ↓
Grounded JobLens Result
```

禁止：

```text
MCP → 直接 Repository 绕过 Registry
MCP → 自己实现 Ranking
MCP → 自己实现 Gap
MCP → 自己实现 Preparation
MCP → 自动 Requirement Extraction
MCP → 自动 Match 生成
MCP → 自动 UserFeedback / Profile 写入
```

### 3.2 Registry 仍然是安全执行边界

MCP Tool annotations 只是对 MCP Client 的行为提示，不是授权机制。

真正的安全条件继续由：

```text
CareerAgentContextBuilder
+ CareerAgentToolRegistry.definition()
+ CareerAgentToolRegistry.invoke()
```

执行。

即使 MCP Client 忽略 annotations，也不能绕过 Registry。

---

## 4. 代码结构

建议第一切片新增：

```text
services/backend/app/mcp/
├── __init__.py
├── server.py
├── schemas.py
├── context.py
└── errors.py

services/backend/scripts/run_mcp_server.py
services/backend/tests/test_mcp_server.py
services/backend/tests/test_mcp_governance.py
```

### `server.py`

职责：

- 创建官方 MCP Python SDK `MCPServer`；
- 注册允许的 Tool；
- 选择 STDIO transport；
- Tool call 只进入 adapter/context/registry；
- 不包含业务判断；
- stdout 仅用于 MCP wire，日志统一走 stderr / logging。

### `schemas.py`

职责：

- 定义 MCP 外部 Tool 输入；
- 定义统一 Tool Envelope；
- 将 JobLens 结果转换成 JSON-safe structured output；
- 保持 MCP schema 与内部 Domain/Registry schema 的显式边界。

注意：不能简单把 Registry 的 `input_schema` 原样暴露。

最重要的例子是：

```text
TargetCohortGapsRequest
```

内部需要 `cohort_id`，但 MCP PRD 明确规定外部 Consumer 不应该理解这个内部执行标识。

因此 MCP 输入应该是：

```text
get_skill_gaps / target_cohort_gaps
├── selected_job_ids
└── name? = "MCP Target Cohort"
```

由服务器内部生成 transient `cohort_id`。

### `context.py`

职责：

- 为每次 MCP Tool call 建立受治理 `CareerAgentContext`；
- 不创建假的 usable context；
- 必须复用 `CareerAgentContextBuilder`；
- `job_preparation(job_id)` 时，用该显式 Job ID 构造 governed current job；
- rank/gap 不需要 current job 时不额外注入；
- context release 不满足时 fail-closed。

### `errors.py`

负责把现有 JobLens error 映射到稳定 MCP envelope：

```text
CareerAgentToolError
→ invalid_argument / context_not_released / permission_denied

TargetCohortSelectionError
→ invalid_argument / not_found

readiness blocker
→ match_not_ready / context_not_released

unexpected repository/runtime failure
→ backend_unavailable / internal_error
```

第一阶段不能把 Python traceback 直接暴露给 Consumer。

---

## 5. MCP SDK 与传输选择

使用官方 MCP Python SDK 当前稳定 v2 系列：

```toml
mcp>=2,<3
```

第一阶段使用：

```text
MCPServer
+ stdio
```

Server 默认：

```text
mcp.run()
```

即 STDIO。

不手写：

- JSON-RPC framing；
- stdin/stdout 协议；
- initialize / discovery handshake；
- cancellation wire protocol。

也不在第一阶段做：

- Streamable HTTP；
- OAuth；
- remote multi-tenant；
- 公网部署。

---

## 6. Registry Governance → MCP Metadata 映射

不能把“1:1 推导”理解成所有 JobLens 治理字段都有标准 MCP annotation。

标准 MCP ToolAnnotations 只覆盖一部分语义。

建议映射：

| JobLens Definition | MCP | 说明 |
|---|---|---|
| `access == READ_ONLY` | `readOnlyHint=true` | 客户端提示 |
| `side_effect_class == READ_ONLY` | `destructiveHint=false` | 客户端提示 |
| `idempotency_class == READ_ONLY` | `idempotentHint=true` | 客户端提示 |
| JobLens 本地事实库 | `openWorldHint=false` | MCP transport policy，不是 Registry 原字段 |
| `provider_cost_class` | `_meta.joblens.providerCostClass` | MCP 无标准等价 annotation |
| `human_gate_requirement` | `_meta.joblens.humanGateRequirement` | MCP 无标准等价 annotation |
| `timeout_class` | `_meta.joblens.timeoutClass` | MCP 无标准等价 annotation |
| `requires_current_job` | `_meta.joblens.requiresCurrentJob` | JobLens governance |
| `requires_explicit_feedback_selection` | `_meta.joblens.requiresExplicitSelection` | JobLens governance |

重要规则：

> MCP annotations / `_meta` 是描述性证据；`CareerAgentToolRegistry.invoke()` 才是执行时治理。

测试必须证明即使 annotations 被忽略，非法请求仍然无法触发 Workflow。

---

## 7. P2-T0 的 3 个外部 Tool Contract

为了不和正式 6 Tool PRD 混淆，内部第一切片可以先保持 Registry 名称，后续正式 vNext 1.3 再统一为 PRD 的 Consumer-facing 名称。

### 7.1 `rank_match_reports`

MCP 输入：

```text
job_ids: string[]
include_blocked: bool = false
top_n?: int
```

流程：

```text
MCP args
→ RankMatchReportsRequest
→ context_builder.build()
→ registry.invoke(RANK_MATCH_REPORTS)
→ BatchRankMatchReportsUseCase
```

不得自动生成 MatchReport。

### 7.2 `target_cohort_gaps`

外部 MCP 输入不要暴露：

```text
cohort_id
selected_feedback_ids
```

第一阶段统一使用显式 Job selection：

```text
selected_job_ids: string[]
name?: string
```

内部：

```text
mcp_request_id
→ transient cohort_id
→ TargetCohortGapsRequest(selected_job_ids=...)
→ registry.invoke()
```

这与现有 `CreateManualTargetCohortUseCase` 的 transient / db_writes=0 契约一致。

### 7.3 `job_preparation`

MCP 输入：

```text
job_id: string
```

执行时不能直接构造一个假的 `CareerAgentContext(current_job=...)`。

必须：

```text
context_builder.build(current_job_id=job_id)
→ registry.invoke(JOB_PREPARATION, JobPreparationRequest(job_id=job_id))
```

如果 Job 不存在 / context 未 release，则 Registry 前置失败，不调用 Preparation Workflow。

---

## 8. 统一输出 Envelope

P2-T0 即开始使用正式 PRD Envelope：

成功：

```json
{
  "ok": true,
  "data": {},
  "meta": {
    "tool": "rank_match_reports",
    "schemaVersion": "1",
    "traceId": "...",
    "providerCalls": 0,
    "businessWrites": 0
  }
}
```

失败：

```json
{
  "ok": false,
  "error": {
    "code": "invalid_argument",
    "message": "...",
    "retryable": false
  },
  "meta": {
    "tool": "rank_match_reports",
    "schemaVersion": "1",
    "traceId": "...",
    "providerCalls": 0,
    "businessWrites": 0
  }
}
```

第一切片 `traceId` 可以先使用 MCP request identity / adapter trace identity；不得伪造 Backend Provider Trace。

---

## 9. 三条必须先锁定的治理拒绝回归

这是 P2-T0 最重要的验收证据。

### Reject-01：未发布 Career Context

条件：

```text
CareerAgentContext.usable = false
```

调用任意 MCP Tool。

预期：

```text
MCP error = context_not_released
registry workflow invocation = 0
provider_calls = 0
business_writes = 0
```

证明 MCP Transport 没绕开 Context Release Gate。

### Reject-02：Gap 没有显式选择

输入：

```text
selected_job_ids = []
```

预期：

```text
invalid_argument
Gap workflow invocation = 0
Provider calls = 0
Business writes = 0
```

证明外部 Agent 不能自己猜 Target Cohort。

### Reject-03：Preparation 试图切换出 governed current job

测试 adapter / Registry seam：

```text
context current_job = job_1
request job_id = job_2
```

预期：

```text
permission_denied / invalid_argument
Preparation workflow invocation = 0
Provider calls = 0
Business writes = 0
```

证明 MCP Consumer 无法用参数覆盖受治理 current Job。

建议追加第四条：

### Reject-04：未知 Tool

```text
unknown tool
→ MCP method/tool error
→ registry invocation = 0
```

---

## 10. 测试分层

### 10.1 Schema / Metadata Tests

验证 3 Tool discovery：

```text
names exactly match approved allowlist
readOnlyHint = true
idempotentHint = true
providerCostClass = none
humanGateRequirement = none
```

并验证没有暴露：

```text
create_user_feedback
extract_job_requirements
execute_match
任意 SQL / filesystem / URL fetch
```

### 10.2 Adapter Unit Tests

Fake Registry / Fake Context Builder：

- MCP args → 正确内部 request；
- transient cohort id 不暴露给 client；
- envelope 稳定；
- error mapping 稳定；
- annotations 不参与授权判断。

### 10.3 Governance Tests

使用真实 `CareerAgentToolRegistry` + fake workflows：

- Reject-01；
- Reject-02；
- Reject-03；
- workflow call count 必须为 0。

### 10.4 MCP In-process Protocol Tests

官方 SDK Client 直接连接 server object：

```text
initialize
→ list_tools
→ call_tool
```

验证：

- discovery；
- input schema；
- structured output；
- tool annotations；
- error semantics。

### 10.5 STDIO Integration Test

启动：

```bash
cd services/backend
.venv/bin/python -m scripts.run_mcp_server
```

由标准 MCP client / Inspector：

```text
spawn subprocess
→ handshake
→ tools/list
→ tools/call
→ graceful close
```

必须证明 stdout 未被普通日志污染。

---

## 11. 推荐开发批次

### Batch A：Protocol + Discovery

子任务：

1. 增加官方 `mcp>=2,<3` 依赖；
2. 新建 `app/mcp/server.py` + STDIO 入口；
3. 只注册 3 个 Registry-backed Tool；
4. annotations / `_meta` 从 `CareerAgentToolDefinition` 生成。

验收：

```text
3/3 discovery
schema 可读
annotations 正确
server 可通过 stdio handshake
```

由于新增第三方依赖与 lockfile，这一批完成后应立即收口、测试，不继续扩下一个大模块。

### Batch B：Governed Context + Invocation

子任务：

1. `context.py` 复用真实 `CareerAgentContextBuilder`；
2. MCP 外部 args → Registry Request adapter；
3. `registry.invoke()` 成为唯一 Tool workflow 执行入口；
4. structured envelope / error mapping。

验收：

```text
3/3 happy path
Provider calls = 0
Business writes = 0
```

### Batch C：Fail-closed Evidence

子任务：

1. Reject-01；
2. Reject-02；
3. Reject-03；
4. 可选 unknown tool。

验收重点不是 HTTP/MCP error 文案，而是：

```text
underlying workflow calls = 0
```

### Batch D：STDIO E2E + Docs

子任务：

1. 标准 MCP Client / Inspector E2E；
2. run command；
3. README / architecture / demo；
4. 明确 local single-user boundary。

完成后才能声明：

> 已实现 JobLens MCP Server 的第一条 Registry-backed STDIO 纵向链。

仍不能声明完整 6-tool / Pi Extension / remote MCP 已完成。

---

## 12. 完成标准：P2-T0

只有全部满足才算 P2-T0 COMPLETE：

- [ ] 官方 MCP SDK 依赖已引入并锁定；
- [ ] STDIO Server 可由标准 MCP Client 初始化；
- [ ] 3/3 Registry Tool 可 discovery；
- [ ] annotations 与 JobLens governance metadata 可审计；
- [ ] 外部 schema 不泄露内部 cohort_id；
- [ ] Tool 只通过 `CareerAgentToolRegistry.invoke()` 执行；
- [ ] context 只通过 `CareerAgentContextBuilder` 构造；
- [ ] 3 条 fail-closed governance rejection 全通过；
- [ ] Reject 后底层 workflow invocation = 0；
- [ ] Provider calls = 0；
- [ ] business-state writes = 0；
- [ ] unknown/unregistered capability 未暴露；
- [ ] STDIO E2E 通过；
- [ ] backend targeted regression + full regression + compileall + diff-check 通过；
- [ ] README/实现文档明确 local-only / read-only / no-Provider 边界。

---

## 13. 与完整 vNext 1.3 的关系

P2-T0 完成后，正式 vNext 1.3 仍有以下工作：

```text
P2-T1
├─ search_jobs
├─ get_job
└─ get_match_report read-only query

P2-T2
├─ 对外统一 6 Tool naming
├─ cancellation / timeout
├─ full read-only release gate
└─ 真实 JobLens DB E2E

P2-T3
├─ Pi Extension MCP Client
├─ 6 Tool registration
├─ 4 Slash Commands
├─ Session state
└─ Pi → MCP → JobLens E2E
```

因此简历声明分阶段：

### P2-T0 完成后可以写

> 基于现有受治理 Tool Registry，实现 JobLens MCP Server 的本地 STDIO 传输层，将 Ranking / Skill Gap / Job Preparation 等成熟只读 Workflow 暴露为标准 MCP Tools，并通过上下文发布门禁、显式选择和 current-job 约束验证 fail-closed 执行边界。

### 完整 Release Gate 通过后再写

> 实现 JobLens MCP Server，将 Job Search / Match / Ranking / Skill Gap / Preparation 等受治理能力暴露为标准 MCP Tools，并开发 Pi Extension 作为真实 MCP Consumer。

不得提前声明：

- remote multi-tenant MCP；
- HTTP/Auth MCP Service；
- 自动 Match / Requirement；
- 自动投递；
- Pi 原生自带 JobLens MCP。

---

## 14. 当前是否立即开发

从当前仓库 `ROADMAP.md` 看，vNext 1.1 仍处于 Agent B 模型质量 Release Gate 阶段，尚未正式标记 COMPLETE，并明确在 Gate / DoD 关闭前不进入下一主阶段。

因此当前最稳妥的动作是：

```text
现在：冻结本设计 + 准备 P2-T0 failing tests / branch plan

vNext 1.1 Release Gate 关闭后：
立即创建 vNext 1.3 MCP Transport slice
→ Batch A
→ Batch B
→ Batch C
→ Batch D
```

如果 Integration Owner 明确改变主线优先级并授权跳过现有阶段顺序，则以新的阶段决策为准；否则不把 MCP 代码提前混入当前 `agent-a/vnext11-provider-gate-handoff` 分支。
