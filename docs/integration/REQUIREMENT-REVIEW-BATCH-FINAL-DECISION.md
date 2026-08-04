# Requirement Review Batch Final Decision Contract

Status: P0-3 Requirement quality release boundary

## Goal

Turn one complete 20-Case Manual Review Batch into an explicit human quality conclusion without confusing evidence completeness with model approval.

This contract does not define an automatic acceptance percentage. It does not run a Provider and does not execute Match.

## State model

### Evidence completeness

```text
formalEvidenceEligible =
  sampleSize == 20
  AND reviewedCount == 20
  AND staleCaseCount == 0
  AND provider != fixture
```

This says the Batch can support a formal decision. It does not say the model passed.

### Human conclusion

```text
finalDecision = null | accept_for_match | reject_for_match
```

The decision is immutable and belongs to one Batch.

### Current Match release gate

```text
matchReleaseEligible =
  formalEvidenceEligible
  AND finalDecision == accept_for_match
```

The value is derived on every read. It is never persisted as a mutable approval flag.

## Create final decision

```http
POST /api/v1/requirement-review-batches/{batchId}/final-decision
Content-Type: application/json
```

Request:

```json
{
  "decision": "accept_for_match",
  "reviewer": "will",
  "notes": "I inspected all twenty frozen Jobs, Requirements and Traces and accept this cohort for the first Match slice."
}
```

Allowed decisions:

```text
accept_for_match
reject_for_match
```

Requirements:

- Batch exists;
- reviewer exactly matches the Batch owner;
- notes contain at least 20 characters after trimming;
- Batch currently satisfies formal evidence conditions;
- every Case has an immutable Review;
- no prior Final Decision exists.

Success:

```http
201 Created
```

```json
{
  "id": "reqbatchdecision_xxx",
  "batchId": "reqreviewbatch_xxx",
  "decision": "accept_for_match",
  "reviewer": "will",
  "notes": "...",
  "sampleSize": 20,
  "reviewedCount": 20,
  "acceptedCount": 19,
  "rejectedCount": 1,
  "staleCaseCount": 0,
  "issueCodeCounts": {
    "missing_requirement": 1
  },
  "evidenceFingerprint": "sha256-hex",
  "decidedAt": "2026-08-05T07:00:00Z"
}
```

### Stable errors

Missing Batch:

```http
404 requirement_review_batch_not_found
```

Decision already exists:

```http
409 requirement_review_batch_final_decision_already_exists
```

Incomplete, Fixture, stale, wrong reviewer or short notes:

```http
422 invalid_requirement_review_batch_final_decision
```

A rejected request writes zero Final Decision rows.

## Batch detail response

```http
GET /api/v1/requirement-review-batches/{batchId}
```

Summary additions:

```json
{
  "formalEvidenceEligible": true,
  "finalDecision": "accept_for_match",
  "matchReleaseEligible": true
}
```

Detail addition:

```json
{
  "finalDecision": {
    "id": "reqbatchdecision_xxx",
    "decision": "accept_for_match",
    "acceptedCount": 19,
    "rejectedCount": 1,
    "issueCodeCounts": {
      "missing_requirement": 1
    },
    "evidenceFingerprint": "sha256-hex"
  }
}
```

`finalDecision` remains visible after the Batch becomes stale. `matchReleaseEligible` becomes false.

## Accepted baseline query

```http
GET /api/v1/requirement-review-batches/accepted-baseline
```

Success:

```http
200 OK
```

```json
{
  "decision": {
    "id": "reqbatchdecision_xxx",
    "decision": "accept_for_match",
    "evidenceFingerprint": "sha256-hex"
  },
  "batch": {
    "id": "reqreviewbatch_xxx",
    "formalEvidenceEligible": true,
    "finalDecision": "accept_for_match",
    "matchReleaseEligible": true
  },
  "issueCodeCounts": {
    "missing_requirement": 1
  }
}
```

When no current accepted Batch exists:

```http
404 accepted_requirement_review_baseline_not_found
```

This includes the case where a historically accepted Batch became stale.

## Evidence fingerprint

Schema version:

```text
requirement-review-batch-evidence-v1
```

The canonical payload includes:

- Batch ID;
- Provider / Model / Extractor / Prompt cohort;
- frozen summary and issue distribution;
- ordered Case, Job, Extraction and Trace IDs;
- JD SHA-256;
- current-version state at decision time;
- Case Review ID, decision, issue codes, notes hash and timestamp.

The API never returns raw Provider requests, API keys or internal source payloads.

## Web behavior

Page:

```text
/evals/requirements/manual/{batchId}
```

Before formal evidence:

- no Final Decision command is available;
- UI explains the missing condition.

Formal evidence, no decision:

- UI says `等待人工最终质量结论`;
- the owner may submit Accept or Reject;
- UI does not calculate an acceptance rate threshold.

Accepted and current:

- UI says `Match 门禁已放行`;
- decision notes, frozen counts and evidence fingerprint are shown.

Accepted but stale:

- historical decision stays visible;
- UI says the current Match gate is revoked;
- accepted-baseline query returns 404.

All browser writes use:

```text
/api/requirement-review-batches/{batchId}/final-decision
```

The Next Route Handler only proxies the Backend command.

## Operational sequence

```text
1. Complete all 20 Case Reviews.
2. Confirm formalEvidenceEligible=true.
3. Inspect accepted/rejected counts, issue distribution, full JD, Requirements and Traces.
4. Submit exactly one human Final Decision.
5. Read accepted-baseline before any future Match workflow.
6. If the Batch becomes stale, create and review a new current Batch; never reuse the historical acceptance as current evidence.
```

## Non-goals

- selecting an automatic quality threshold;
- claiming the sample is statistically representative;
- reviewer authentication or RBAC;
- Provider execution;
- Match scoring, ranking or recommendation;
- amending an existing decision.
