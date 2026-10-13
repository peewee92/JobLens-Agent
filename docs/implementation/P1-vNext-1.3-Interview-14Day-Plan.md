# JobLens vNext 1.3：面试可演示 MCP 接入（14 天执行计划）

- 状态：执行中
- 创建日期：2026-10-13
- 实施分支：`codex/vnext13-mcp-stdio`（从当前已验证开发分支创建）
- 当前基线：`agent-a/vnext12-execution-layer` / `74ae807`；Backend `1387 passed`；Web 测试、类型检查、生产构建通过。
- 本地未跟踪文件（保留，不覆盖）：`docs/implementation/P1-JobLens-MCP-Transport-Layer-Development-Plan.md`、`docs/interview-labs.md`。

## 目标

在本地、单用户、STDIO 边界内，将现有受治理、零 Provider 成本的三个只读 Workflow 通过官方 MCP Python SDK 暴露给标准 MCP Client：

1. `rank_match_reports`
2. `target_cohort_gaps`
3. `job_preparation`

这不是完整六工具 MCP 发布，也不包含 Pi Extension、远程 HTTP、认证、自动投递或 Provider 调用。

## 执行批次

### Batch A：基线与协议骨架

- [x] 保存本计划与恢复上下文。
- [x] 修复 Web 端到端冒烟测试中已过期的错误码断言。
- [x] 加入并锁定官方 `mcp>=2,<3` SDK（MCP 2.3.0）。
- [x] 建立 `app/mcp` 服务、外部输入/输出契约、STDIO 启动脚本。
- [x] 注册三个工具的说明、扁平输入 Schema 与只读 metadata。

### Batch B：受治理调用链

- [x] 建立不依赖 FastAPI `Depends` 的 MCP composition factory，复用 Context Builder、Registry 和成熟 Workflow。
- [x] 所有 MCP Tool 一律经过 `CareerAgentContextBuilder` 与 `CareerAgentToolRegistry.invoke()`。
- [x] 对外 Gap 输入只接受 `selected_job_ids` 与可选 `name`；服务器生成 transient `cohort_id`。
- [x] 使用公开 projection 转换返回值；不泄露 raw Resume、raw JD、source raw 或内部 canonical 字段。
- [x] 统一输出 `ok/data/error/meta`，明确请求标识、零 Provider 调用和零业务写入。

### Batch C：治理与协议验证

- [x] 进程内 SDK discovery 与 3/3 成功调用测试。
- [x] STDIO 子进程 discovery / call / restart 测试。
- [x] 未发布 career context、空岗位选择、准备岗位切换三种拒绝回归；底层 Workflow 调用必须为 0。
- [x] 临时 SQLite 合成演示数据种子与可复制的标准客户端演示命令；不提交个人数据、数据库或密钥。

### Batch D：作品化与验收

- [x] README 更新真实能力、测试数字、MCP 运行与演示步骤。
- [x] 在 README 增加传输架构图；在本文记录失败场景演示与 90 秒面试讲述。
- [x] Backend 全量测试、Web 测试/类型检查/构建、Web smoke、MCP SDK protocol E2E、`git diff --check` 已通过。

## 当前验证记录

- 2026-10-13：`services/backend/.venv/bin/python -m pytest -q`：`1387 passed in 99.46s`。
- 2026-10-13：`apps/web` 的 `pnpm test && pnpm typecheck && pnpm build`：通过。
- 2026-10-13：`pnpm smoke:e2e` 失败：脚本仍预期 `semantic_match_inputs_not_ready`，真实后端现返回 `eligibility_inputs_not_ready`。这是过期的验收断言，纳入 Batch A 修复。
- 2026-10-13：修正 smoke 断言；待完整 smoke 回归确认。
- 2026-10-13：`seed_mcp_demo.py` 创建临时 SQLite 合成数据后，三个真实 Adapter 调用均成功，且均为 `provider_calls=0 / business_writes=0`。
- 2026-10-13：Backend 全量回归：`1393 passed, 1 skipped`；Web：`170 passed`、typecheck、production build 通过；`pnpm smoke:e2e` 通过。
- 2026-10-13：修复 MCP SDK metadata 字段断言；进程内官方 Client 完成 discovery 与 3/3 成功调用验证。
- 2026-10-13：STDIO 子进程以合成 SQLite 数据库完成 discovery、三个工具调用、进程退出后重新连接与再次调用。每次返回均为 `providerCalls=0 / businessWrites=0`；Gap projection 不再返回仅供内部一次性使用的 `cohortId`。
- 2026-10-13：新增 protocol 测试后 Backend 全量回归：`1396 passed`；其中 MCP adapter / SDK protocol 小集：`9 passed`。
- 2026-10-13：按 README 的实际命令重新生成临时合成数据库并调用标准客户端，3/3 工具成功；返回均为零 Provider 调用、零业务写入，且 Gap 结果不含 `cohortId`。
- 2026-10-14：修复 MCP Adapter 在 Context Builder 抛出存储/内部异常时绕过统一错误 envelope 的缺陷。先用失败回归复现未捕获的 `OSError`，再将 Context Builder 调用纳入受控错误映射；三个工具的存储异常/未知异常均返回脱敏 `backend_unavailable`/`internal_error`，且不触发 Registry。官方 SDK Client 的失败响应回归通过；MCP 专项 `16 passed`，Backend 全量 `1403 passed`，compileall 与 `git diff --check` 通过。Web 验证未运行：当前 DevSpace 环境缺少 `pnpm` 命令；STDIO 真实子进程及重连由本轮协议测试覆盖。Provider calls=0，business writes=0。

## 下一动作

优先检查 MCP 对外三个响应的字段投影是否仍暴露不必要的内部标识或原始材料，并用最小协议回归确认；随后在具备 `pnpm` 的环境完成 Web/smoke 验证，再由其他机器按 README 命令验证干净环境 `uv sync` 与标准客户端复现。后续功能范围保持在计划外，不提前扩展为六工具或 Pi Extension。

## 阻塞项

- 本机 `uv sync` 下载 `cryptography` wheel 曾长时间未完成；锁文件已完整记录 MCP SDK 2.3.0 依赖，干净环境执行 `uv sync` 会安装锁定版本。当前本地已使用 SDK 完成协议验证。
- vNext 1.1 真实 Provider 质量门仍为独立人工/付费发布门；本阶段 Provider calls 固定为 0。

## 面试演示与讲述

### 失败场景（30 秒）

调用 `rank_match_reports` 前删除或不创建已确认的 Profile/SearchIntent。MCP 会返回 `context_not_released` envelope；Adapter 在 `CareerAgentContextBuilder` 后停止，Registry/Ranking Workflow 调用数为 0。这个案例说明 MCP annotations 只是提示，真正的执行边界仍在 JobLens 内部治理层。

### 90 秒讲述

“JobLens 不把简历和岗位描述直接扔给模型给分，而是先把用户确认的经历、岗位 Requirement 和 MatchReport 变成可追溯事实。现有 Web 和 Agent Runtime 已经有 Ranking、Skill Gap、Preparation 三个成熟只读 Workflow。我做 MCP 时没有把 REST 接口复制一遍，也没有让外部 Agent 直接访问数据库；我把 MCP 定义为一个 transport adapter。每个 Tool 都先走 Context Builder，再走受治理的 Tool Registry，最后才调用原有 Workflow。外部消费者只能传岗位 ID；例如 Gap 的 cohort ID 由服务端临时生成，避免泄露内部执行细节。返回值统一为结构化 envelope，并明确 Provider calls 和 business writes 都是零。我还加入了合成 SQLite 演示数据和拒绝回归：职业上下文未发布、空选择、或岗位上下文不一致时，底层工作流不会被调用。这样项目同时展示了协议集成、分层后端、可测试治理边界和全栈可复现演示。”
