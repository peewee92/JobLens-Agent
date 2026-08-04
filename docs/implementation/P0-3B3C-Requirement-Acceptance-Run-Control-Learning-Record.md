# P0-3B-3C｜Requirement Acceptance Run Control Learning Record

Status: engineering implementation verified; live Provider and human quality work pending

## 1. Prediction sheet — answer before reading explanations

Write your answer in your own words:

1. Should two exports with different `generatedAt` but identical ordered JD evidence resume the same Run?
2. Which evidence fields should make the dataset fingerprint change?
3. Why does an existing safe Extraction consume zero `maxNewExtractions` budget?
4. A provider call fails. Does it consume budget? What evidence must remain?
5. The current invocation has no budget left, but that Case failed in an earlier invocation. Should the database show `deferred` or retain `failed`?
6. A Case was created by this Run during canary, then reused during resume. What should the current command report? What should the persistent Run report?
7. The process exits after Trace and Extraction commit but before Run Case update. How does the next run avoid paying again?
8. Why is `GET Run` appropriate while `POST Start Run` is deliberately absent?
9. Which records prove engineering completion?
10. Which evidence is still required before entering Match?

Do not copy the implementation wording. Use a small state diagram or concrete example.

## 2. Minimal explanation

### 2.1 Preflight and execution are different operations

Preflight answers:

```text
Is this a valid formal 20-JD dataset?
What stable evidence set is it?
How large is the input?
```

It must not:

- create Import rows;
- create Jobs;
- construct a provider client;
- make model calls;
- create Trace, Extraction, Run or Batch rows.

This makes Preflight safe even when API credentials are absent.

### 2.2 Stable identity excludes time-only metadata

`generatedAt` describes when the source file was exported. It does not necessarily mean the JDs changed.

Stable fingerprint inputs are ordered evidence fields:

```text
version
URL / sourceJobId
title
company
sourceVersion
descriptionHash
```

A timestamp-only re-export resumes the same Run. A changed JD hash or changed source identity creates a different Run identity.

### 2.3 Canary budget measures risk-bearing work

`maxNewExtractions` counts actual provider calls made now.

```text
safe reuse       → 0 budget
successful call  → 1 budget
failed call      → 1 budget
deferred case    → 0 budget
```

This distinction matters because the purpose of the limit is to bound cost and exposure to a new model/prompt, not to limit how many database records the command reads.

### 2.4 Current invocation and persistent history answer different questions

Current invocation asks:

> What happened in this command?

Persistent Run asks:

> Across the entire controlled execution, how did each Case reach its current evidence?

Example:

```text
invocation 1: Case 1 extracted
invocation 2: Case 1 reused
```

CLI result for invocation 2: `reused`.

Persistent Run Case: remains `extracted`, because this Run originally created it and incurred the call.

### 2.5 Deferred is not a failure and must not erase a failure

`deferred` means no call occurred now because the call limit or provider-wide policy stopped execution.

It is not evidence that an earlier failed attempt disappeared. Therefore:

```text
prior failed + current deferred
→ persistent Case remains failed with original Trace/error
```

A later successful real extraction can replace the operational failure state, but immutable Trace history remains queryable.

### 2.6 Short transactions create a recoverable crash window

The existing Workflow records Trace, then the Extraction use case records the immutable Extraction. The Run Case update happens afterward.

Possible crash:

```text
Trace committed
Extraction committed
process exits
Run Case still pending/deferred/failed
```

On rerun, the orchestrator computes the current JD hash and cohort, finds the valid latest Extraction and safely reuses it. It then repairs the Run Case without another provider call.

This is an at-least-once orchestration pattern with deterministic deduplication, not a claim of a globally exactly-once provider call.

### 2.7 The Batch remains the completion boundary

A partial Run is useful operational evidence, but not a formal Review Batch.

Batch creation requires:

```text
20 successful current Extractions
same provider/model/extractor/prompt cohort
no failed current invocation cases
no deferred current invocation cases
```

The Batch then freezes exact Extraction IDs for human review.

### 2.8 Read progress over HTTP; execute through CLI

The API can safely expose:

```http
GET /api/v1/requirement-acceptance-runs/{runId}
```

It returns status and evidence references. It does not own provider call lifetime.

A browser-triggered start would require additional product decisions:

- who owns cost;
- request cancellation;
- queue/lease behavior;
- retry policy;
- concurrency control;
- authentication and authorization.

Those are intentionally outside this slice.

## 3. Common wrong implementation

```python
@app.post("/run-20-jobs")
def run_all():
    results = []
    for job in jobs:
        results.append(model.extract(job.description))
    return {"completed": len(results)}
```

Why it fails:

- all 20 calls start without a canary;
- request timeout/cancellation semantics are unclear;
- progress exists only in process memory;
- a crash may repeat calls;
- no stable Run identity exists;
- no distinction between reused and newly called outputs;
- failed evidence may disappear from the response;
- `completed=20` does not prove one coherent current cohort;
- it encourages treating API success as quality approval.

Failure scenario:

```text
Calls 1–3 produce structurally valid but obviously poor Requirements.
The endpoint continues Calls 4–20 anyway.
Call 12 times out.
The request is retried and repeats Calls 1–11.
The operator sees only the final HTTP error and cannot reconstruct paid work.
```

## 4. State-transition exercise

Fill the expected persistent result:

| Previous state | Current event | Persistent state | Attempt count change |
|---|---|---|---:|
| pending | budget exhausted | ? | ? |
| pending | provider call succeeds | ? | ? |
| pending | provider call fails | ? | ? |
| extracted | safe reuse | ? | ? |
| failed | budget exhausted | ? | ? |
| failed | later call succeeds | ? | ? |

Expected reasoning:

- no-attempt events do not increment attempts;
- actual calls increment attempts;
- persistent provenance should not be weakened by later invocation wording;
- prior attempted failure is preserved until a real later attempt resolves it.

## 5. Tests to study

Primary test file:

```text
services/backend/tests/test_requirement_acceptance_preparation.py
```

Study these proof categories:

1. Preflight avoids provider/repository construction.
2. Timestamp-only export changes do not change fingerprint.
3. Three-case canary produces three Traces and seventeen deferred cases.
4. Resume keeps the same Run and creates only seventeen new calls.
5. Third invocation creates no Trace and reuses the exact Batch.
6. Provider unavailable makes one attempted failure and defers the rest.
7. Later deferral does not erase a previous failed Trace.
8. Run API is read-only and produces stable 404.
9. Invalid limit is rejected before Import.
10. JD change creates new evidence and makes the old Batch stale.

Migration evidence:

```text
services/backend/tests/test_migrations.py
```

## 6. ADR to explain in an interview

```text
docs/decisions/0025-persistent-requirement-acceptance-runs-and-canary-control.md
```

Explain these decisions:

- why a persistent Run is not a replacement for Trace or Extraction;
- why dataset identity excludes export timestamp;
- why explicit live budget is mandatory;
- why no provider-start POST was added;
- why per-Case writes are preferable to one transaction around external calls;
- why concurrency/distributed leases were deferred.

## 7. Interview questions

1. How would you implement idempotency for a batch of LLM calls?
2. What is the difference between an idempotency key and a dataset fingerprint?
3. Why should external provider calls not run inside one long DB transaction?
4. How do you recover when side effect A committed but state update B did not?
5. What does “at least once with deterministic reuse” mean here?
6. Why does a failed provider call consume budget even when no Extraction is persisted?
7. How would you model `failed` versus `deferred`?
8. Why can a later no-op event not erase a prior real failure?
9. How do you distinguish current-command metrics from historical provenance?
10. Why is a read-only progress API safer than a synchronous execution endpoint?
11. What DB constraints protect one Run’s identity and 20 ordered Cases?
12. Where would you add a distributed lease if multiple workers were introduced?
13. How would you prevent two workers from executing the same pending Case?
14. Why does a completed engineering Run not prove model quality?
15. What evidence is required before downstream Match trusts JobRequirement?

## 8. Demo script (3–5 minutes)

### Scene 1 — Safe input inspection

Run:

```bash
.venv/bin/python -m scripts.prepare_requirement_acceptance \
  /path/to/formal-review.json \
  --preflight --json
```

Show:

- stable fingerprint;
- 20 selected cases;
- character summary;
- `dbWrites=0`;
- `providerCalls=0`.

### Scene 2 — Three-case canary

Run live provider with:

```bash
--reviewer will
--title "Real Requirement acceptance"
--max-new-extractions 3
--json
```

Show:

- one `runId`;
- three extracted cases;
- seventeen deferred cases;
- three Trace IDs;
- no Batch.

### Scene 3 — Read persisted progress

Call:

```http
GET /api/v1/requirement-acceptance-runs/{runId}
```

Show:

- Case statuses and attempt counts;
- Trace and Extraction IDs;
- no full JD duplicated in Run response;
- no POST execution operation in OpenAPI.

### Scene 4 — Resume

After manually checking canary output, rerun the same dataset/title/reviewer with another explicit limit.

Show:

- same Run ID;
- prior cases reused in current invocation;
- no duplicate Trace for prior cases;
- remaining calls only;
- one Batch after all 20 succeed.

### Scene 5 — Manual boundary

Open:

```text
/evals/requirements/manual
```

State clearly:

> The Agent prepared auditable evidence. I must personally compare each JD and Requirement and submit the human judgment.

## 9. What the learner must do next

1. Answer the prediction sheet.
2. Run Preflight on the accepted real dataset.
3. Choose a 1–3 case live canary budget and justify it.
4. For each canary case, record:
   - JD purpose;
   - extracted Requirements;
   - missing/unsupported facts;
   - importance errors;
   - Trace ID;
   - latency/tokens when available.
5. Decide whether to continue the same cohort.
6. Finish the remaining calls with explicit limits.
7. Manually review all 20 Batch cases.
8. Write a model-quality conclusion separate from the engineering conclusion.

## 10. Explicitly unverified

- no live API credential was available in the implementation environment;
- no real OpenAI call was made;
- no real token cost, latency or rate-limit behavior was measured;
- no 20-case human Review was completed;
- no acceptance threshold was approved;
- no concurrency test with two intentional workers was performed;
- no queue cancellation or lease recovery was implemented;
- Match remains blocked on real quality evidence.
