# Requirement Acceptance Live Canary Operator CLI

状态：P0-3B-3J operational contract

## 1. Goal

为正式 Requirement Extraction 提供唯一推荐的初始/部分 Live Canary 副作用入口。

它组合：

- Formal Dataset Preflight；
- canonical private handoff；
- Live Readiness；
- explicit budget；
- explicit cost/human-review acknowledgement；
- stable-identity database execution lease；
- Resumable Preparation；
- Session Manifest；
- Run/Case/Extraction/Trace evidence；
- Human Workbench handoff。

它不执行 Continue/Stop，不执行 Controlled Resume，不自动跑满 20 条。

## 2. Required private handoff

正式数据必须先由 Guarded Bootstrap 写入。Operator 会在解析 JSON 前先拒绝 private root 外文件：

```text
data/private/requirement-acceptance/datasets/
formal-<datasetFingerprint first 16 hex>.json
```

当前附件候选预期为：

```text
data/private/requirement-acceptance/datasets/
formal-b96c8048ead3bbb0.json
```

Operator 会重新运行完整项目 Preflight，并检查实际路径是否等于 Fingerprint 推导路径。

## 3. Plan command

```bash
cd services/backend

.venv/bin/python -m scripts.operate_requirement_acceptance_canary \
  ../../data/private/requirement-acceptance/datasets/formal-b96c8048ead3bbb0.json \
  --reviewer will \
  --title "2026-08 real Requirement acceptance" \
  --max-new-extractions 1 \
  --json
```

Plan 模式：

```text
Provider Runtime build = 0
Provider attempts = 0
Acceptance domain writes = 0
```

## 4. Explicit execute command

```bash
.venv/bin/python -m scripts.operate_requirement_acceptance_canary \
  ../../data/private/requirement-acceptance/datasets/formal-b96c8048ead3bbb0.json \
  --reviewer will \
  --title "2026-08 real Requirement acceptance" \
  --max-new-extractions 1 \
  --execute-canary \
  --confirm-live-cost-and-human-review \
  --json
```

执行模式必须同时满足：

```text
canonical private dataset
AND Formal Preflight passed
AND DB revision == Alembic head
AND Provider == openai
AND Model configured
AND API Key configured
AND nextAction == run_canary
AND providerExecutionAllowed == true
AND maxNewExtractions in 1..3
AND --execute-canary
AND --confirm-live-cost-and-human-review
AND stable execution identity has no active lease owner
```

## 5. Arguments

```text
dataset                                   canonical private formal JSON
--reviewer <text>                         immutable Run/review owner
--title <text>                            stable Run identity
--max-new-extractions <1-3>               this invocation's upper attempt budget
--web-base-url <url>                      used to build Workbench URL
--private-root <path>                     must remain under data/private
--session-manifest <path>                 optional private override
--execute-canary                          request Provider side effect
--confirm-live-cost-and-human-review      acknowledge cost and manual duty
--json                                    machine-readable output
```

## 6. Output contract

### 6.1 Operator

```json
{
  "operator": {
    "state": "ready_for_explicit_execution",
    "planReady": true,
    "executionAuthorized": false,
    "executeRequested": false,
    "liveCostConfirmed": false,
    "datasetPath": ".../formal-....json",
    "expectedDatasetPath": ".../formal-....json",
    "sessionManifestPath": ".../session.json",
    "requestedMaxNewExtractions": 1,
    "attemptedCallsBefore": 0,
    "blockers": []
  }
}
```

States：

```text
blocked
ready_for_explicit_execution
authorized
```

### 6.2 Dataset file evidence

```json
{
  "datasetFileSha256": "sha256-hex",
  "datasetByteCount": 332907,
  "datasetFileChangedDuringExecution": false,
  "datasetFileSha256AfterExecution": "sha256-hex",
  "datasetByteCountAfterExecution": 332907
}
```

`Dataset Fingerprint` 标识业务 cohort；`File SHA-256` 标识完整文件字节，两者不能互相替代。

### 6.3 Execution evidence

```json
{
  "executionOutcome": "completed",
  "liveExtractionAttemptsObserved": 1,
  "newAttemptEvidence": [
    {
      "caseId": "case_...",
      "caseIndex": 0,
      "jobId": "job_...",
      "status": "extracted",
      "attemptDelta": 1,
      "extractionId": "extraction_...",
      "traceRunId": "trace_...",
      "errorCode": null
    }
  ],
  "missingTraceCaseIds": [],
  "attemptBudgetExceeded": false,
  "automaticCanaryDecisionSubmitted": false
}
```

`liveExtractionAttemptsObserved` 是持久化 Attempt 增量，不声明 Provider 网络一定成功。网络和模型结果必须结合 Trace、Case status 和 Extraction ID 判断。

### 6.4 Manifest state

```json
{
  "sessionManifestWrittenBeforeExecution": true,
  "sessionManifestUpdatedAfterExecution": true,
  "sessionManifestPath": ".../reqacceptsession_....json"
}
```

如果执行后更新失败：

```text
executionOutcome = completed_with_attention_required
sessionManifestWrittenBeforeExecution = true
sessionManifestUpdatedAfterExecution = false
postExecutionManifestError = <type>
```

Provider/DB 事实不会因为 Manifest 失败而被当成未执行。

### 6.5 Human handoff

第三次累计 Attempt 后：

```json
{
  "postReadiness": {
    "nextAction": "review_canary",
    "recommendedCommand": null,
    "workbenchUrl": "http://localhost:3000/evals/requirements/canary/run_..."
  },
  "manualHumanDecisionRequired": true,
  "automaticCanaryDecisionSubmitted": false
}
```

## 7. Exit codes

```text
0  Plan ready, or clean execution completed
1  Plan blocked for fixable environment state, or execution needs attention
2  Invalid/rejected command, missing explicit confirmation, unsafe path,
   pre-execution Manifest failure, or application gate rejection
```

Exit 0 不能证明模型质量通过。

## 8. Evidence hierarchy

按可信程度使用：

```text
Database Acceptance Run / Case
→ Trace
→ Extraction
→ Session Manifest
→ CLI JSON
→ terminal text
```

CLI 不取代数据库和 Trace。

## 9. Failure behavior

### Outside-private or non-canonical path

private root 外文件在 JSON 读取前直接拒绝；私有目录内但文件名与 Fingerprint 不匹配时在 Preflight 后拒绝。两者都不写 Session Manifest、不构造 Provider Runtime。

### Missing confirmation

可写执行前 Manifest，但不构造 Provider Runtime。

### Attempt without Trace

保留 Run Case，返回 Attention Required。

### Concurrent execution lease conflict

同一 Dataset/Title/Reviewer/Provider/Model/Extractor/Prompt 身份已有活动执行者时：

```text
executionOutcome = execution_rejected
executionError.type = RequirementAcceptanceExecutionLeaseUnavailableError
Provider attempts = 0
new Trace = 0
new import = 0
```

租约默认 30 分钟，并在每次新 Provider 调用前由当前 owner token 原子续租。续租时发现租约已过期或已被接管，会在该次 Provider 调用前返回 `RequirementAcceptanceExecutionLeaseLostError`。进程异常退出后，过期租约可由后续显式执行原子接管；旧 owner token 不能续租或释放新租约。

### Observed Attempt delta exceeds explicit budget

保留真实 Run/Trace，标记 `attemptBudgetExceeded=true` 并返回 Attention Required；这可能表示运行边界异常，不能静默归入本次成果。

### Dataset file changed during execution

保留真实 Run/Trace，返回 Attention Required。

### Post Run cannot be read

Preparation 结果仍保留，`liveExtractionAttemptsObserved=null`，返回 Attention Required；不能把无法回读误报为 0 次 Attempt。

### Post Manifest failure

保留真实 Run/Trace，返回 Attention Required。

### Three cumulative Attempts

返回 Workbench，不调用 Provider，不自动 Continue/Stop。

### Existing Continue

`nextAction=resume_run` 时本命令拒绝。使用 [`REQUIREMENT-ACCEPTANCE-CONTROLLED-RESUME.md`](REQUIREMENT-ACCEPTANCE-CONTROLLED-RESUME.md) 中的专用 Resume Operator，并显式绑定 Run ID 与不可变 Canary Review ID。

## 10. Privacy

CLI 和 Manifest 不输出：

- API Key；
- Authorization Header；
- 完整 JD；
- Raw Trace Output；
- 人工 Review Notes 正文。

CLI 会输出私有本地路径，公开作品集前必须脱敏。

## 11. Current environment

截至 2026-08-05：

```text
Database revision = 20260804_0013
Alembic head = 20260805_0014
Provider = disabled
Model = blank
API Key configured = false
Canonical private formal dataset = absent
```

因此当前不能执行真实 Provider Canary。
