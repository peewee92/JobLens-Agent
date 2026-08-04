# ADR-0032｜Explicit Live Requirement Canary Operator

状态：Accepted
日期：2026-08-05

## Context

Requirement Acceptance 已具备 Formal Dataset Preflight、Readiness、Persistent Run、Canary Human Gate、Web Workbench、Session Manifest 和 Resumable Preparation，但真实执行仍可能由操作者手工拼接多个命令。

Readiness 是只读判断。如果它直接触发 Provider，计划检查、CI 或一次误操作就可能产生付费调用。另一方面，仅依赖 Preparation Use Case 内部 Canary Gate，仍不能证明操作者明确接受本次成本、确认后续需要亲自审核，也不能保证使用的是 canonical 私有数据文件。

## Decision

新增唯一的初始/部分 Canary Operator CLI：

```text
scripts.operate_requirement_acceptance_canary
```

它遵守以下决策：

1. **Readiness 与副作用分离**：Readiness 只返回允许状态；Operator 才能执行；
2. **canonical private handoff**：在解析 JSON 前先拒绝 private root 外文件；输入还必须等于由 Dataset Fingerprint 生成的 `data/private/.../formal-<fingerprint>.json`；
3. **双显式确认**：执行需要同时传入 `--execute-canary` 和 `--confirm-live-cost-and-human-review`；
4. **只允许 pre-review Canary**：仅接受 `nextAction=run_canary`，不执行 Resume；
5. **预算上限**：本命令只接受 1-3，并继续服从累计 Canary Gate；
6. **Manifest before side effect**：执行前必须成功写入 Session Manifest；
7. **数据库事实 after side effect**：执行后重新读取同一 Acceptance Run；
8. **证据增量**：通过 Case `attemptCount` Before/After 计算本次 Attempt，并关联 Extraction/Trace；
9. **Cohort invariant**：Preparation 的 Run ID、Provider 和 Model 必须与授权状态一致；若副作用后 Run 无法回读，则 Attempt 数保持未知并返回 Attention；
10. **Human decision remains manual**：达到 3 次后只返回 Workbench URL；
11. **fail closed on incomplete evidence**：Trace 缺失、文件变化或 Post Manifest 更新失败时返回 Attention Required；
12. **private path recheck**：Manifest 写入前再次 Resolve，防止晚发生的符号链接逃逸；
13. **no Fixture formal path**：Operator 不提供 `--allow-fixture`。

## Consequences

### Positive

- 计划检查不会意外调用 Provider；
- 付费调用有清晰的显式边界；
- 正式数据来源与私有路径可复现；
- 本次调用证据可以从持久化 Run/Case/Trace 推导；
- Human Gate 不能被 CLI 自动绕过；
- 1-2 次后不会自动补齐；
- Operator 输出能区分 Clean Completion 和 Attention Required。

### Negative

- 操作者需要输入较长的确认参数；
- 正式文件必须先经过 Bootstrap；
- CLI 仍是本地受信任运维入口，不解决团队 RBAC；
- 外部 Provider 是否真正收到请求不能仅由 attemptCount 证明，仍需 Trace；
- Provider 已执行而 Post Manifest 写失败时，需要依赖数据库/Trace 修复 Manifest。

## Rejected Alternatives

### 1. Readiness 自动调用 Provider

拒绝。Readiness 必须保持只读和可安全重复运行。

### 2. 直接继续使用 Preparation CLI

拒绝作为推荐 Live 入口。Preparation 保留底层编排能力，但缺少 canonical handoff、双确认和前后证据汇总。

### 3. 在 Web 增加“运行 20 条”按钮

拒绝。长 Provider 任务、凭据和付费副作用不应在当前浏览器边界中启动。

### 4. 第三次后自动 Continue

拒绝。Requirement 质量判断是本轮刻意保留给学习者和操作者的核心能力。

### 5. 自动执行 1-3 条直到上限

拒绝。每次 Invocation 的预算必须显式；成功 1-2 条后是否继续仍由操作者决定。
