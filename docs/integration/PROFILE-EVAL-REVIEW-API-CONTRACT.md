# Profile Eval Review API Contract

## Purpose

Separate technical model-quality evidence from an explicit human governance decision.

```text
Profile Eval Run
→ technical Gate
→ human review
→ accepted baseline
```

An Eval Run is immutable execution evidence. A Review is a separate immutable decision about whether a live, technically eligible Run may become the official comparison baseline.

## Scope

Included:

- accept or reject one live Profile Eval Run;
- store reviewer, notes and review timestamp;
- allow exactly one Review per Eval Run;
- expose Review in Eval detail;
- query the current accepted baseline;
- allow the live Eval CLI to resolve the accepted baseline before calling the Provider.

Excluded:

- editing or deleting a Review;
- accepting Fixture runs;
- accepting Gate-failed or non-release-eligible runs;
- automatic deployment;
- Web review dashboard;
- multi-user authentication or cryptographic reviewer identity.

## Review command

```http
POST /api/v1/profile-evals/{evalRunId}/review
Content-Type: application/json
```

Request:

```json
{
  "decision": "accepted",
  "reviewer": "local-user",
  "notes": "Reviewed all ten cases and their Trace evidence. No unsupported facts observed."
}
```

Rules:

- `decision` is `accepted` or `rejected`;
- `reviewer` must be non-empty after trimming;
- `notes` must contain at least 10 visible characters after trimming;
- the Eval Run must exist;
- only `mode=live` Runs may receive an official Review;
- `accepted` additionally requires `gatePassed=true` and `releaseEligible=true`;
- `rejected` may be recorded for any live Run, including Gate-failed Runs;
- one Eval Run may receive only one immutable Review.

Success:

```http
201 Created
```

```json
{
  "id": "review_...",
  "evalRunId": "eval_...",
  "decision": "accepted",
  "reviewer": "local-user",
  "notes": "Reviewed all ten cases and their Trace evidence. No unsupported facts observed.",
  "reviewedAt": "2026-08-03T06:00:00Z"
}
```

## Current accepted baseline

```http
GET /api/v1/profile-evals/baseline/accepted
```

Returns the most recently created `accepted` Review and its Eval Run summary.

```json
{
  "review": {
    "id": "review_...",
    "evalRunId": "eval_...",
    "decision": "accepted",
    "reviewer": "local-user",
    "notes": "Reviewed all ten cases and their Trace evidence. No unsupported facts observed.",
    "reviewedAt": "2026-08-03T06:00:00Z"
  },
  "run": {
    "id": "eval_...",
    "datasetVersion": "profile-extraction-v1",
    "mode": "live",
    "provider": "openai",
    "model": "runtime-configured-model",
    "extractorVersion": "profile-extractor-v1",
    "promptVersion": "profile-proposal-v1",
    "gateVersion": "profile-eval-gate-v1",
    "baselineRunId": null,
    "totalCases": 10,
    "passedCases": 10,
    "casePassRate": 1.0,
    "workflowSuccessRate": 1.0,
    "skillRecall": 1.0,
    "yearsAccuracy": 1.0,
    "forbiddenFactRate": 0.0,
    "gatePassed": true,
    "releaseEligible": true,
    "createdAt": "2026-08-03T05:30:00Z"
  }
}
```

When no accepted baseline exists:

```http
404 accepted_profile_eval_baseline_not_found
```

## Eval detail extension

`GET /api/v1/profile-evals/{evalRunId}` adds:

```json
{
  "review": null
}
```

or an immutable Review object after review.

## Stable errors

| HTTP | Code | Meaning |
| ---: | --- | --- |
| 404 | `profile_eval_run_not_found` | Eval Run does not exist |
| 404 | `accepted_profile_eval_baseline_not_found` | no accepted live baseline exists |
| 409 | `profile_eval_run_already_reviewed` | immutable Review already exists |
| 422 | `invalid_profile_eval_review` | reviewer/notes invalid, Fixture Run, or acceptance requirements not met |

## CLI baseline resolution

The live Eval CLI supports:

```bash
PROFILE_EXTRACTOR_PROVIDER=openai \
PROFILE_EXTRACTOR_MODEL='<model>' \
OPENAI_API_KEY='<secret>' \
uv run python -m scripts.run_profile_eval --accepted-baseline
```

Rules:

- `--accepted-baseline` and `--baseline-run-id` are mutually exclusive;
- `--accepted-baseline` is only valid for `mode=live`;
- baseline resolution occurs before any Provider call;
- when no accepted baseline exists, exit code is 1 with zero new Trace and zero new Eval Run.

## Evidence of completion

- database Review row;
- immutable one-review unique constraint;
- API 201/404/409/422 tests;
- Fixture acceptance rejection;
- Gate-failed acceptance rejection;
- accepted baseline switching test;
- CLI preflight test proving zero Provider/Trace work when baseline is unavailable;
- architecture tests proving Router does not decide acceptance rules or manage transactions.
