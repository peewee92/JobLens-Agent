# Requirement Acceptance Controlled Resume Operator

Status: P0-3B-3K operational contract

## 1. Goal

After an immutable Canary `continue` decision, resume the same formal Requirement Acceptance Run without relying on shell history or operator memory.

The command binds one invocation to:

```text
Dataset Fingerprint
+ Run ID
+ Canary Review ID
+ Reviewer / Title
+ Provider / Model / Extractor / Prompt cohort
+ explicit new-extraction budget
```

It does not create or modify the human Continue decision. It does not automatically run all remaining Cases.

## 2. Preconditions

Before using this command:

1. the formal dataset has been staged by Guarded Bootstrap under `data/private`;
2. the database is at current Alembic head;
3. the live Provider, Model and API Key are configured;
4. the initial 1–3 Canary attempts have persisted Run Case, Extraction and Trace evidence;
5. the owner has submitted an immutable Canary `continue` decision;
6. Readiness returns `nextAction=resume_run`.

A `stop` decision, missing decision or pending Canary review cannot be resumed.

## 3. Read-only Plan command

```bash
cd services/backend

.venv/bin/python -m scripts.operate_requirement_acceptance_resume \
  ../../data/private/requirement-acceptance/datasets/formal-<fingerprint16>.json \
  --reviewer will \
  --title "2026-08 real Requirement acceptance" \
  --max-new-extractions 5 \
  --expected-run-id reqacceptrun_<id> \
  --expected-canary-review-id reqacceptcanary_<id> \
  --json
```

Plan mode guarantees:

```text
Provider Runtime build = 0
Provider attempts = 0
new Acceptance writes = 0
```

It may read the database and dataset to verify identity and evidence.

## 4. Explicit Execute command

After reviewing the Plan output:

```bash
.venv/bin/python -m scripts.operate_requirement_acceptance_resume \
  ../../data/private/requirement-acceptance/datasets/formal-<fingerprint16>.json \
  --reviewer will \
  --title "2026-08 real Requirement acceptance" \
  --max-new-extractions 5 \
  --expected-run-id reqacceptrun_<id> \
  --expected-canary-review-id reqacceptcanary_<id> \
  --execute-resume \
  --confirm-reviewed-canary-and-live-cost \
  --json
```

The two execute flags are intentionally separate from Plan mode.

## 5. Safety checks

The Operator rejects execution unless all checks pass.

### 5.1 Private dataset identity

The dataset must be exactly:

```text
<private-root>/datasets/formal-<datasetFingerprint first 16>.json
```

A file outside the private root is rejected before JSON parsing. A private file with the wrong fingerprint-derived path is rejected after Preflight.

### 5.2 Run identity

The persisted Run must match Readiness on:

- dataset fingerprint;
- title;
- reviewer;
- provider;
- model;
- Run ID.

`--expected-run-id` must equal the persisted Run ID.

### 5.3 Immutable Continue evidence

The Run must contain one immutable Canary review whose decision is `continue`.

`--expected-canary-review-id` must equal the persisted Review ID. The Operator also checks that:

- Review owner equals Run/Readiness owner;
- reviewed Case IDs still exist;
- every reviewed Case still proves an Attempt;
- Continue freezes at least one successful Extraction ID;
- every reviewed Case has one frozen Trace ID;
- before the first Resume, current Case pointers match the frozen Review snapshot.

After Resume begins, a retry may update a Run Case's current Extraction/Trace pointer. The immutable Review IDs remain the historical approval evidence and are not required to equal later current pointers. The Review notes body is not emitted by the CLI or Session Manifest.

### 5.4 Resume budget

The requested budget must be positive and no greater than:

```text
total Run Cases - completed Cases
```

Completed means `reused + extracted`. Failed or deferred Cases remain eligible for controlled retry.

The budget is an upper limit on new Provider attempts. Reused Extractions do not consume it.

A Provider HTTP `504` is treated as a gateway timeout, not as a reason to increase the local HTTP timeout. Within one invocation, Acceptance may retry the same Case exactly once **only when at least one explicit attempt remains in the requested budget**. The first 504 and the retry are separate Provider attempts with separate Trace evidence and both consume budget. If the retry also returns 504, the invocation fails fast and all later Cases are deferred. HTTP `429` and `503` still fail fast immediately without an automatic retry.

### 5.5 Execution lease

ADR-0033 execution leases protect the stable Dataset/Title/Reviewer/Cohort identity.

If another process owns the lease:

```json
{
  "executionOutcome": "execution_rejected",
  "executionError": {
    "type": "RequirementAcceptanceExecutionLeaseUnavailableError"
  },
  "preparation": null,
  "postReadiness": null,
  "liveExtractionAttemptsObserved": 0
}
```

The rejected process must not create a new Trace or increment a Case attempt.

## 6. Output contract

### 6.1 Operator plan

```json
{
  "operator": {
    "state": "ready_for_explicit_execution",
    "planReady": true,
    "executionAuthorized": false,
    "expectedRunId": "reqacceptrun_...",
    "expectedCanaryReviewId": "reqacceptcanary_...",
    "runId": "reqacceptrun_...",
    "canaryReviewId": "reqacceptcanary_...",
    "requestedMaxNewExtractions": 5,
    "attemptedCallsBefore": 3,
    "completedCaseCountBefore": 3,
    "remainingCaseCountBefore": 17,
    "blockers": []
  }
}
```

States:

```text
blocked
ready_for_explicit_execution
authorized
```

### 6.2 Attempt evidence

```json
{
  "liveExtractionAttemptsObserved": 2,
  "newAttemptEvidence": [
    {
      "caseId": "reqacceptcase_...",
      "caseIndex": 3,
      "jobId": "job_...",
      "status": "extracted",
      "attemptDelta": 1,
      "extractionId": "reqrun_...",
      "traceRunId": "run_...",
      "errorCode": null
    }
  ],
  "missingTraceCaseIds": [],
  "attemptBudgetExceeded": false
}
```

`liveExtractionAttemptsObserved` comes from persisted Case `attemptCount` deltas. It does not infer success from terminal text.

### 6.3 Partial clean resume

When Cases remain:

```json
{
  "executionOutcome": "completed",
  "furtherResumeRequired": true,
  "manualReviewReady": false,
  "postReadiness": {
    "nextAction": "resume_run",
    "recommendedCommand": ".venv/bin/python -m scripts.operate_requirement_acceptance_resume ..."
  }
}
```

The next command contains the same explicit Run and Canary Review IDs.

### 6.4 Final Batch handoff

When all 20 Cases have same-cohort current Extractions:

```json
{
  "executionOutcome": "completed",
  "furtherResumeRequired": false,
  "manualReviewReady": true,
  "manualReviewUrl": "http://localhost:3000/evals/requirements/manual/<batch-id>",
  "postReadiness": {
    "nextAction": "open_manual_review",
    "recommendedCommand": null
  }
}
```

No more Provider command is recommended.

## 7. Exit codes

```text
0  Plan ready, or clean partial/final resume completed
1  Plan blocked by current state, or execution completed with attention required
2  Invalid/rejected command, missing explicit confirmation, unsafe path,
   execution lease conflict or application gate rejection
```

Exit `0` does not mean Requirement quality passed. It only means the operational step completed cleanly.

## 8. Failure behavior

### Wrong Run or Review ID

Rejected before Provider Runtime construction and before Session Manifest execution evidence is written.

### Stop or pending Review

Rejected because `nextAction` is not `resume_run`.

### Budget above remaining Cases

Rejected before execution. The command does not silently clamp the requested budget.

### Missing Trace on a new Attempt

The Run evidence is preserved and the command returns `completed_with_attention_required`.

### Dataset changed during execution

The Run evidence is preserved, but the result requires attention. The before/after file SHA-256 and byte count are emitted.

### Execution lease lost

Provider or database side effects may already have happened. The command returns `liveExtractionAttemptsObserved=null`, requires a fresh Readiness/Run/Trace inspection and never claims zero attempts.

### Post-execution Run or Review mismatch

The Provider side effect may already have happened. The command returns attention-required and does not claim zero attempts.

### Session Manifest failure

Database Run/Case/Trace evidence remains authoritative. A failed Manifest update never rewrites the execution as not executed.

## 9. Evidence hierarchy

```text
Database Run / Case / immutable Canary Review
→ Trace
→ Extraction
→ frozen Manual Review Batch
→ Session Manifest
→ CLI JSON
→ terminal text
```

## 10. Privacy

The CLI and Session Manifest do not output:

- API Key;
- Authorization header;
- complete JD text;
- raw model output;
- human Canary Review notes body.

Local private paths are emitted and must be removed from public screenshots or demos.

## 11. Current local status

As of 2026-08-05:

```text
Configured database revision = 20260804_0013
Alembic head = 20260805_0014
Provider = disabled
Model = blank
API Key configured = false
Canonical private formal dataset = absent
```

Therefore the Operator is implemented and tested, but a real Resume cannot run in the current local environment.
