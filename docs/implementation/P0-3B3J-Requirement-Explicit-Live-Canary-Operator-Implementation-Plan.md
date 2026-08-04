# P0-3B-3J｜Requirement Explicit Live Canary Operator 实施计划

状态：代码已实现，真实 Provider 执行等待正式数据进入 DevSpace 私有目录和真实凭据。

## 1. 当前真实功能

将已经存在的 Formal Dataset Preflight、Database Checkpoint、Readiness、Session Manifest、Resumable Preparation 和 Canary Human Gate 收束成一个唯一的显式副作用入口：

```text
canonical private 20-JD dataset
→ read-only Readiness
→ Operator Plan
→ explicit --execute-canary
→ explicit live-cost/human-review acknowledgement
→ pre-execution Session Manifest
→ at most 1-3 cumulative pre-review live attempts
→ Acceptance Run / Case / Extraction / Trace evidence
→ post-execution Session Manifest
→ human Workbench
```

命令只允许 `nextAction=run_canary`。它不能执行 Continue 后的 Resume，不能提交 Continue/Stop，也不能创建 Fixture 正式证据。

## 2. 本轮学习目标

本轮只学习当前切片需要的知识：

1. Readiness policy 与 side-effect command 的边界；
2. Plan Ready 与 Execution Authorized 的区别；
3. 双显式确认如何防止意外付费调用；
4. canonical private handoff 与内容寻址路径；
5. side effect 前后证据快照；
6. 用 Run Case `attemptCount` 增量识别本次新尝试；
7. Attempt、Provider 网络成功、Extraction 成功三者的区别；
8. 为什么 Human Gate 不能被 Operator 自动完成；
9. TOCTOU、符号链接逃逸和执行后 Manifest 失败；
10. 为什么 CLI 退出码不能代替数据库和 Trace 证据。

## 3. 业务风险和学习风险

### 3.1 业务风险：高

- Readiness 命令意外触发 Provider；
- 上传文件未经过私有 Staging 就直接执行；
- 第一次调用超过 3 条；
- 已到人工审核阶段仍继续调用；
- 只传 `--execute` 就发生付费；
- Provider 执行后没有 Run/Trace 证据；
- Manifest 写失败却显示完全成功；
- 1-2 条完成后自动补齐第 3 条；
- 自动提交 Continue 或 Stop；
- 把 `attemptCount` 当成网络请求一定到达 Provider；
- Session Manifest 通过后期符号链接逃逸到 Git 跟踪目录。

### 3.2 学习风险：高

- 只会调用 Use Case，不会设计副作用门禁；
- 把 Presence Check 当作 Runtime Authorization；
- 不理解为何 Plan 成功仍必须再次明确执行；
- 不会从 Before/After Run 推导本次证据；
- 把 Agent 的质量判断交给自动化；
- 把 `exit 0` 当作质量验收结论。

## 4. 核心机制责任边界

### 4.1 由学习者先写/解释

1. 为以下状态画真值表：
   - Provider allowed，但未请求执行；
   - 请求执行，但未确认成本与人工审核；
   - 已有 1-2 次 Attempt；
   - 已有 3 次 Attempt，等待人工审核；
   - 已 Continue；
   - 已 Stop；
2. 解释 `planReady` 和 `executionAuthorized`；
3. 解释为什么 `attemptDelta` 不是“网络请求成功次数”；
4. 解释为什么第三次 Attempt 后只能返回 Workbench；
5. 亲自审查 JD、Requirement、importance、evidenceSpan 和 Trace；
6. 亲自作出 Continue/Stop 判断。

### 4.2 可由开发 Agent 完成

- 纯 Operator Policy；
- canonical private path gate；
- 双确认 CLI；
- Readiness/Preparation 编排；
- 前后 Session Manifest；
- Run Case Attempt 增量证据；
- Trace 缺失门禁；
- 路径二次校验；
- 测试、ADR、CLI 契约、学习记录和 Demo。

## 5. 已确认事实、推断、假设和未知项

### 5.1 已确认事实

- 本地数据库已在 Alembic Head `20260804_0013`；
- 当前 Provider=`disabled`；
- 当前 Model 为空；
- 当前 API Key 未配置；
- DevSpace 私有目录中尚无 Formal Dataset；
- 会话附件中存在候选文件 `boss-job-filter-requirement-review-v1.4.5-2026-08-04T08-31-15-681Z(1).json`；
- 附件候选为 332,907 字节，文件 SHA-256 为 `cca99169dc7192734df1c2e3fcdcf6b052e6dd6392f850b7c9f8457402b23548`；
- 附件元数据显示 version=`1.4.5`、purpose=`requirement_manual_quality_review`、status=`ready`、selectedCount=20；
- 按项目 Fingerprint 算法得到 `b96c8048ead3bbb0e077206ceaca1068a3c527cec527e317ab63399441015d17`；
- canonical 私有路径因此应为 `data/private/requirement-acceptance/datasets/formal-b96c8048ead3bbb0.json`；
- 附件容器与 DevSpace 文件系统隔离，尚未完成项目内正式 Preflight。

### 5.2 推断

- 数据库已不再是 Live Canary 的 blocker；
- 下一次真实推进只需要完成文件私有交接和 Provider 配置；
- 一个唯一 Operator Command 比继续保留多段手工命令更不容易绕过门禁。

### 5.3 假设

- 当前仍是本地单用户 SQLite MVP；
- Operator 在受信任本地终端运行；
- API Key 通过环境配置，不写入 Manifest；
- 正式数据由 Guarded Bootstrap 复制到 canonical 私有路径；
- 真实 Provider 仍为 OpenAI Responses API Adapter。

### 5.4 未知项

- 最终选择的 OpenAI Model；
- API Key 是否有效、账户是否有配额；
- 真实调用的网络延迟、Token、限流和错误率；
- 20 条数据在 DevSpace 中运行完整 Preflight 的结果；
- 真实 Canary Requirement 质量；
- 人工 Continue/Stop 结论。

## 6. 四类完成标准

### 6.1 工程完成标准

1. 在读取 JSON 前先拒绝 private root 外的文件，并只接受 fingerprint-addressed canonical private dataset；
2. Plan 模式不能构造 Provider Runtime；
3. `--execute-canary` 与 `--confirm-live-cost-and-human-review` 缺一不可；
4. 预算必须是 1-3，并受累计 Canary Gate 约束；
5. 只允许 `nextAction=run_canary`；
6. Provider 副作用前必须成功写 Session Manifest；
7. 执行后必须读取同一 Run/Cohort；
8. 本次 Attempt 必须通过 Case attemptCount 增量证明；
9. 每个新增 Attempt 应有 Trace ID，否则返回 Attention Required；
10. Provider/Model/Run ID 不一致时 fail closed；Run 无法回读时将 Attempt 数标为未知并返回 Attention；
11. 执行后 Manifest 更新失败不能返回 Clean Completion；
12. 第三次 Attempt 后返回 Workbench，不能提交判断；
13. 数据文件执行前后 Hash/大小变化时返回 Attention Required；
14. 不能提供 Fixture 或 Controlled Resume 路径。

### 6.2 学习完成标准

学习者能独立解释：

- Readiness 与 Operator 的职责；
- 为什么双确认不是重复；
- 为什么 private handoff 使用 Dataset Fingerprint；
- 为什么 Attempt、Trace、Extraction 要分开；
- 如何计算本次新增证据；
- 为什么 1-2 次后仍需再次显式调用；
- 为什么第三次后必须停在人工作业；
- 为什么 Manifest 更新失败不等于 Provider 没执行。

### 6.3 作品集完成标准

可以展示：

- 一条受控 Live Canary Operator CLI；
- 双显式确认；
- Readiness 与副作用分层；
- canonical private handoff；
- 前后 Session Manifest；
- Run/Case/Extraction/Trace 证据增量；
- Human Gate 不可自动化；
- 故障注入和 Attention Outcome。

不能声明：

- 已完成真实 Provider Canary；
- 已批准模型质量；
- 已完成 20 条人工审核；
- 已进入 Match。

### 6.4 用户价值假设

> 将多个手工命令收束为一个显式 Operator Boundary，可以降低误调用、超预算、绕过人工门禁和证据丢失的概率，让真实模型质量判断更可复现。

该假设的软件边界已验证；真实价值仍需首次 Canary 运行验证。

## 7. 完成标准到证据的映射

| 完成标准 | 证据 |
|---|---|
| canonical private handoff | pre-read containment test + CLI blocker + path policy test |
| 双确认 | Runtime 未构造测试 |
| 1-3 预算 | Readiness/Operator policy tests |
| 只允许 run_canary | nextAction blocker test |
| 副作用前 Manifest | write-order CLI test |
| 本次 Attempt 数 | Run Case attemptCount delta |
| 成功 Extraction | Extraction ID |
| 调用过程证据 | Trace ID |
| 第三次后人工审核 | postReadiness + Workbench URL |
| 不自动判断 | source boundary test + output flag |
| Manifest 失败不伪装成功 | failure-injection test |
| 数据文件未变化 | before/after file SHA + byte count |
| Cohort 一致 | runtime invariant |
| Post Run 无法回读 | structured Attention output + unknown attempt count test |
| 无 Web Provider 按钮 | 既有 Web architecture tests |

## 8. 最小知识与预测

### 预测 1

`providerExecutionAllowed=true`，但没有 `--execute-canary`。

答案：只输出 Plan，不构造 Provider Runtime，不写 Acceptance Domain 数据。

### 预测 2

同时传入 `--execute-canary`，但没有确认成本与人工审核。

答案：可以写执行前 Manifest，但不构造 Provider Runtime，退出 2。

### 预测 3

已有 3 次 Attempt，传入全部执行标志。

答案：`nextAction=review_canary`，Operator 拒绝执行并返回 Workbench。

### 预测 4

成功完成 2 条。

答案：不会自动补第 3 条；Post Readiness 可生成下一条显式命令，仍需再次人工执行。

### 预测 5

Provider 已执行，但 Post Manifest 写盘失败。

答案：Run/Trace 仍是事实；CLI 返回 `completed_with_attention_required`，并区分执行前 Manifest 和执行后更新状态。

## 9. 常见错误实现和失败案例

```python
readiness = check_readiness()
if readiness.provider_execution_allowed:
    prepare_use_case.execute(payload)
```

错误原因：

- Readiness 变成隐式副作用入口；
- 没有 explicit execute；
- 没有成本/人工审核确认；
- 没有 canonical private handoff；
- 没有 pre-execution evidence；
- 没有本次 Attempt delta；
- 没有第三次后的 Human Stop；
- 容易被计划检查或 CI 意外触发。

失败案例：

```text
Run 已有 2 次 Attempt
→ 操作者请求 max=3
→ 错误实现再尝试 3 次
→ 累计达到 5 次
→ Human Canary Gate 被绕过
```

正确实现由 Readiness 计算 remaining budget，并由 Operator 只允许 `run_canary`。

## 10. 1-3 小时 Tickets

| Ticket | 内容 | 预计 | 状态 |
|---|---|---:|---|
| T0 | 风险、真值表和范围冻结 | 1h | 完成 |
| T1 | Pure Operator Policy | 1-2h | 完成 |
| T2 | canonical private handoff gate | 1h | 完成 |
| T3 | Plan/Execute 双确认 CLI | 2-3h | 完成 |
| T4 | pre/post Session Manifest | 1-2h | 完成 |
| T5 | Attempt/Extraction/Trace delta | 2h | 完成 |
| T6 | Human Workbench handoff | 1h | 完成 |
| T7 | TOCTOU/Cohort/Manifest failure tests | 2-3h | 完成 |
| T8 | ADR、契约、学习记录、Demo | 2h | 完成 |
| T9 | 正式文件 DevSpace 私有交接 | 1h | 外部阻塞 |
| T10 | 真实 1-3 Canary + 人工判断 | 1-3h | 外部阻塞 |

## 11. 明确不扩展范围

本轮不做：

- Controlled Resume；
- Continue/Stop 自动判断；
- 20 条完整运行；
- 自动人工 Review；
- 新数据库表；
- 新 HTTP Provider API；
- Web 中保存 API Key；
- Match、Ranking、Gap、Resume；
- Queue、Lease、Distributed Lock；
- Multi-Agent。

## 12. 尚未验证

- 正式文件在 DevSpace canonical path 的完整 Preflight；
- OpenAI Model 和 Key；
- 真实 Provider 网络请求；
- 真实 Token/Latency/Error；
- 真实 Run/Case/Extraction/Trace；
- Workbench 中的真实人工检查；
- Continue/Stop；
- 20 条人工结论；
- 模型质量批准。
