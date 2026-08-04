# ADR-0028｜Requirement Live Acceptance Readiness Gate

- Status: Accepted
- Date: 2026-08-04
- Scope: Requirement Acceptance live operation

## Context

JobLens 已具备：

- formal 20-JD dataset Preflight；
- resumable Requirement Extraction；
- persistent Run/Case；
- 1–3 次 live Canary 限额；
- immutable human Continue/Stop；
- Canary Review Web Workbench；
- 20-case Manual Review Batch。

但实际开始 live run 前，操作者仍需要手工检查：

- dataset 是否真的是 formal 20-JD；
- Provider 是否为 live OpenAI；
- Model、API Key 是否存在；
- SQLite 是否存在且 Alembic revision 为 head；
- 同一 dataset/title/reviewer/cohort 是否已有 Run；
- 下一步属于 Provider、Human Review、Resume、Manual Review 或 Stop。

只检查环境变量不足以决定是否安全调用。一个 Run 可能已经累计 3 次并等待人工判断，也可能已 Stop，或已生成 Batch。

## Decision

增加独立只读命令：

```bash
python -m scripts.check_requirement_acceptance_readiness ...
```

该命令：

1. 复用 formal dataset Preflight；
2. 动态读取 Alembic head；
3. 以 read-only SQLite 连接读取当前 revision；
4. 读取环境配置，但只暴露 `apiKeyConfigured: boolean`；
5. 根据 dataset fingerprint、title、reviewer、provider/model/extractor/prompt 查询 Existing Run；
6. 输出机器可消费 blocker code；
7. 输出唯一 `nextAction`；
8. 仅在 Provider execution 真正允许时输出不含密钥的 command preview；
9. 固定声明 `dbWrites=0`、`providerCalls=0`。

## Result model

核心字段：

```text
workflowReady
providerExecutionAllowed
readyForNextAction
nextAction
blockers[]
runId
attemptedCalls
canaryDecision
workbenchUrl
manualReviewUrl
recommendedCommand
```

`nextAction`：

```text
fix_blockers
run_canary
review_canary
resume_run
open_manual_review
stopped
```

## Why three readiness booleans

### `workflowReady`

表示数据、配置身份和数据库结构可以被系统正确理解。

### `providerExecutionAllowed`

表示此刻允许发生新的付费模型调用。

### `readyForNextAction`

表示下一步是否已经明确且可以执行。人工 Review 或打开 Manual Batch 时，它可以为 true，而 Provider permission 为 false。

这样避免把所有状态压缩为一个含义模糊的 `ready`。

## Blocker scopes

### `workflow`

例如：

- 数据库不可达；
- migration 不在 head；
- live Provider/Model 未配置；
- reviewer/title 缺失。

### `provider_execution`

例如：

- API Key 缺失；
- max limit 缺失或越界；
- 超过剩余未审核 Canary budget。

## Database check

对于本地 SQLite，缺失文件时普通连接可能创建空数据库。Readiness 使用只读 URI：

```text
file:<absolute-path>?mode=ro
```

如果文件不存在，返回 blocker，不创建文件。

Alembic head 从 migration graph 动态获取，不硬编码 revision ID。

## Existing Run semantics

| Run fact | nextAction | Provider allowed |
|---|---|---|
| 无 Run | run_canary | 额度 1–3 且配置完整时是 |
| 1–2 attempts，无 Review | run_canary | 不超过剩余额度时是 |
| 3 attempts，无 Review | review_canary | 否 |
| Continue | resume_run | 显式额度与 Key 完整时是 |
| Stop | stopped | 否 |
| Batch attached | open_manual_review | 否 |

## Security and privacy

- 不输出 API Key；
- 不输出 Provider request body；
- 不执行网络健康探测；
- 不复制 JD 内容；
- command preview 不包含 secret；
- 数据库检查只读；
- Readiness 不创建 Run、Import、Trace 或 Extraction。

## Alternatives rejected

### 仅扩展 `--preflight`

拒绝。Preflight 是数据契约，Readiness 是运行状态投影。混合后会使“数据有效”和“允许调用”含义不清。

### 只检查 API Key 和 Model

拒绝。无法识别 migration、Existing Run、Human Gate、Stop 和 Batch。

### 启动时自动修 migration

拒绝。Readiness 应报告事实，而不是悄悄修改数据库。

### 自动执行推荐命令

拒绝。Readiness 必须保持零调用；付费行为仍需要显式命令。

### 调用 Provider 做 health check

拒绝。会引入网络、费用和 Trace 语义，超出本切片。

## Consequences

### Positive

- live 操作前有统一、可复现的证据；
- 人工动作与机器动作明确分离；
- CI/脚本可依赖稳定 blocker code；
- 减少错误 migration、重复调用和绕过门禁；
- 缺失 SQLite 不会被检查动作创建；
- 不泄露凭据。

### Negative

- 多一个 CLI 和 contract；
- 仍依赖操作者提供数据集绝对路径；
- 不验证 OpenAI 网络可达性；
- 非 SQLite 数据库只能做到无显式写入，不能提供 SQLite `mode=ro` 同等级保证；
- 不能替代真实 Trace 与人工质量结论。

## Revisit when

- Provider execution 迁移到队列；
- 引入多个正式 Provider；
- Readiness 需要进入 Web/CI；
- 引入 authentication、RBAC 和 cost owner；
- 多进程需要原子 lease/claim；
- 非 SQLite 成为主要运行数据库。
