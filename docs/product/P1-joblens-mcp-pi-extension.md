# P1 JobLens MCP Server + Pi Extension 产品需求文档

- 状态：Planned / vNext 1.3 / 第一阶段范围已冻结
- 目标阶段：vNext 1.3 MCP / External Agent Integration
- 前置条件：vNext 1.0 Agent Runtime 稳定；vNext 1.1 Natural Language / Tool Registry 边界稳定；vNext 1.2 求职执行层不要求全部完成，但 MCP 第一阶段只暴露已经成熟的只读能力
- 核心目标：把 JobLens 已有、受治理、可评测的业务能力通过 MCP 暴露给外部 Agent，并以 Pi Extension 作为首个真实 Consumer
- 关联决策：`docs/decisions/0004-llm-workflow-agent-boundary.md`
- 关联架构：`docs/architecture/SYSTEM-ARCHITECTURE.md`
- 关联实现：`services/backend/app/agent/tool_registry.py`
- 外部参考：Pi Extension 支持注册 LLM Tool、Slash Command、生命周期事件和 Session State；本需求只把 Pi 当作 Consumer，不把 Pi 业务逻辑带入 JobLens Domain

---

## 1. 背景

JobLens 已经具备成熟的内部业务能力：

- Job Pool 查询；
- Job Detail；
- current MatchReport / Ranking；
- Target Cohort / Skill Gap；
- Job Preparation；
- Career Agent Tool Registry。

但这些能力当前主要通过 JobLens Web / REST API / 内部 Agent Runtime 消费。为了验证 JobLens 是否能成为一个真正可复用的 Agent Capability Provider，需要建立标准化外部工具边界。

目标不是“给所有 API 套一层 MCP”，而是：

> **把稳定、粗粒度、受治理的 JobLens Workflow 作为 MCP Tool 暴露，并让真实 Coding Agent（Pi）在自己的 Agent Loop / Session 中调用它。**

目标架构：

```text
                     Pi Coding Agent
                          │
                joblens-pi-extension
                          │
                 MCP Client Adapter
                          │
                          ▼
                  JobLens MCP Server
                          │
                  Application Use Cases
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
      Jobs             Match             Gap / Prepare
                          │
                          ▼
                    JobLens Backend
```

原则：

> MCP 是协议 / Tool Boundary；Pi Extension 是 Consumer / UX；JobLens Backend / Workflow 仍然是唯一业务事实与规则来源。

---

## 2. 产品目标

### 2.1 一句话目标

> 用户在 Pi 中可以搜索自己的 JobLens 岗位池、查看岗位与匹配结果、排序岗位、分析技能差距和生成准备材料，而不需要复制 JD、简历或重新让 Pi 自己推断 JobLens 业务事实。

### 2.2 第一阶段必须证明的能力

- MCP Server 可以被标准 MCP Client 发现并调用；
- Tool Schema 清晰、稳定、粗粒度；
- Tool 复用 JobLens 已有 Application Workflow；
- Tool 不绕过 Release Gate；
- 第一阶段全部是 read-only / transient；
- Tool 不自动触发 Provider 成本；
- Pi Extension 可以注册 JobLens Tool 并提供 4 个 Slash Command；
- Pi Session 能消费 JobLens Tool Result 并继续自己的 Agent Loop；
- Backend / MCP / Pi 三层错误能够区分；
- Demo、测试和 README 可以让招聘方复现。

---

## 3. 明确不做什么

第一阶段不做：

- 把每个 REST Endpoint 都转成 MCP Tool；
- MCP Tool 内重新实现 Ranking / Gap / Preparation；
- MCP 自动生成 MatchReport；
- MCP 自动执行 Requirement Extraction；
- MCP 写 UserFeedback；
- MCP 修改 Profile / SearchIntent；
- 自动投递职位 / 自动联系招聘者；
- MCP 远程公网部署；
- Multi-user OAuth；
- Pi Extension 直接访问 JobLens 数据库；
- Pi Extension 自己重写 JobLens 排序规则。

---

## 4. 边界与代码位置

### 4.1 JobLens MCP Server

第一阶段作为 Backend 内的 Adapter 层存在：

```text
services/backend/app/mcp/
├── server.py
├── tools.py
├── schemas.py
└── errors.py

services/backend/scripts/run_mcp_server.py
```

MCP Server 调用现有 Application Use Case / Query Repository，不复制业务逻辑。

### 4.2 Pi Extension

Pi Extension 是新的用户入口，适合放在已有 pnpm workspace 的 `apps` 层：

```text
apps/pi-extension/
├── package.json
├── src/
│   ├── index.ts
│   ├── mcp-client.ts
│   ├── tools.ts
│   ├── commands.ts
│   ├── session.ts
│   └── errors.ts
└── tests/
```

理由：`apps` 在 JobLens 架构中表示用户入口；Pi Extension 是通过 Pi 访问 JobLens 的新入口，而不是共享 Domain Package。

---

## 5. Transport 决策

### 5.1 第一阶段：STDIO

第一阶段使用本地 STDIO MCP Server：

```text
Pi Extension
→ spawn / connect JobLens MCP Server
→ MCP stdio
→ Backend Application Use Cases
```

理由：

- JobLens 当前仍是 local-first / SQLite-first；
- 免去公网认证、TLS 与多租户问题；
- 更适合本地 Pi / Claude / MCP Inspector 验证；
- 更容易证明 Tool Contract，而不是先做部署平台。

### 5.2 后续可选：Streamable HTTP

只有出现远程 Consumer / 多用户需求时，再增加 Streamable HTTP + Auth。

第一阶段文档和简历不得声称“已完成远程 MCP Service”。

---

## 6. MCP Tool 列表

第一阶段固定为 6 个 Tool。

## 6.1 `search_jobs`

用途：查询 JobLens 已导入的岗位池。

输入：

```text
q?
city?
min_salary_k?
remote_status?
source?
sort?
limit?          default 20, max 50
offset?         default 0
```

复用：现有 `ListJobsUseCase`。

禁止：

- 调用 Collector；
- 打开外部招聘网站；
- 触发 Requirement / Match。

输出只使用公开 Job List 字段。

## 6.2 `get_job`

输入：`job_id`

复用：现有 `GetJobUseCase`。

输出：公开 Job Detail。

不得返回：

- `source_raw`；
- 内部 canonical identity；
- secret / local path；
- 未公开内部字段。

## 6.3 `get_match_report`

用途：读取 current persisted MatchReport。

### 当前缺口

当前 REST 中 `POST /job-requirements/{job_id}/match-report` 是生成命令，可能触发 Match / Provider，不可直接作为 MCP read tool。

第一阶段必须增加一个真正 read-only 的 current MatchReport Query：

```text
GetCurrentMatchReportUseCase
→ AbstractMatchReportQueryRepository.list_latest_for_jobs((job_id,))
```

如果不存在 current report：

```text
status = not_ready
blocker = match_report_missing
```

禁止 MCP 自动生成。

## 6.4 `rank_jobs`

输入：

```text
job_ids     1..50
include_blocked = false
top_n?      1..50
```

复用现有 `BatchRankMatchReportsUseCase` / `rank_match_reports`。

如果部分岗位没有 current MatchReport，应返回结构化 blocker / unavailable jobs，不自动补计算。

## 6.5 `get_skill_gaps`

面向 MCP Consumer 的输入不暴露内部 `cohort_id`：

```text
selected_job_ids  1..20
name?             optional, default "MCP Target Cohort"
```

MCP Adapter 在服务端生成本次 transient `cohort_id`（基于 request ID / UUID），再复用现有 `CreateManualTargetCohortCommand` + Gap Workflow。

理由：`cohort_id` 是 JobLens 内部执行标识，不应该要求外部 Agent 理解；MCP Consumer 只需要表达“分析这些岗位的共同差距”。同时，Consumer 显式选择 Job，不应该为了查询 Gap 先写 UserFeedback。

输出：结构化 Target Cohort Gap / Action Plan facts。

## 6.6 `prepare_job`

输入：`job_id`

复用现有 `BuildJobPreparationBundleUseCase`。

输出：当前 grounded Preparation bundle。

如果 Requirement / Match readiness 不满足，返回 blocker，不自动触发上游 Provider 工作。

---

## 7. Tool 通用契约

### FR-MCP-01：全部第一阶段 Tool 必须 read-only / transient

```text
business_state_writes = 0
Provider calls        = 0
External writes       = 0
```

允许 MCP / Backend 写 Trace、metrics 等运行态观测数据，但不得修改 Profile、SearchIntent、JobRequirement、MatchReport、UserFeedback 等业务事实。测试和 Release Gate 必须区分业务写入与 telemetry 写入。

### FR-MCP-02：统一 Tool Envelope

成功：

```json
{
  "ok": true,
  "data": {},
  "meta": {
    "tool": "rank_jobs",
    "schemaVersion": "1",
    "traceId": "..."
  }
}
```

失败：

```json
{
  "ok": false,
  "error": {
    "code": "match_not_ready",
    "message": "...",
    "retryable": false
  },
  "meta": {
    "tool": "rank_jobs",
    "schemaVersion": "1",
    "traceId": "..."
  }
}
```

### FR-MCP-03：错误代码至少区分

- `invalid_argument`；
- `not_found`；
- `context_not_released`；
- `match_not_ready`；
- `permission_denied`；
- `business_invariant`；
- `backend_unavailable`；
- `timeout`；
- `cancelled`；
- `internal_error`。

### FR-MCP-04：Tool 描述禁止夸大

Tool Description 必须说明：

- 数据来自 JobLens 已确认 / 已发布事实；
- Tool 是否需要 current MatchReport；
- Tool 不会自动调用 Provider；
- Tool 不能被解释为“录用概率”。

---

## 8. Pi Extension 需求

Pi 官方 Extension API 支持 `registerTool()`、`registerCommand()`、生命周期事件和 Session State。JobLens Pi Extension 使用这些原生扩展点，不修改 Pi Core。

### FR-PI-01：注册 JobLens MCP Tools

Extension 启动后：

1. 创建一个 Session 级 MCP Client；
2. 通过 STDIO 启动 / 连接一个 JobLens MCP Server 子进程，而不是每次 Tool Call 重新启动；
3. Discover 允许的 6 个 Tool；
4. 将其注册为 Pi LLM-callable Tool；
5. Tool 名增加 `joblens_` 前缀，避免与其他 Extension 冲突；
6. Pi Session 结束 / reload 时关闭 MCP Client 与子进程，避免 orphan process。

默认启动命令通过 Extension 配置给出；实现时使用官方 MCP SDK 的 STDIO Client Transport，不手写 JSON-RPC framing。

例如：

```text
joblens_search_jobs
joblens_get_job
joblens_get_match_report
joblens_rank_jobs
joblens_get_skill_gaps
joblens_prepare_job
```

Pi Tool wrapper 只负责：

- TypeBox / JSON Schema 参数映射；
- MCP 调用；
- cancellation propagation；
- Tool result render；
- error mapping。

不得写 JobLens 业务规则。

### FR-PI-02：四个 Slash Commands

```text
/job-search
/job-rank
/job-gap
/job-prepare
```

#### `/job-search <query>`

调用 `joblens_search_jobs`，把返回的 Job IDs 保存为 `last_job_ids`。

第一阶段 Slash Command 只要求 query；city / salary / remote 等高级筛选通过 LLM Tool 参数或后续 Command flags 扩展，不在 P0 命令解析器里重复造 DSL。

#### `/job-rank [job ids]`

- 显式传 ID 时使用这些 Job；
- 未传 ID 时使用 `last_job_ids`；
- 两者都没有时返回 `no_job_selection`，不猜测。

成功后保存 `last_ranked_job_ids`。

#### `/job-gap [job ids]`

- 显式传 ID 时分析这些 Job；
- 未传 ID 时取 `last_ranked_job_ids` 前 5 个，并在执行前通过 Pi UI 要求用户确认；
- 用户拒绝即取消，不调用 MCP。

成功后保存 `last_selected_job_ids`。

#### `/job-prepare <job id>`

必须有一个明确 Job ID；第一阶段不通过标题模糊匹配自动猜 Job。

调用 `joblens_prepare_job`。

Command 是用户快捷入口；同一 MCP Tool 也必须可由 LLM 自主调用。

### FR-PI-03：Session State

允许在 Pi Session 中保存轻量 JobLens context：

```text
last_search_query
last_job_ids
last_ranked_job_ids
last_selected_job_ids
```

禁止保存：

- API Key；
- raw resume；
- raw JD；
- MCP secret；
- 大型 Tool Output。

Session State 使用 Pi 原生 Extension session persistence（例如 extension entry / session state），不另建一套隐藏数据库。

Session 恢复后，JobLens ID 必须重新通过 Tool 查询 current facts，不能把旧 Tool Result 当事实源。

### FR-PI-04：用户体验

当 MCP Server 不可用时，不允许 Pi 模型“假装已经查询 JobLens”。

必须明确显示：

```text
JobLens unavailable
```

并提供启动 / 配置提示。

---

## 9. MCP 与 Pi 的职责分离

| 层 | 负责 | 不负责 |
|---|---|---|
| JobLens Domain / Workflow | 业务事实、规则、Release Gate | Agent UX |
| MCP Server | Tool Contract、协议、错误映射 | Ranking / Gap 业务实现 |
| Pi Extension | Tool 注册、Command、Session UX | JobLens Domain Rule |
| Pi Agent | 理解自然语言、选择 Tool、解释结果 | 修改 JobLens 事实 |

核心原则：

> Pi 可以决定“调用哪个 JobLens Tool”，但不能决定“JobLens 的事实规则是什么”。

---

## 10. Security / Permission

### FR-SEC-01：本地信任边界

第一阶段 STDIO MCP 与本地 JobLens Backend 运行在同一用户机器，属于 single-user local trust boundary。

这不是多租户安全模型。

### FR-SEC-02：最小能力

第一阶段只暴露 6 个 read-only Tool。

禁止暴露：

- 任意 SQL；
- 文件系统；
- arbitrary URL fetch；
- Provider Key；
- raw database query；
- 任意 Backend method invocation。

### FR-SEC-03：未来 HTTP Transport

若未来增加 Streamable HTTP，必须单独设计：

- authentication；
- authorization；
- user / workspace boundary；
- rate limit；
- audit；
- CSRF / origin / network exposure。

不得把 local stdio 信任模型直接搬到公网。

---

## 11. Cancellation / Timeout / Retry

### FR-MCP-05：Cancellation

Pi Extension 的 `AbortSignal` 必须向 MCP request 传播。

被取消后 Tool 不得继续在后台运行并把旧结果写回当前 Session。

### FR-MCP-06：Timeout

每个 read tool 必须有 bounded timeout。

第一阶段建议：

```text
search/get     5s
rank/gap       10s
prepare        10s
```

实际值可实现时按本地数据量校准，但不能无限等待。

### FR-MCP-07：Retry

- 参数错误：不重试；
- not ready / permission / invariant：不重试；
- stdio connection reset：最多一次 reconnect；
- Tool execution 是否重试由 Tool idempotency 决定。

第一阶段全部 Tool read-only，因此允许连接层一次有限重连，但不得无限循环。

---

## 12. Trace / Observability

MCP Tool 调用至少记录：

```text
mcp_request_id
pi_session_id?        # consumer 提供时
joblens_trace_id
tool
input_summary
start/end/duration
result_status
error_code
provider_calls
db_writes
```

必须能够证明：

- Tool 是否真的调用了 JobLens；
- Tool 使用哪个业务 Use Case；
- 是否触发 Provider；
- 是否发生写入；
- Pi 失败是 MCP、Backend 还是业务 blocker。

---

## 13. 测试与验收

## 13.1 MCP Server 测试

至少覆盖：

1. 6 个 Tool 均可 discovery；
2. 参数 Schema；
3. Job search filters；
4. Job not found；
5. MatchReport exists / missing；
6. Ranking 部分 unavailable；
7. manual selected_job_ids Gap；
8. Preparation readiness blocker；
9. cancellation；
10. backend / repository error mapping；
11. Provider calls = 0；
12. DB writes = 0。

## 13.2 Pi Extension 测试

至少覆盖：

1. MCP connect；
2. MCP unavailable；
3. 6 Tool 注册；
4. Tool schema mapping；
5. cancellation propagation；
6. `/job-search`；
7. `/job-rank`；
8. `/job-gap`；
9. `/job-prepare`；
10. Session state restore 不复用旧事实结果。

## 13.3 E2E Demo

必须可以真实演示：

```text
$ pi

/job-search AI Agent
→ 返回 JobLens Job Pool

/job-rank <selected jobs>
→ current MatchReport ranking

/job-gap <top jobs>
→ grounded gap facts

/job-prepare <job>
→ preparation bundle
```

并额外演示一次自然语言：

> “从刚才搜到的岗位里，帮我挑最值得投的几个，再告诉我共同短板。”

Pi 必须通过已注册 JobLens Tool 完成，不允许把 Tool Output 缺失时自行编造 JobLens 数据。

---

## 14. Release Gate

第一阶段完成门槛：

- 6/6 Tool 可 discovery 和调用；
- Tool Contract 测试全部通过；
- MCP read-only 边界测试通过；
- Provider calls = 0；
- business-state writes = 0（Trace / telemetry 写入允许）；
- Pi 6 个 Tool 注册成功；
- 4/4 Slash Commands 可用；
- cancellation / unavailable / not-ready 路径有明确行为；
- 至少一条 Pi → MCP → JobLens Backend E2E 真实演示；
- README 包含安装、启动、架构图和 Demo；
- 不依赖手工复制数据库或修改源代码才能启动。

---

## 15. 简历与面试可声明边界

只有完成上述 Release Gate 后，才可以写：

> 实现 JobLens MCP Server，将 Job Search / Match / Ranking / Skill Gap / Preparation 等受治理能力暴露为标准 MCP Tools；开发 Pi Extension，通过自定义 Tool、Slash Command 和 Session 集成让 Coding Agent 直接调用 JobLens，并保持业务规则、权限与 Agent Runtime 解耦。

不能写：

- “Pi 原生支持 MCP”；
- “JobLens 已支持远程多租户 MCP”；
- “MCP 自动完成招聘网站采集”；
- “MCP Tool 会自动补齐 Match / Requirement”。

---

## 16. Grill-me 需求澄清结论

按照 `grill-me` 的 goal / behavior / input-output / scope / success / constraints / edge cases 维度压力检查后，冻结以下原本容易写模糊的决定：

1. **Pi Extension 到底调 REST 还是 MCP？** 第一阶段统一通过 MCP；不再同时维护一套 Pi→REST 业务适配。
2. **MCP Server 是否独立业务服务？** 不是。它是 Backend 的 Adapter / Transport Boundary，复用 Application Use Case。
3. **第一阶段用什么 Transport？** STDIO。本地先证明协议和集成；HTTP / Auth 以后单独设计。
4. **`get_match_report` 是否可以复用现有 POST？** 不可以。必须新增 read-only current MatchReport query，避免隐式 Provider 成本。
5. **`get_skill_gaps` 是否先写 UserFeedback？** 不需要。第一阶段使用 explicit `selected_job_ids` 的 manual transient cohort。
6. **Pi Slash Command 和 LLM Tool 是否二选一？** 不是。同一 MCP capability 同时支持 LLM Tool 和用户快捷 Command。
7. **Pi Session 能不能缓存 JobLens 事实？** 只能缓存 ID / selection；恢复时必须重查 current facts。
8. **第一阶段是否开放写操作？** 不开放。全部 Tool 保持零写入、零 Provider。
9. **MCP 的安全边界是什么？** 第一阶段是 local single-user stdio，不等价于公网安全模型。
10. **什么才算 Pi Integration 做完？** 不是能连上 MCP，而是 6 Tool + 4 Commands + Session + Cancel/Error + E2E Demo + Tests 全部成立。
11. **MCP 子进程由谁管理？** Pi Extension 每个 Session 建立一个长生命周期 STDIO Client / Server 子进程，并在 session end / reload 时清理，禁止“一次 Tool Call 启一次进程”。
12. **`get_skill_gaps` 为什么不让 Agent传 cohort_id？** 因为这是内部执行标识；外部契约只暴露用户真正关心的 selected Job IDs。
13. **Slash Command 无参数时能不能让 LLM 猜？** 不允许。`/job-rank` 可复用 last search，`/job-gap` 可复用 last ranking 但必须人工确认，`/job-prepare` 必须显式 Job ID。
14. **“零 DB 写入”与 Trace 是否冲突？** 指标冻结为 business-state writes = 0；Trace / metrics 属于运行态写入。

这些决策优先保证：MCP 不绕过 JobLens 事实底座，Pi 不成为第二套业务实现，外部 Agent 只能消费被明确批准的粗粒度能力。
