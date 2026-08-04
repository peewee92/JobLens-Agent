# Requirement Acceptance Readiness CLI

Status: P0-3B-3F operational contract

## Goal

Before any real Requirement Extraction call, determine the next safe action using formal dataset evidence, live configuration, database migration state and the existing Acceptance Run.

The command is read-only:

```text
dbWrites = 0
providerCalls = 0
```

## Command

```bash
cd services/backend
.venv/bin/python -m scripts.check_requirement_acceptance_readiness \
  /absolute/path/to/formal-review.json \
  --reviewer will \
  --title "2026-08-04 real Requirement acceptance" \
  --max-new-extractions 3 \
  --web-base-url http://localhost:3000 \
  --session-manifest ./artifacts/requirement-acceptance-session.json \
  --json
```

## Arguments

```text
dataset                         formal 20-JD review JSON
--reviewer <text>               stable Run/review owner
--title <text>                  stable Run identity; defaults from generatedAt/file
--max-new-extractions <1-20>    requested new Provider-call budget
--web-base-url <url>            used only to build navigation URLs
--session-manifest <path>       atomic secret-free Session/Evidence JSON output
--json                          machine-readable output
```

## Checks

### Dataset

Reuses the existing formal Requirement acceptance Preflight:

- `purpose=requirement_manual_quality_review`;
- exactly 20 selected Jobs;
- ready quality gate;
- no blockers;
- consistent length/hash metadata;
- unique URLs;
- no near-duplicate pair above threshold;
- all Jobs eligible for Requirement review.

Invalid dataset exits with code 2.

### Runtime identity

- `REQUIREMENT_EXTRACTOR_PROVIDER=openai`;
- non-blank `REQUIREMENT_EXTRACTOR_MODEL`;
- non-blank reviewer and title.

### Credential

The command checks only whether `OPENAI_API_KEY` exists.

It never prints:

- key value;
- Authorization header;
- Provider request body.

### Database

- database is readable;
- current `alembic_version` equals dynamic Alembic head;
- for SQLite, a missing file is not created;
- Existing Run is queried only after database/config identity is valid.

### Run state

It detects:

- no Run;
- 1–2 unreviewed attempts;
- awaiting Canary review;
- immutable Continue;
- immutable Stop;
- attached Manual Review Batch.

## JSON output

```json
{
  "datasetFingerprint": "sha256-hex",
  "sourceVersion": "1.4.6",
  "selectedCount": 20,
  "provider": "openai",
  "model": "gpt-model",
  "apiKeyConfigured": true,
  "reviewer": "will",
  "title": "2026-08-04 real Requirement acceptance",
  "requestedMaxNewExtractions": 3,
  "databaseReachable": true,
  "databaseRevision": "20260805_0014",
  "migrationHead": "20260805_0014",
  "workflowReady": true,
  "providerExecutionAllowed": true,
  "readyForNextAction": true,
  "nextAction": "run_canary",
  "runId": null,
  "runStatus": null,
  "attemptedCalls": 0,
  "canaryDecision": null,
  "batchId": null,
  "workbenchUrl": null,
  "manualReviewUrl": null,
  "recommendedCommand": ".venv/bin/python -m scripts.operate_requirement_acceptance_canary ...",
  "sessionId": "reqacceptsession_xxx",
  "sessionManifestPath": "/private/path/artifacts/requirement-acceptance-session.json",
  "blockers": [],
  "dbWrites": 0,
  "providerCalls": 0
}
```

## nextAction

### `fix_blockers`

Workflow identity cannot be safely evaluated. Read blocker codes and fix them before live work.

### `run_canary`

No Run exists, or the unreviewed cumulative budget remains below 3.

### `review_canary`

Provider calls must stop. Open `workbenchUrl` and submit the human Continue/Stop decision.

### `resume_run`

An immutable Continue exists. A new explicit budget may resume the same Run.

### `open_manual_review`

A 20-case Batch exists. Open `manualReviewUrl`; more Provider calls are unnecessary.

### `stopped`

The Run has an immutable Stop decision. Create a genuinely new dataset/cohort/Run only after diagnosing the failure; do not overwrite the decision.

## Readiness booleans

### workflowReady

The dataset identity, runtime identity and database schema can be interpreted reliably.

### providerExecutionAllowed

A new Provider call is currently permitted.

### readyForNextAction

The next action is clear and executable. Human Review and Manual Review can be ready even when Provider execution is false.

## Blocker schema

```json
{
  "scope": "provider_execution",
  "code": "openai_api_key_missing",
  "message": "Set OPENAI_API_KEY before a live Provider call. The key value is never printed."
}
```

Scopes:

```text
workflow
provider_execution
```

Stable codes currently include:

```text
database_unreachable
database_migration_not_current
live_provider_not_configured
live_model_not_configured
reviewer_missing
title_missing
openai_api_key_missing
max_new_extractions_missing
max_new_extractions_out_of_range
initial_canary_limit_exceeded
remaining_canary_limit_exceeded
```

## Exit codes

```text
0  next action is ready: run/resume, human Canary review, or Manual Review
1  readiness evaluated but blockers remain, or the Run is stopped
2  file/JSON/formal dataset is invalid
```

Exit 0 does not mean the model passed quality review.

## Examples

### Missing Key

```json
{
  "workflowReady": true,
  "providerExecutionAllowed": false,
  "readyForNextAction": false,
  "nextAction": "run_canary",
  "blockers": [
    {
      "scope": "provider_execution",
      "code": "openai_api_key_missing"
    }
  ]
}
```

### Awaiting human review

```json
{
  "workflowReady": true,
  "providerExecutionAllowed": false,
  "readyForNextAction": true,
  "nextAction": "review_canary",
  "attemptedCalls": 3,
  "workbenchUrl": "http://localhost:3000/evals/requirements/canary/reqacceptrun_xxx",
  "blockers": []
}
```

### Continue then resume

```json
{
  "providerExecutionAllowed": true,
  "nextAction": "resume_run",
  "canaryDecision": "continue",
  "recommendedCommand": ".venv/bin/python -m scripts.operate_requirement_acceptance_resume ... --expected-run-id reqacceptrun_xxx --expected-canary-review-id reqacceptcanary_xxx --json"
}
```

### Manual Batch ready

```json
{
  "providerExecutionAllowed": false,
  "readyForNextAction": true,
  "nextAction": "open_manual_review",
  "manualReviewUrl": "http://localhost:3000/evals/requirements/manual/reqreviewbatch_xxx"
}
```

## Recommended operation sequence

```text
1. Run Readiness
2. If fix_blockers: fix only listed blockers and rerun
3. If run_canary/resume_run: run the recommended dedicated Operator in Plan mode
4. Review the Operator Plan, then add its explicit execute and confirmation flags
5. If review_canary: open workbench and make the human decision
6. If open_manual_review: complete all 20 case judgments
7. Never interpret Readiness as model-quality approval
```

## Scope exclusions

- Provider network health call;
- automatic migration;
- automatic Import or Extraction;
- automatic Continue/Stop;
- API Key persistence;
- queue/lease/cancellation;
- Match/Ranking;
- production authentication/RBAC.
