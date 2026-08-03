# Requirement Eval Read API Contract

Status: implemented in Phase 3B-1 on 2026-08-03

## Purpose

Expose immutable Requirement Extraction quality evidence without triggering model execution or exposing raw JD text.

## Endpoints

### List runs

```http
GET /api/v1/requirement-evals?limit=20&offset=0
```

Response fields:

- pagination: `total`, `limit`, `offset`;
- immutable Run summaries;
- dataset/provider/model/extractor/prompt/gate provenance;
- aggregate metrics;
- `gatePassed` and `releaseEligible`;
- optional `baselineRunId`.

### Get run detail

```http
GET /api/v1/requirement-evals/{evalRunId}
```

Response contains:

- `summary`;
- `cases` with `traceRunId`, pass/fail and diagnostics;
- derived `comparison` when a baseline exists.

### Not found

```json
{
  "error": {
    "code": "requirement_eval_run_not_found",
    "message": "Requirement Eval Run 'reqeval_xxx' was not found"
  }
}
```

## Privacy boundary

The read API does not expose:

- raw JD description;
- `originalText`;
- `evidenceSpan`;
- provider request payloads;
- secrets.

Case details link to Trace by opaque `traceRunId`. Trace remains governed by the existing tracing privacy boundary.

## Release semantics

```text
fixture + any Gate result → releaseEligible=false
live + Gate failed        → releaseEligible=false
live + Gate passed        → releaseEligible=true
```

`releaseEligible=true` means eligible for future human review, not approved for Match.

## Baseline semantics

`baselineRunId` must reference an existing immutable Requirement Eval Run. Missing baselines are rejected before Workflow execution. Metric deltas are derived on read.

## Out of scope

- run creation over HTTP;
- human review/accepted baseline;
- Web review UI;
- Match enablement;
- deletion or mutation of Eval history.
