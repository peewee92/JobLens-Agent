# P0-3B-3F｜Requirement Live Acceptance Readiness Gate 实施计划

状态：已实现并验证（2026-08-04）

## 1. 当前真实项目功能

本切片实现：

> 在发生任何真实 Provider 调用前，用一个零写入、零调用的 Readiness Gate，验证正式 20-JD 数据集、live Provider 配置、模型、API Key 是否存在、Alembic revision、Run 身份和当前人工门禁状态，并明确给出唯一下一动作。

命令：

```bash
cd services/backend
.venv/bin/python -m scripts.check_requirement_acceptance_readiness \
  /absolute/path/to/formal-review.json \
  --reviewer will \
  --title "2026-08-04 real Requirement acceptance" \
  --max-new-extractions 3 \
  --json
```

可能的 `nextAction`：

```text
fix_blockers
run_canary
review_canary
resume_run
open_manual_review
stopped
```

Readiness 不执行 Import、不创建 Run、不调用模型，也不打印 API Key。

## 2. 本次学习目标

本切片需要掌握：

- Preflight 与 Operational Readiness 的区别；
- workflow readiness 与 provider execution permission 的区别；
- 为什么“配置存在”不等于“可以调用”；
- 为什么状态机必须读取持久化 Run，而不能只看环境变量；
- 如何用只读方式检查 SQLite migration；
- 如何设计机器可消费的 blocker code；
- exit code、JSON contract 和人工下一动作之间的关系；
- 为什么 Readiness 证据不能证明模型质量。

## 3. 风险判断

### 3.1 业务风险：高

没有 Readiness Gate 时，操作者可能：

- 使用 blocked 或非 20 条数据集；
- 在旧 migration 上执行新代码；
- 使用 disabled/fixture Provider 冒充 live；
- 忘记模型或 API Key；
- 对已经 Stop 的 Run 再次尝试；
- 在等待 Canary Review 时继续请求第 4 次调用；
- 已存在 Batch 时仍重复调用；
- 将环境检查成功误认为模型质量成功。

### 3.2 学习风险：中高

Agent 最容易替学习者跳过的是：

- 不区分“下一步是人工动作还是机器动作”；
- 只检查 API Key 是否存在；
- 看见绿色 `ready=true` 就认为模型通过；
- 不解释 blocker 与状态机的关系；
- 不理解为什么数据库 revision 属于调用前条件。

## 4. 哪些机制由学习者先完成

学习者应先手写以下真值表：

| Run 状态 | API Key | 请求额度 | 下一动作 | 是否允许 Provider 调用 |
|---|---|---:|---|---|
| 不存在 | 有 | 3 | ? | ? |
| 不存在 | 有 | 4 | ? | ? |
| 2 attempts，无 Review | 有 | 1 | ? | ? |
| 2 attempts，无 Review | 有 | 2 | ? | ? |
| 3 attempts，无 Review | 无 | 17 | ? | ? |
| Continue | 有 | 17 | ? | ? |
| Stop | 有 | 1 | ? | ? |
| Batch ready | 无 | 1 | ? | ? |

学习者还需要自己解释：

- 为什么等待人工 Review 时不需要 API Key；
- 为什么 Stop 不是“缺少配置”；
- 为什么 Batch ready 时不再需要 Provider permission；
- 为什么 migration mismatch 是 workflow blocker。

## 5. Agent 可以完成的外围工作

- 结构化结果与 blocker dataclass；
- Alembic head 读取；
- SQLite read-only revision 检查；
- Existing Run 查询；
- CLI 参数、JSON 与文本输出；
- 不含密钥的 command preview；
- 单元测试、CLI 测试；
- ADR、学习记录、Demo runbook；
- 独立 Diff 审查。

## 6. 事实、推断、假设和未知项

### 已确认事实

- 20-JD formal preflight 已存在；
- live Canary 累计上限和人工 Continue/Stop 已存在；
- Run、Case、Trace、Extraction 和 Batch 已持久化；
- Web Canary Workbench 已存在；
- 当前 DevSpace 进程没有 Provider、模型和 API Key；
- 当前本地 SQLite 可读，但 revision 为 `20260803_0010`，代码 Alembic head 为 `20260804_0013`；
- 上传文件的 `/mnt/data` 路径在 DevSpace 主机不可见；
- 尚未执行真实 OpenAI Canary。

### 推断

- 实际 live 运行前应有统一的机器可验证入口；
- Readiness 必须同时读取静态配置和动态 Run 状态；
- 下一动作不能统一表达成 `ready/not ready`；
- 数据库 migration 不匹配时，不应尝试读取新表或调用模型。

### 假设

- 当前仍使用本地 SQLite；
- 操作者从 `services/backend` 运行 CLI；
- OpenAI 是当前唯一正式 live Provider；
- Web 默认地址为 `http://localhost:3000`；
- 一个 dataset/title/reviewer/cohort 对应同一个 Run 身份。

### 未知项

- 用户最终使用的模型；
- API Key 和 base URL；
- 正式数据集在 DevSpace 主机上的绝对路径；
- 真实费用、延迟和限流；
- 是否需要将 Readiness 放入 CI 或 Web；
- 真实人工审核结论。

## 7. 四类完成标准

### 7.1 工程完成标准

- formal dataset 仍由现有 Preflight 校验；
- Readiness 不创建缺失 SQLite 文件；
- migration revision 与动态 Alembic head 对比；
- 不输出 API Key，只输出 `apiKeyConfigured`；
- 读取 Existing Run 后给出唯一 `nextAction`；
- Provider 调用权限与 Workflow 下一动作分离；
- JSON 输出含稳定 blocker code；
- 仅在执行允许时输出无密钥 command preview；
- 所有路径均声明 `dbWrites=0/providerCalls=0`。

### 7.2 学习完成标准

学习者能够不看代码解释：

- Preflight、Readiness、Canary、Review、Batch 的边界；
- `workflowReady` 与 `providerExecutionAllowed`；
- 六种 `nextAction`；
- 为什么人工动作可以 ready，但 Provider permission 为 false；
- 为什么 Readiness 不能作为模型质量证据。

### 7.3 作品集完成标准

Demo 能展示：

1. 环境缺失时输出 blocker codes；
2. 新 Run 额度 4 被拒绝、额度 3 可执行；
3. 3 attempts 后下一动作变成 Web Review；
4. Continue 后下一动作变成 Resume；
5. Stop 后不再给执行命令；
6. Batch ready 后给出 Manual Review URL；
7. 全过程没有输出密钥或调用模型。

### 7.4 用户价值假设

> 在真实模型调用前明确“缺什么、下一步做什么、是否允许花费”，可以减少错误配置、重复调用、绕过人工门禁和无效调试，使一次 live 质量验收可复现、可审计。

该假设尚未通过真实 Provider 操作验证。

## 8. 最小知识

### 8.1 Preflight 只回答数据是否合格

```text
20 条？
正式 purpose？
哈希一致？
无近重复？
```

它不回答：

```text
数据库是否升级？
Provider 是否配置？
是否等待人工判断？
该 Run 是否已 Stop？
```

### 8.2 Readiness 是状态机投影

Readiness 不创建新的业务事实。它把以下事实组合成下一动作：

```text
Dataset fingerprint
+ runtime config
+ database revision
+ existing Run
+ Canary Review
+ Batch
+ requested budget
```

### 8.3 Workflow ready 不等于 Provider allowed

例如 3 attempts 后：

```text
workflowReady = true
providerExecutionAllowed = false
readyForNextAction = true
nextAction = review_canary
```

系统没有故障，只是下一步属于人。

### 8.4 只读 SQLite 检查

缺失 SQLite 文件时，普通连接可能创建空文件。Readiness 使用：

```text
file:<path>?mode=ro
```

因此检查不会改变工作目录或伪造一个“数据库存在”的事实。

## 9. 先预测

1. 数据集合法但数据库不存在，`workflowReady` 是什么？
2. 3 attempts、无 Review、API Key 缺失，下一步是什么？
3. Continue 后 API Key 缺失，下一步和 permission 各是什么？
4. Stop 后所有配置齐全，为什么仍不能调用？
5. Batch ready 后为什么 `providerExecutionAllowed=false` 不是失败？
6. 为什么不能把 API Key 值写入 JSON？
7. 为什么 Readiness 不能运行 Import？
8. 为什么 migration head 要动态读取，而不是硬编码 `0013`？

## 10. 常见错误实现

```python
ready = bool(api_key and model and dataset_is_valid)
if ready:
    run_provider()
```

失败原因：

- 不读数据库 revision；
- 不读已有 Run；
- 无法识别 awaiting review、Stop 和 Batch ready；
- 不检查累计 Canary budget；
- `ready` 同时混合机器与人工动作；
- 很容易绕过后端门禁。

### 失败案例

Run 已累计 3 次调用，正在等待人工判断。环境中 Key、Model、Dataset 全部存在。错误实现返回 `ready=true` 并再次调用。正确 Readiness 返回：

```json
{
  "workflowReady": true,
  "providerExecutionAllowed": false,
  "readyForNextAction": true,
  "nextAction": "review_canary",
  "workbenchUrl": "..."
}
```

## 11. Ticket 拆分

| Ticket | 时间 | 内容 | 证据 |
|---|---:|---|---|
| T0 | 1h | 风险、真值表、范围冻结 | 实施计划 |
| T1 | 1–2h | Readiness result/blocker/next-action policy | 纯单元测试 |
| T2 | 1–2h | 只读 DB revision 与 Alembic head | SQLite 不创建文件测试 |
| T3 | 1–2h | Existing Run 状态投影 | 状态机测试 |
| T4 | 1–2h | CLI JSON/text/exit code | CLI 输出测试 |
| T5 | 1h | 无密钥 command preview | secret-redaction 测试 |
| T6 | 1–2h | 文档、ADR、学习记录、Demo | 文档 Diff |
| T7 | 1–2h | 全仓库回归和独立 Diff 审查 | test/build/diff |
| T8 | 人工 | 配置真实 Key 和数据路径，执行 Canary | 真实 Trace/DB/UI |

## 12. 完成标准与证据映射

| 完成标准 | 证据 |
|---|---|
| 新 Run 只能请求 1–3 条 | policy test |
| 2 attempts 只能再请求 1 条 | policy test |
| 3 attempts 指向 Web Review | policy test + URL |
| Continue 指向 Resume | policy test |
| Stop 不允许继续 | policy test |
| Batch 指向 Manual Review | policy test + URL |
| Missing Key 不泄露值 | CLI JSON test |
| Missing SQLite 不创建文件 | filesystem assertion |
| Migration mismatch 阻止 workflow | revision test |
| Readiness 零调用零写入 | JSON fields + implementation boundary |
| 不影响已有系统 | full Backend/Web/Collector regression |

## 13. 范围排除

- 不保存 API Key；
- 不探测 Provider 网络健康；
- 不执行真实模型调用；
- 不自动提交 Continue/Stop；
- 不启动 Backend/Web；
- 不上传数据集；
- 不实现队列、租约或并发 claim；
- 不进入 Match。

## 14. 本轮沉淀物

- `tests/test_requirement_acceptance_readiness.py`；
- ADR-0028；
- 本实施计划；
- P0-3B-3F 学习记录；
- Readiness CLI 契约；
- Demo runbook。
