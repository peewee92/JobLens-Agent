# Requirement Acceptance Preparation CLI Contract

Status: P0-3B-3C controlled local workflow

## Goal

Safely turn one formally accepted Collector Requirement dataset into a persistent, resumable Requirement Acceptance Run and eventually one version-frozen manual Review Batch.

The command composes existing capabilities. It never decides Review outcomes, approves a model, or starts Match.

For formal live operations, this is now the lower-level execution primitive. Use the dedicated [Live Canary Operator](REQUIREMENT-ACCEPTANCE-LIVE-CANARY-OPERATOR.md) before human review and the [Controlled Resume Operator](REQUIREMENT-ACCEPTANCE-CONTROLLED-RESUME.md) after an immutable Continue decision. Those Operators bind canonical private paths, explicit evidence IDs, execution confirmation, Session Manifest and post-run verification.

## 1. Preflight — no credentials, writes or calls

```bash
cd services/backend
.venv/bin/python -m scripts.prepare_requirement_acceptance \
  /absolute/path/to/boss-job-filter-requirement-review-v1.4.6-*.json \
  --preflight \
  --json
```

Preflight validates the complete formal input and returns:

```json
{
  "datasetFingerprint": "sha256-hex",
  "sourceVersion": "1.4.6",
  "generatedAt": "2026-08-04T12:00:00.000Z",
  "selectedCount": 20,
  "totalDescriptionCharacters": 12345,
  "minimumDescriptionCharacters": 300,
  "maximumDescriptionCharacters": 1600,
  "averageDescriptionCharacters": 617.25,
  "dbWrites": 0,
  "providerCalls": 0
}
```

`--preflight` returns before constructing Provider, Repository or DB execution dependencies. `--reviewer` is not required.

The fingerprint excludes `generatedAt`. A timestamp-only re-export of the same ordered evidence keeps the same fingerprint and resumes the same Run.

## 2. Low-level live canary primitive

The dedicated Live Canary Operator is the recommended entry point. Direct use below remains documented for application-layer testing and recovery only.

OpenAI requires an explicit call limit:

```bash
cd services/backend
REQUIREMENT_EXTRACTOR_PROVIDER=openai \
OPENAI_API_KEY=... \
REQUIREMENT_EXTRACTOR_MODEL=... \
.venv/bin/python -m scripts.prepare_requirement_acceptance \
  /absolute/path/to/boss-job-filter-requirement-review-v1.4.6-*.json \
  --reviewer will \
  --title "2026-08-04 real Requirement acceptance" \
  --max-new-extractions 3 \
  --json
```

Recommended first live budget: `1–3`.

Without `--max-new-extractions`, OpenAI mode exits with configuration error before Import.

## 3. Human Canary gate and Resume

The same Run may make at most 3 cumulative OpenAI calls without a human decision. After inspecting the Canary Job, exact Requirement Extraction and Trace evidence, open the Web workbench:

```text
/evals/requirements/canary
/evals/requirements/canary/{runId}
```

Then submit one immutable `continue` or `stop` decision. The Web command proxies:

```http
POST /api/v1/requirement-acceptance-runs/{runId}/canary-review
```

Without `continue`, a request that would exceed 3 cumulative attempts is rejected before a new Import or Provider call. `stop` permanently blocks this frozen Run.

After `continue`, use the dedicated Controlled Resume Operator. It requires the same dataset/title/reviewer/cohort plus the exact Run ID and immutable Canary Review ID:

```bash
.venv/bin/python -m scripts.operate_requirement_acceptance_resume \
  /private/path/formal-review.json \
  --reviewer will \
  --title "2026-08-04 real Requirement acceptance" \
  --max-new-extractions 5 \
  --expected-run-id reqacceptrun_<id> \
  --expected-canary-review-id reqacceptcanary_<id> \
  --json
```

This first command is Plan mode. Add the documented execute and confirmation flags only after reviewing the Plan. Safe existing Extractions are reused and do not consume the current limit. The Application layer, not only either CLI, still enforces the cumulative human gate.

## 4. Fixture engineering smoke

Fixture remains opt-in:

```bash
REQUIREMENT_EXTRACTOR_PROVIDER=fixture \
.venv/bin/python -m scripts.prepare_requirement_acceptance \
  /absolute/path/to/formal-review.json \
  --reviewer will \
  --title "Fixture acceptance smoke" \
  --allow-fixture \
  --max-new-extractions 3
```

Fixture validates engineering behavior only. Its Review Batch is never formal live evidence.

## Options

```text
--preflight                 validate/fingerprint only; zero writes/calls
--reviewer <text>           required unless --preflight
--title <text>              optional; defaults to generatedAt/file stem
--max-new-extractions <1-20>
                            maximum actual new Provider calls now;
                            reuse does not consume the limit
--allow-fixture             explicit fixture engineering-smoke opt-in
--json                      machine-readable result
```

## Accepted input

The JSON root must contain:

```text
purpose = requirement_manual_quality_review
qualityGate.status = ready
qualityGate.requiredSampleSize = 20
qualityGate.selectedCount = 20
qualityGate.distinctEligibleCount >= 20
qualityGate.blockers = []
jobs.length = 20
```

Every selected Job must have:

```text
detailSucceeded = true
descriptionQuality = full_jd
descriptionHasRoleEvidenceSignal = true
descriptionNoiseCount = 0
requirementReviewEligible = true
requirementReviewIneligibilityReasons = []
sourceVersion = dataset.version
unique URL
self-consistent UTF-16 descriptionLength
self-consistent fnv1a32 descriptionHash
pairwise similarity below declared threshold
```

Quality-gate counts and `excludedNearDuplicates` must be internally consistent. Invalid formal input is rejected before Import.

## Result semantics

### Exit 0

All 20 Jobs have current same-cohort Extractions and one exact Review Batch was created or reused.

### Exit 1

Import/Run exists but work remains:

- failed Case(s);
- deferred Case(s) because the explicit limit was reached;
- Provider-wide unavailable condition.

Successful Trace/Extraction rows and Run progress remain persisted. No incomplete Batch is created.

### Exit 2

Configuration/formal input is rejected, including:

- missing/invalid file;
- non-ready or inconsistent dataset;
- invalid call limit;
- disabled provider;
- fixture without `--allow-fixture`;
- OpenAI without key/model;
- OpenAI without explicit `--max-new-extractions`;
- first live command requesting more than 3 calls;
- cumulative fourth call without Canary `continue`;
- a Run with immutable Canary `stop`;
- Import identity/order failure.

Unexpected programming or persistence errors terminate loudly; they are not converted into Case failures.

## JSON output

```json
{
  "runId": "reqacceptrun_xxx",
  "datasetFingerprint": "sha256-hex",
  "importId": "imp_xxx",
  "sourceVersion": "1.4.6",
  "received": 20,
  "createdJobs": 20,
  "updatedJobs": 0,
  "reusedExtractions": 0,
  "createdExtractions": 3,
  "failedExtractions": 0,
  "deferredExtractions": 17,
  "maxNewExtractions": 3,
  "provider": "openai",
  "model": "configured-model",
  "extractorVersion": "requirement-extractor-v1",
  "promptVersion": "requirement-extraction-v1",
  "batchId": null,
  "batchReused": false,
  "readyForManualReview": false,
  "cases": []
}
```

Each invocation Case includes:

```text
status = extracted | reused | failed | deferred
extractionId
traceRunId
errorCode
errorMessage
```

The invocation status describes this command. Persistent historical provenance is available through the Run API and may differ appropriately; for example a Case originally extracted by this Run remains persistent `extracted` when a later invocation reports it as `reused`.

## New-call budget

```text
safe reuse       = 0 calls
successful call  = 1 call
failed call      = 1 call
deferred         = 0 calls
```

When the limit is reached, remaining non-reusable Cases are `deferred`. Rerun the same identity to continue.

Provider-wide unavailable behavior:

- the first attempted unavailable call records a failed Trace;
- later non-reusable Cases are deferred without calls;
- any later Case already safely reusable may still be recognized.

## Persistent Run

One Run is identified by:

```text
datasetFingerprint
title
reviewer
provider
model
extractorVersion
promptVersion
```

It stores:

- first/latest Import IDs;
- latest observed source export timestamp;
- 20 ordered Case states;
- attempt counts;
- Trace and Extraction references;
- optional Batch ID.

A prior failed Trace is not overwritten merely because a later invocation defers the Case.

## Read progress

```http
GET /api/v1/requirement-acceptance-runs/{runId}
```

See `REQUIREMENT-ACCEPTANCE-RUN-API.md`.

There is no HTTP POST to start/resume Provider work in this slice. The only POST is the short, non-Provider Canary human decision command.

## Reuse rule

An Extraction is safe only when:

```text
inputHash == SHA-256(current persisted description)
provider == configured provider
model == configured model
extractorVersion == current workflow version
promptVersion == current prompt version
latest Extraction for the Job
```

## Batch rule

Batch creation requires exactly 20 successful current Extractions from one cohort and no failed/deferred Cases in the invocation. An exact existing Batch is reused when title, reviewer and ordered Extraction IDs match.

## Human boundary

Before the cumulative fourth live call, the learner must personally inspect the available 1–3 Canary cases and submit `continue` or `stop`; the system never generates that decision or its notes.

After Batch success, open:

```text
/evals/requirements/manual
```

The learner must personally inspect and judge every Case. The CLI never:

- accepts/rejects a Case;
- chooses issue codes;
- writes human notes;
- promotes a model/baseline;
- starts Match or Ranking.

## Privacy and Trace

- Run Case stores source metadata and description SHA-256, not another full JD copy.
- Trace input refs contain Job ID, description hash and character count.
- Trace output may contain structured Requirements and remains sensitive local data.
- API credentials are not written to Run records or output.

## Scope exclusions

- queue workers or distributed scheduling;
- automatic retry/backoff;
- browser-triggered Provider execution;
- automatic human labels/model approval;
- Match, Eligibility, Ranking or application automation.
