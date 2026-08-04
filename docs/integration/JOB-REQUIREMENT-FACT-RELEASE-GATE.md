# Job Requirement Fact Release Gate Contract

Status: implemented

## Goal

Before future Eligibility or Match consumes `JobRequirement`, answer one narrow question:

> Are this Job's latest Requirement facts current, traceable, exact, and produced by the currently human-accepted Requirement cohort?

This endpoint does not run Extraction or Match.

## Endpoint

```http
GET /api/v1/jobs/{jobId}/requirement-release-readiness
```

### Existing Job

Returns `200` for both eligible and blocked states.

```json
{
  "jobId": "job_xxx",
  "releaseEligible": true,
  "currentDescriptionSha256": "sha256",
  "extractionId": "reqrun_xxx",
  "extractionInputHash": "sha256",
  "provider": "openai",
  "model": "model-name",
  "extractorVersion": "requirement-extractor-v1",
  "promptVersion": "requirement-extraction-v1",
  "traceRunId": "run_xxx",
  "requirementCount": 8,
  "acceptedBaselineBatchId": "reqreviewbatch_xxx",
  "acceptedBaselineDecisionId": "reqbatchdecision_xxx",
  "acceptedBaselineEvidenceFingerprint": "sha256",
  "blockers": []
}
```

Blocked example:

```json
{
  "jobId": "job_xxx",
  "releaseEligible": false,
  "currentDescriptionSha256": "sha256",
  "extractionId": "reqrun_xxx",
  "extractionInputHash": "old-sha256",
  "provider": "openai",
  "model": "model-name",
  "extractorVersion": "requirement-extractor-v1",
  "promptVersion": "requirement-extraction-v1",
  "traceRunId": "run_xxx",
  "requirementCount": 8,
  "acceptedBaselineBatchId": null,
  "acceptedBaselineDecisionId": null,
  "acceptedBaselineEvidenceFingerprint": null,
  "blockers": [
    {
      "code": "accepted_baseline_missing",
      "message": "No current human-accepted Requirement Review baseline exists."
    },
    {
      "code": "extraction_input_stale",
      "message": "The latest Extraction no longer matches the current Job description."
    }
  ]
}
```

### Missing Job

```http
404 Not Found
```

```json
{
  "error": {
    "code": "job_not_found",
    "message": "Job 'job_xxx' was not found"
  }
}
```

A missing Job is a resource error. A present Job with untrusted facts is a readiness result.

## Blocker codes

| Code | Meaning | Required action |
|---|---|---|
| `accepted_baseline_missing` | No current human-accepted 20-Case baseline | Complete real Manual Review and Final Decision, or replace stale evidence |
| `requirement_extraction_missing` | Job has no Extraction | Run the controlled Extraction command after prerequisites are met |
| `extraction_input_stale` | Extraction input hash differs from current JD | Re-extract the current JD |
| `extraction_cohort_mismatch` | Extraction provider/model/version/prompt differs from accepted baseline | Re-extract with the accepted cohort or create a new formal baseline |
| `requirements_empty` | No persisted Requirement facts | Inspect Provider/validation and re-extract |
| `requirement_count_mismatch` | Summary count differs from loaded facts | Treat as persistence integrity failure |
| `trace_missing` | Linked Trace does not exist | Investigate persistence/provenance integrity |
| `trace_failed` | Trace contains an execution error | Do not use the Extraction; re-run after fixing the failure |
| `trace_capability_mismatch` | Trace belongs to another capability | Investigate incorrect linkage |
| `trace_cohort_mismatch` | Trace model/version/prompt differs from Extraction | Investigate immutable evidence corruption |
| `trace_input_mismatch` | Trace Job/hash refs differ from Extraction | Investigate input provenance corruption |
| `trace_output_mismatch` | Trace Requirement output differs from persisted facts | Investigate output/persistence corruption |

The response may contain more than one blocker.

## Exact release rule

```text
releaseEligible =
  accepted baseline exists
  AND latest Extraction exists
  AND extraction.inputHash == SHA256(current JD)
  AND extraction cohort == accepted baseline cohort
  AND persisted Requirements are non-empty
  AND persisted count is consistent
  AND Trace exists and succeeded
  AND Trace capability/cohort/input match Extraction
  AND Trace Requirement output exactly equals persisted Requirement facts
```

No percentage or score threshold is evaluated by this endpoint.

## Exact Trace output comparison

For every Requirement in source order, the Gate compares:

- `type`;
- `originalText`;
- `normalizedCapability`;
- `importance`;
- `evidenceSpan`;
- `confidence`.

Comparing only list length is insufficient.

## Side-effect contract

The endpoint is read-only:

```text
dbWrites = 0
providerCalls = 0
newTraces = 0
newExtractions = 0
newReviews = 0
newMatchReports = 0
```

It must remain safe to refresh from the Job detail page.

## Web behavior

The Job detail page reads the endpoint through the server-only Backend client.

### Eligible

It displays:

- `已通过 Requirement 事实发布门禁`；
- accepted Batch ID；
- Final Decision ID；
- accepted evidence fingerprint。

This means only that Requirement facts are allowed to enter a future Match workflow. It does not mean Match has run or that the Job is recommended.

### Blocked

It displays:

- `不可供 Match 使用`；
- every blocker label；
- stable blocker code。

The page does not calculate thresholds or inspect database tables directly.

## Curl

```bash
curl \
  http://127.0.0.1:8000/api/v1/jobs/job_xxx/requirement-release-readiness
```

## Verification matrix

| Behavior | Evidence |
|---|---|
| missing baseline blocks | Application + API + smoke |
| missing Extraction blocks | Application test |
| changed JD blocks | Application test |
| cohort mismatch blocks | Application test |
| empty/count mismatch blocks | Application test |
| missing/failed Trace blocks | Application test |
| Trace identity/input/cohort mismatch blocks | Application test |
| same count but different Trace content blocks | Application test |
| complete trust chain releases | Application + smoke |
| Query is read-only | DB Extraction/Trace count assertions |
| UI consumes Backend facts | Web architecture test |
| baseline stale revokes release | FastAPI + production Next smoke |

## Scope exclusions

- Profile readiness;
- SearchIntent readiness;
- deterministic Eligibility;
- Semantic Match;
- recommendation level;
- MatchReport persistence;
- batch release/readiness optimization;
- real Provider quality conclusion.
