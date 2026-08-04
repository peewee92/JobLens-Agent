# Requirement Acceptance Run and Canary Review API

Status: P0-3B-3E operational read + short human command contract

## Goal

Expose persistent Requirement acceptance progress, provide enough bounded evidence for the Canary Review Web Workbench, and allow one short immutable human decision without allowing HTTP clients to start cost-bearing Provider work.

## 1. List Runs

```http
GET /api/v1/requirement-acceptance-runs?limit=20&offset=0
```

Query limits:

```text
limit  1–100
 offset >= 0
```

Response:

```json
{
  "total": 1,
  "limit": 20,
  "offset": 0,
  "items": [
    {
      "id": "reqacceptrun_xxx",
      "title": "2026-08-04 real Requirement acceptance",
      "reviewer": "will",
      "provider": "openai",
      "model": "configured-model",
      "extractorVersion": "requirement-extractor-v1",
      "promptVersion": "requirement-extraction-v1",
      "status": "awaiting_canary_review",
      "attemptedCalls": 3,
      "completedCaseCount": 2,
      "failedCount": 1,
      "deferredCount": 17,
      "canaryReviewRequired": true,
      "canaryDecision": null,
      "batchId": null,
      "createdAt": "2026-08-04T10:00:00Z",
      "updatedAt": "2026-08-04T10:02:00Z"
    }
  ]
}
```

The API returns Backend-derived status. Clients may reorder the returned summaries for presentation, but must not recalculate the Run state.

## 2. Read one Run

```http
GET /api/v1/requirement-acceptance-runs/{runId}
```

Successful response: `200 OK`.

Missing Run:

```http
404 Not Found
```

```json
{
  "error": {
    "code": "requirement_acceptance_run_not_found",
    "message": "Requirement acceptance run 'reqacceptrun_xxx' was not found"
  }
}
```

Relevant response fields:

```json
{
  "id": "reqacceptrun_xxx",
  "provider": "openai",
  "model": "configured-model",
  "status": "awaiting_canary_review",
  "attemptedCalls": 3,
  "canaryReviewRequired": true,
  "canaryContinueAllowed": true,
  "canaryStopAllowed": true,
  "canaryReviewBlockReason": null,
  "canaryReview": null,
  "batchId": null,
  "cases": [
    {
      "id": "reqacceptcase_xxx",
      "caseIndex": 0,
      "sourceUrl": "https://www.zhipin.com/job_detail/example.html",
      "descriptionHash": "sha256-of-canary-input",
      "descriptionSnapshot": "the normalized persisted JD used by Extraction",
      "currentDescriptionHash": "sha256-of-current-job-description",
      "descriptionIsCurrent": true,
      "isCanaryEvidence": true,
      "jobId": "job_xxx",
      "status": "extracted",
      "attemptCount": 1,
      "extractionId": "reqrun_xxx",
      "traceRunId": "run_xxx",
      "traceCapability": "requirement_extraction",
      "traceModel": "configured-model",
      "tracePromptVersion": "requirement-extraction-v1",
      "traceLatencyMs": 1850,
      "traceInputTokens": 920,
      "traceOutputTokens": 410,
      "traceError": null,
      "traceCreatedAt": "2026-08-04T10:01:00Z",
      "errorCode": null,
      "errorMessage": null
    }
  ]
}
```

### Backend-owned policy fields

```text
canaryContinueAllowed
canaryStopAllowed
canaryReviewBlockReason
```

Web must consume these facts rather than duplicate provider/attempt/Trace/Extraction policy.

Possible block reasons include:

- the Run is not live OpenAI;
- the Run has no attempted Canary;
- more than three cumulative attempts already occurred;
- an attempted Case lacks Trace evidence;
- no Extraction succeeded, so Continue is unavailable while Stop remains possible;
- a decision or Batch already exists.

## 3. Detailed evidence retrieval

The Run endpoint returns the frozen normalized persisted JD snapshot only for Cases with `isCanaryEvidence=true`, because those are the Cases the human must inspect. Deferred/unattempted Cases expose hashes and state but not their full JD text. It also returns the current Job description hash so clients can signal later JD drift without substituting current text for historical evidence.

For new Runs:

```text
descriptionSnapshot = stripped persisted Job.description after Import
descriptionHash = SHA-256(descriptionSnapshot)
```

Raw Collector description is not the snapshot authority because Import normalization may alter the model input.

The Web workbench also reads current navigation context and exact structured evidence through existing endpoints:

```http
GET /api/v1/jobs/{jobId}
GET /api/v1/jobs/{jobId}/requirement-extractions/{extractionId}
```

It must not use the latest Requirements endpoint for a frozen Run Case. For an old pre-snapshot Run, current Job text may be used only when `descriptionIsCurrent=true`; otherwise exact historical JD evidence is unavailable and the UI must say so.

The response field `isCanaryEvidence` has time-stable semantics:

```text
before an immutable Review exists:
  attempted Case (`attemptCount > 0`)

after a Review exists:
  Case ID appears in frozen `reviewedCaseIds`
```

A failed reviewed Case remains evidence even when `extractionId = null`. Later post-Continue calls do not expand the historical Canary evidence set, and their full JD snapshots are not exposed through this review response.

## 4. Submit immutable Canary decision

```http
POST /api/v1/requirement-acceptance-runs/{runId}/canary-review
Content-Type: application/json
```

Request:

```json
{
  "reviewer": "will",
  "decision": "continue",
  "notes": "I inspected the exact Canary Jobs, Requirements and Trace evidence; the observed grounding is sufficient for controlled continuation."
}
```

Decision values:

```text
continue
stop
```

Successful response:

```http
201 Created
```

```json
{
  "id": "reqacceptcanary_xxx",
  "runId": "reqacceptrun_xxx",
  "reviewer": "will",
  "decision": "continue",
  "notes": "...",
  "reviewedCaseIds": ["reqacceptcase_a", "reqacceptcase_b"],
  "reviewedExtractionIds": ["reqrun_a", "reqrun_b"],
  "reviewedTraceRunIds": ["run_a", "run_b"],
  "reviewedAt": "2026-08-04T11:00:00Z"
}
```

The client does not submit reviewed IDs. Backend derives them from every attempted Case at decision time.

## 5. Stable errors

| HTTP | code | Meaning |
|---|---|---|
| 404 | `requirement_acceptance_run_not_found` | Run does not exist |
| 409 | `requirement_acceptance_canary_review_already_exists` | immutable decision already exists |
| 422 | `invalid_requirement_acceptance_canary_review` | reviewer/notes/evidence/provider/state is invalid |

Provider execution blocked by the Application gate is surfaced by the CLI. A future command API would map it to:

```text
409 requirement_acceptance_canary_gate_blocked
```

## 6. Review eligibility

A Canary Review is accepted only when:

```text
provider = openai
batchId = null
no existing Canary Review
reviewer = Run reviewer
notes length >= 20
cumulative Provider attempt count between 1 and 3
every attempted Case has a Trace
continue has at least one successful Extraction
```

`Stop` may remain available when all Canary calls failed, provided each attempted call has Trace evidence.

## 7. Run status semantics

```text
pending                  all Cases untouched
partial                  progress exists; cumulative cap not yet reached or approval exists
awaiting_canary_review   >=3 attempted calls, no Review, no Batch
stopped                  immutable decision = stop
ready                    20 successful current Extractions and Batch attached
```

`continue` does not create a new status and does not mean model approval. It only unlocks later explicitly budgeted CLI execution.

`ready` is historical execution completion, not proof that the attached Batch remains current after later JD updates. Query the Requirement Review Batch and use `staleCaseCount` / Case `isCurrent` for current validity.

## 8. Evidence and privacy boundaries

The Run/Review response exposes:

- Job ID and source URL;
- frozen normalized model-input JD snapshot for attempted Canary Cases only;
- historical/current description SHA-256 and currentness flag;
- Trace ID and bounded operational metadata;
- Extraction ID;
- Import IDs;
- Batch ID;
- frozen Canary decision evidence.

It does not expose:

- raw Collector payloads or unrelated candidate content;
- Provider request body;
- API keys;
- raw Trace input/output payload;
- automatic quality judgments.

The exact Extraction endpoint provides structured Requirements. Job Detail provides current navigation context; the Run snapshot remains the historical JD authority.

## 9. Execution boundary

There is still no:

```http
POST /api/v1/requirement-acceptance-runs
POST /api/v1/requirement-acceptance-runs/{runId}/resume
```

Provider execution remains CLI-owned. The Canary Review POST is allowed because it is a short database transaction with no model call.

A queued execution command requires later decisions for:

- authentication and cost ownership;
- lease/claim semantics;
- cancellation;
- retry/backoff;
- concurrent worker protection.

## 10. Web routes

```text
/evals/requirements/canary
/evals/requirements/canary/{runId}
```

The Client Component submits through the same-origin proxy:

```text
/api/requirement-acceptance-runs/{runId}/canary-review
```

The proxy forwards only the human decision command. It contains no Provider or extraction logic.

## 11. Curl examples

List:

```bash
curl 'http://localhost:8000/api/v1/requirement-acceptance-runs?limit=20&offset=0'
```

Read:

```bash
curl http://localhost:8000/api/v1/requirement-acceptance-runs/reqacceptrun_xxx
```

Continue:

```bash
curl -X POST \
  http://localhost:8000/api/v1/requirement-acceptance-runs/reqacceptrun_xxx/canary-review \
  -H 'Content-Type: application/json' \
  -d '{
    "reviewer": "will",
    "decision": "continue",
    "notes": "I inspected the exact Canary Jobs, Extractions and Trace evidence and approve controlled continuation."
  }'
```

Stop:

```bash
curl -X POST \
  http://localhost:8000/api/v1/requirement-acceptance-runs/reqacceptrun_xxx/canary-review \
  -H 'Content-Type: application/json' \
  -d '{
    "reviewer": "will",
    "decision": "stop",
    "notes": "The Canary outputs contain unacceptable omissions, so this frozen Run must stop before wider spend."
  }'
```

## 12. Scope exclusions

- HTTP-triggered Provider execution;
- editable Canary decisions;
- automatic Continue/Stop recommendation;
- automatic model approval;
- Match/Ranking;
- authentication/RBAC/CSRF hardening;
- general raw Trace explorer;
- distributed scheduling or locking.
