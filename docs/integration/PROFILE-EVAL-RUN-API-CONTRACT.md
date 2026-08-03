# Profile Eval Run API Contract

## Purpose

Persist each Profile Extraction evaluation as an immutable, reviewable run instead of treating terminal output as the quality record.

```text
profile-extraction-v1 dataset
→ configured Profile Extraction Workflow
→ one Trace per case
→ structured case results
→ aggregate metrics
→ versioned quality gate
→ immutable Eval Run
```

A Fixture run can prove the evaluation pipeline is deterministic. It can never prove that a live model is release-ready.

## Run modes

- `fixture`: deterministic CI/demo provider.
- `live`: external model provider using runtime credentials.

`releaseEligible` is true only when:

```text
mode == live
AND gatePassed == true
```

## Gate v1

Gate identifier: `profile-eval-gate-v1`.

| Metric | Rule |
| --- | --- |
| casePassRate | >= 0.90 |
| workflowSuccessRate | == 1.00 |
| skillRecall | >= 0.95 |
| yearsAccuracy | >= 0.90 when the dataset contains year expectations |
| forbiddenFactRate | == 0.00 |

The gate is versioned because changing thresholds changes the meaning of a passing run.

## Metrics

- `casePassRate`: cases with no failure divided by total cases.
- `workflowSuccessRate`: cases that produced a validated Proposal divided by total cases.
- `skillRecall`: expected skills found divided by all expected skills.
- `yearsAccuracy`: cases within the 0.5-year tolerance divided by cases with an expected year value.
- `forbiddenFactRate`: cases containing at least one forbidden unsupported term divided by total cases.

Aggregate metrics never replace case-level review.

## Persistence

### `profile_eval_runs`

Stores immutable run identity, dataset/provider/model/prompt/gate versions, aggregate metrics, gate outcome and optional baseline run.

### `profile_eval_case_results`

Stores one immutable result per dataset case:

- linked `traceRunId` when the Workflow reached a traced provider attempt;
- pass/fail;
- stable failure codes and human-readable reasons;
- expected/actual skills;
- expected/actual years;
- forbidden and observed forbidden terms.

Resume text is not copied into Eval tables. The dataset remains the controlled source and Trace retains only its existing privacy-bounded input reference.

## Read API

### List runs

```http
GET /api/v1/profile-evals?limit=20&offset=0
```

Response:

```json
{
  "total": 1,
  "limit": 20,
  "offset": 0,
  "items": [
    {
      "id": "eval_...",
      "datasetVersion": "profile-extraction-v1",
      "mode": "fixture",
      "provider": "fixture",
      "model": "fixture-profile-extractor",
      "extractorVersion": "profile-extractor-v1",
      "promptVersion": "profile-proposal-v1",
      "gateVersion": "profile-eval-gate-v1",
      "totalCases": 10,
      "passedCases": 10,
      "casePassRate": 1.0,
      "workflowSuccessRate": 1.0,
      "skillRecall": 1.0,
      "yearsAccuracy": 1.0,
      "forbiddenFactRate": 0.0,
      "gatePassed": true,
      "releaseEligible": false,
      "baselineRunId": null,
      "createdAt": "2026-08-03T00:00:00Z"
    }
  ]
}
```

### Get one run

```http
GET /api/v1/profile-evals/{evalRunId}
```

Returns the summary, optional baseline metric deltas and ordered case results.

Missing run:

```http
404 profile_eval_run_not_found
```

## CLI

```bash
PROFILE_EXTRACTOR_PROVIDER=fixture \
uv run python -m scripts.run_profile_eval
```

Optional baseline:

```bash
uv run python -m scripts.run_profile_eval --baseline-run-id eval_xxx
```

Exit code:

- `0`: the versioned gate passed;
- `1`: the gate failed or execution could not produce a persisted run.

A zero exit code for Fixture means only that the CI gate passed. It does not imply `releaseEligible=true`.

## Explicitly out of scope

- inventing a live result without credentials;
- generic multi-capability Eval platform;
- prompt/model auto-selection;
- automatic deployment approval;
- Match/Ranking Eval;
- exposing resume text through the Eval API;
- mutating or deleting historical runs.
