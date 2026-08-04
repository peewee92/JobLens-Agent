# Requirement Acceptance Readiness Dashboard

状态：P0-3 operational visibility contract

## 1. Purpose

该能力让用户在浏览器中查看正式 Requirement Acceptance 当前卡在哪一步，同时保持所有真实副作用在既有 CLI Operator 边界内。

它只回答：

```text
现在是否具备继续条件？
唯一 nextAction 是什么？
阻塞属于工程准备、Provider 执行，还是人工审核？
```

它不会执行：

- 数据集 Bootstrap；
- SQLite backup / migration；
- Live Canary；
- Controlled Resume；
- Continue / Stop；
- 20 条 Case Review；
- Final Decision。

## 2. Web entry

```text
/evals/requirements/canary/readiness
```

Canary Run 列表页提供入口：

```text
/evals/requirements/canary
```

页面的参数表单使用 GET：

- `reviewer`：稳定 Run/review owner；
- `title`：稳定 Run title；留空且数据集有效时可由 `generatedAt` 推导；
- `maxNewExtractions`：只用于 Readiness 预算判断，范围 1–20，默认 1。

“重新检查只读状态”不会创建 Run 或调用 Provider。

## 3. Backend API

```http
GET /api/v1/requirement-acceptance-runs/readiness
```

Query：

```text
reviewer=<string, max 120>
title=<optional string, max 200>
max_new_extractions=<integer 1..20, default 1>
```

示例：

```http
GET /api/v1/requirement-acceptance-runs/readiness?reviewer=will&title=2026-08%20acceptance&max_new_extractions=1
```

## 4. Dataset discovery

Backend 只检查服务端 private root：

```text
<private-root>/datasets/formal-*.json
```

默认：

```text
<data/private>/requirement-acceptance
```

可通过服务端环境变量覆盖，用于隔离测试或部署：

```env
REQUIREMENT_ACCEPTANCE_PRIVATE_ROOT=/absolute/server-side/private/root
```

该值不能由浏览器 Query 设置。

### 4.1 States

| State | Meaning | nextAction effect |
|---|---|---|
| `missing` | 0 个 canonical candidate | `fix_blockers` |
| `selection_required` | 多于 1 个 candidate | `fix_blockers` |
| `invalid` | JSON、formal preflight 或 fingerprint 文件名失败 | `fix_blockers` |
| `ready` | 恰好 1 个有效 canonical dataset | 继续组合 DB/Provider/Run 状态 |

有效文件名必须等于：

```text
formal-<datasetFingerprint first 16 hex>.json
```

API 只返回 `datasetFileName`，不返回绝对路径。

## 5. Response

阻塞示例：

```json
{
  "datasetState": "missing",
  "datasetCandidateCount": 0,
  "datasetFileName": null,
  "datasetFingerprint": null,
  "sourceVersion": null,
  "selectedCount": 0,
  "provider": "disabled",
  "model": "",
  "apiKeyConfigured": false,
  "reviewer": "will",
  "title": "2026-08 acceptance",
  "requestedMaxNewExtractions": 1,
  "databaseReachable": true,
  "databaseRevision": "20260804_0013",
  "migrationHead": "20260805_0015",
  "workflowReady": false,
  "providerExecutionAllowed": false,
  "readyForNextAction": false,
  "nextAction": "fix_blockers",
  "runId": null,
  "runStatus": null,
  "attemptedCalls": 0,
  "canaryDecision": null,
  "batchId": null,
  "workbenchUrl": null,
  "manualReviewUrl": null,
  "blockers": [
    {
      "scope": "workflow",
      "code": "formal_dataset_missing",
      "message": "..."
    }
  ],
  "dbWrites": 0,
  "providerCalls": 0
}
```

响应不会包含：

```text
API Key value
absolute dataset path
private root
full JD
raw Trace
recommended command
execute flags
```

## 6. nextAction

| nextAction | Meaning | Responsible boundary |
|---|---|---|
| `fix_blockers` | 数据集、数据库、Provider、Reviewer 或 Title 尚未就绪 | 人工/运维修复参数 |
| `run_canary` | 初始或剩余 Canary 可运行 | Explicit Live Canary CLI |
| `review_canary` | 已达到人工判断边界 | Canary Web Workbench + human decision |
| `resume_run` | Continue 已冻结，可补齐剩余 Case | Controlled Resume CLI |
| `open_manual_review` | 20 条 Extraction 已形成 frozen Batch | Manual Review Web |
| `stopped` | 人工 Stop 已冻结 | 不继续该 Run |

即使 `providerExecutionAllowed=true`，Web 也不会出现执行 Provider 的按钮。

## 7. Blocker scopes

### `workflow`

阻止建立稳定执行身份或读取正确状态，例如：

- `formal_dataset_missing`；
- `formal_dataset_selection_required`；
- `formal_dataset_invalid`；
- `database_unreachable`；
- `database_migration_not_current`；
- `live_provider_not_configured`；
- `live_model_not_configured`；
- `reviewer_missing`；
- `title_missing`。

### `provider_execution`

Workflow 已可定位，但真实调用仍不允许，例如：

- `openai_api_key_missing`；
- `max_new_extractions_missing`；
- `max_new_extractions_out_of_range`；
- `initial_canary_limit_exceeded`；
- `remaining_canary_limit_exceeded`。

## 8. Database safety

SQLite revision 使用 read-only URI：

```text
file:<database>?mode=ro
```

约束：

- 缺失数据库不能被自动创建；
- Readiness 前后数据库文件字节保持不变；
- 数据库未到 Alembic Head 时，不查询 Acceptance Run 表；
- API 本身不执行 migration。

`dbWrites=0` 表示本次 Readiness 请求不写业务数据。它不是数据库驱动层统计器，也不表示历史 Run 从未写入。

## 9. Provider safety

- 只返回 `apiKeyConfigured: boolean`；
- 不读取或渲染密钥值；
- 不构建 LLM Adapter；
- 不创建 Extraction 或 Trace；
- 不提供 execute command；
- `providerCalls=0` 固定描述本次只读请求。

## 10. Verification

Backend targeted：

```bash
cd services/backend
.venv/bin/python -m compileall -q app scripts tests
.venv/bin/pytest -q \
  tests/test_requirement_acceptance_readiness.py \
  tests/test_requirement_acceptance_readiness_dashboard.py \
  tests/test_requirement_acceptance_readiness_api.py \
  tests/test_requirement_acceptance_readiness_architecture.py
```

Web：

```bash
cd apps/web
./node_modules/.bin/tsx --test tests/*.test.ts
./node_modules/.bin/tsc --noEmit
env -u NODE_OPTIONS ./node_modules/.bin/next build
```

Cross-process Smoke：

```bash
cd apps/web
node scripts/requirement-readiness-smoke.mjs
```

Smoke 创建隔离 SQLite 并迁移到 Head，使用空 private root 和 disabled Provider，启动真实 FastAPI 与 production Next，验证：

```text
formal_dataset_missing
+ live_provider_not_configured
+ live_model_not_configured
→ nextAction=fix_blockers
→ dbWrites=0
→ providerCalls=0
→ Extraction/Trace/Acceptance Run counts unchanged
```

## 11. Current operational boundary

Dashboard 完成只代表 Human Gate 可见性完成。开始真实验收仍需要：

1. 人工提供正式 20-JD JSON；
2. Guarded Bootstrap；
3. 数据库备份和显式迁移授权；
4. 本地配置 OpenAI Provider、模型与 API Key；
5. 显式 Live Canary 双确认；
6. 人工 Continue/Stop；
7. Controlled Resume；
8. 20 条人工 Review；
9. Final Decision。

没有这些真实证据时，项目仍不能进入 Match。
