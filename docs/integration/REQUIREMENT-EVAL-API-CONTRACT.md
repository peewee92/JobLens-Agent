# Requirement Eval Governance API Contract

Status: implemented through Phase 3B-2 on 2026-08-03

## Purpose

Expose immutable Requirement Extraction quality evidence, human governance decisions and the current accepted baseline without triggering model execution or exposing raw JD text.

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
- derived `comparison` when a baseline exists;
- immutable `review` when one exists.

### Submit immutable Review

```http
POST /api/v1/requirement-evals/{evalRunId}/review
Content-Type: application/json
```

```json
{
  "decision": "accepted",
  "reviewer": "local-reviewer",
  "notes": "Reviewed every Requirement case and linked Trace before accepting."
}
```

Successful response:

```http
201 Created
```

```json
{
  "id": "reqreview_xxx",
  "evalRunId": "reqeval_xxx",
  "decision": "accepted",
  "reviewer": "local-reviewer",
  "notes": "Reviewed every Requirement case and linked Trace before accepting.",
  "reviewedAt": "2026-08-03T11:00:00Z"
}
```

Policy:

- Fixture Run: neither accept nor reject;
- Gate-failed Live Run: reject only;
- Gate-passed, release-eligible Live Run: accept or reject;
- any already reviewed Run: no second Review;
- reviewer must not be blank;
- notes must contain at least 10 trimmed characters.

### Get current accepted baseline

```http
GET /api/v1/requirement-evals/baseline/accepted
```

Response:

```json
{
  "review": {
    "id": "reqreview_xxx",
    "evalRunId": "reqeval_xxx",
    "decision": "accepted",
    "reviewer": "local-reviewer",
    "notes": "Reviewed all cases and Trace evidence.",
    "reviewedAt": "2026-08-03T11:00:00Z"
  },
  "run": {
    "id": "reqeval_xxx",
    "mode": "live",
    "gatePassed": true,
    "releaseEligible": true
  }
}
```

The full Run summary is returned; the abbreviated example shows governance-critical fields.

## Stable error codes

| Status | Code | Meaning |
|---:|---|---|
| 404 | `requirement_eval_run_not_found` | requested Run does not exist |
| 404 | `accepted_requirement_eval_baseline_not_found` | no accepted live baseline exists |
| 409 | `requirement_eval_run_already_reviewed` | immutable Review already exists |
| 422 | `invalid_requirement_eval_review` | mode, Gate, reviewer or notes violate policy |
| 422 | `request_validation_error` | request shape or enum is invalid |

## Privacy boundary

The API does not expose:

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

`releaseEligible=true` means eligible for human acceptance review. It is not the same as `review.decision=accepted`.

## Accepted baseline semantics

The current baseline is derived from immutable history:

```text
review.decision = accepted
AND run.mode = live
AND run.gatePassed = true
AND run.releaseEligible = true
ORDER BY reviewedAt DESC, reviewId DESC
LIMIT 1
```

`baselineRunId` on a new Eval Run records which baseline was used for comparison. Metric deltas are derived on read.

CLI:

```bash
REQUIREMENT_EXTRACTOR_PROVIDER=openai \
uv run python -m scripts.run_requirement_eval --accepted-baseline
```

The option is rejected for Fixture mode. Missing accepted baseline is detected before provider setup or Workflow execution.

## Web routes

```text
/evals/requirements
/evals/requirements/{evalRunId}
POST /api/requirement-evals/{evalRunId}/review
```

The browser posts only to the same-origin Next route. Backend policy remains authoritative.

## Out of scope

- Eval Run creation over HTTP;
- Review edits or deletion;
- authenticated reviewer/RBAC;
- real Provider approval evidence;
- Match enablement;
- mutation or deletion of Eval history.
