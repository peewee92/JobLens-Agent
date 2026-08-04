# P0-3B-3C｜Requirement Acceptance Run Control

Status: implemented and verified on 2026-08-04

## 1. Current real project feature

Safely run the 20 accepted real JDs through one live Requirement Extractor cohort without allowing an unmanaged command to spend 20 calls, lose partial progress, or hide what happened between invocations.

```text
formal Collector review dataset
→ zero-write / zero-call Preflight
→ explicit 1–3 case live canary
→ persist one Acceptance Run and 20 Case states
→ inspect Trace / structured output
→ resume the same Run with another explicit call limit
→ create one exact Review Batch only after all 20 are current
→ learner manually reviews all 20 cases
```

This slice controls execution evidence. It does not perform human judgments, approve the model, start Match, or claim live quality without a credential-backed run.

## 2. Learning goal

Use the real JobLens pipeline to master the minimum backend and Agent-engineering knowledge needed for managed LLM execution:

- Preflight versus execution;
- stable dataset identity versus export metadata;
- canary rollout and explicit budget limits;
- invocation result versus persistent historical truth;
- persistent state-machine transitions;
- at-least-once execution and recovery after a process crash;
- Trace, Extraction, Run Case and Review Batch boundaries;
- why a browser may read progress but must not trigger this long provider job;
- why the development Agent may automate execution controls but not human quality labels.

## 3. Risk assessment

### Business risk: high

An uncontrolled live run can:

- spend 20 model calls before the first result is inspected;
- repeat paid calls after a process failure;
- overwrite a previous failure with a later “not attempted” state;
- mix outputs from changed JDs or different model/prompt versions;
- create a Batch from fewer than 20 current results;
- expose a polished progress page that is not backed by database records;
- let fixture evidence appear equivalent to live evidence.

The highest-risk failure is a system reporting “20/20 ready” even though some outputs were never called, were generated from old JDs, or belong to another cohort.

### Learning risk: high

The learner may skip core understanding by asking the Agent to:

- choose the canary size without understanding its purpose;
- treat a successful HTTP 200 as evidence of model quality;
- confuse an invocation-level `reused` result with the Run’s historical origin;
- ignore failed Trace evidence when continuing a run;
- delegate accepted/rejected decisions and issue labels;
- move to Match before explaining why Requirement facts are trustworthy.

## 4. Core mechanisms reserved for the learner

Before studying the implementation, the learner should write predictions for:

1. Should `generatedAt` be part of the stable dataset identity? Why?
2. Does a reused Extraction consume the current invocation’s canary budget?
3. If the process dies after an Extraction commit but before the Run Case update, what should a rerun do?
4. If a Case was originally extracted by this Run, should a later invocation rewrite its persistent status to `reused`?
5. If a prior failed Case is deferred because the current budget is exhausted, which evidence should remain in the database?
6. Why must live OpenAI execution require an explicit call limit?
7. Why may HTTP expose `GET Run`, but not `POST Start Run` in this slice?
8. What facts prove engineering completion but do not prove model quality?

The learner must personally:

- choose the first live canary size, normally 1–3;
- inspect the canary JDs, Requirements and Traces;
- explain whether errors are case-specific or provider-wide;
- manually accept/reject all 20 real Review cases;
- select issue codes and write notes;
- decide whether the observed quality is sufficient to begin Match.

## 5. Peripheral work completed by the development Agent

- formal dataset Preflight and stable fingerprint;
- persistent Run and Run Case schema;
- migration, Repository and Unit of Work;
- explicit new-call budget enforcement;
- resumable state transitions;
- failure/Trace preservation;
- read-only Run API;
- CLI options and machine-readable output;
- tests, ADR, API contract, learning record and Demo outline;
- independent Diff review and regression execution.

## 6. Facts, inference, assumptions and unknowns

### Confirmed facts

- The Collector formal review gate can provide exactly 20 independent `full_jd` samples.
- Job Import, immutable Requirement Extraction, Trace and version-frozen manual Review Batch already exist.
- P0-3B-3B already supports safe same-input/same-cohort Extraction reuse.
- Before this slice, one CLI invocation could still make all 20 live calls and the orchestration itself had no persistent Run record.
- No live Provider environment variables are configured in the current development shell.
- No 20-case credential-backed human quality decision has been completed.

### Inference

- Live quality work should begin with a small canary rather than all 20 calls.
- A persistent Run should survive shell/process restarts and make every Case inspectable.
- The stable identity should describe evidence, not the time a file was exported.
- Run history and current invocation results are different facts and should not overwrite each other.
- A read-only API improves observability without making a browser request own a long provider lifecycle.

### Assumptions

- MVP remains local and single-user.
- SQLite remains the active database.
- Only one operator intentionally runs a given dataset/reviewer/cohort at a time.
- CLI remains the execution boundary; no queue or distributed lease is added.
- Reviewer identity remains free text.
- An explicit `--max-new-extractions` value is the current cost-control mechanism.

### Unknowns

- Actual live model accuracy, latency and token cost.
- Provider rate limits and transient-error behavior.
- Whether one 1–3 case canary is representative enough to continue.
- Whether production needs queues, cancellation, leases or distributed locking.
- The final acceptance threshold for entering Match.
- Reviewer authentication and RBAC requirements.

## 7. User value hypothesis

A JobLens operator can safely inspect a few real Requirement outputs before committing to the remaining calls, resume after failures without duplicate paid work, and prove every result through a Run Case, Trace, Extraction and frozen Review Batch.

Observable value:

```text
preflight data
→ see stable fingerprint and input size
→ run 1–3 canary calls
→ query exact persisted progress
→ inspect Trace/output
→ resume with another explicit budget
→ receive Batch only at 20 current results
```

## 8. Completion standards

### Engineering completion

| Standard | Required evidence |
|---|---|
| Preflight makes no DB writes or provider construction | CLI test + zero Import/Job/Trace/Run rows |
| re-export time does not split one evidence set into two Runs | stable fingerprint test |
| changed source identity or JD changes the fingerprint | fingerprint unit assertions |
| live OpenAI cannot run without an explicit call limit | CLI guard test + exit 2 behavior |
| canary counts only new calls | 3 new calls create 3 Traces; reused cases do not consume limit |
| one execution has a persistent Run and 20 Cases | DB row counts + Run API response |
| each attempted call records attempt count and Trace | Case DB/API assertions |
| limit-exhausted cases are deferred and uncalled | `deferred` rows + no Trace/Extraction |
| prior failure evidence survives a later deferred invocation | failure-preservation test |
| Run history preserves original extracted/reused provenance | persistent status test |
| resume uses the same Run | same Run ID + updated latest Import/source timestamp |
| process-safe reuse prevents duplicate provider work | same-input Extraction lookup + rerun tests |
| incomplete work creates no Review Batch | Batch row count zero |
| 20 current same-cohort cases create one Batch | DB/API/Batch assertions |
| repeated completed invocation reuses the Batch | unchanged Batch count and ID |
| browser can read but not start a long run | GET endpoint + OpenAPI has no POST |
| missing Run produces stable 404 | API test |
| schema upgrade/downgrade is reversible | Alembic migration test |
| no regression | full Backend/Web/Collector tests, build and drift check |

### Learning completion

The learner can explain without reading code:

- stable fingerprint versus `generatedAt`;
- why reuse does not consume new-call budget;
- invocation state versus historical Run state;
- `pending / deferred / failed / extracted / reused` semantics;
- how rerun recovers an Extraction committed before a Case update;
- why failure Trace must not be overwritten by a later deferred state;
- why the live CLI requires explicit budget;
- why engineering success is not model-quality approval.

Evidence: written answers in the learning record and explanation of three real canary cases.

### Portfolio completion

Repository contains:

- persistent Run/Case schema and migration;
- explicit state-transition and budget tests;
- read-only progress API;
- safe live CLI examples;
- ADR describing identity, provenance and execution boundaries;
- failure case showing preserved Trace evidence;
- 3–5 minute Demo script;
- explicit list of unverified live-provider facts.

### User-value completion

A user can observe:

```text
CLI Preflight JSON
→ CLI canary summary with runId
→ GET Run API with 20 cases and Trace IDs
→ resumed Run with no duplicate calls
→ one Review Batch ID only when ready
→ existing manual Review UI
```

## 9. Minimal knowledge for this slice

### 9.1 Stable evidence identity

The Run fingerprint contains stable evidence fields:

```text
dataset version
ordered URL / optional sourceJobId
title
company
sourceVersion
descriptionHash
```

`generatedAt` is source metadata and may change when the same evidence is re-exported. It is stored, but does not create a new identity.

### 9.2 Two kinds of status

Current invocation:

```text
reused / extracted / failed / deferred
```

Persistent Run history:

- If this Run originally created an Extraction, later invocations do not rewrite it to `reused`.
- A failed attempt keeps its error and Trace until a later real successful attempt replaces it.
- A budget-deferred invocation does not erase prior attempted evidence.

### 9.3 Canary budget

```text
maxNewExtractions = number of actual new provider calls allowed now
```

Safe reuse costs zero budget. A failed provider attempt consumes one budget slot because a real request occurred.

### 9.4 Recovery window

The provider Workflow commits Trace and Extraction before the Run Case update. If the process crashes in between, the next invocation finds the current same-cohort Extraction, reuses it and repairs the Run Case without another provider call.

## 10. Common wrong implementation

```python
for job in jobs:
    result = provider.extract(job.description)
    in_memory_results.append(result)
write_progress_json(in_memory_results)
```

Why it fails:

- no durable Run exists during execution;
- a crash loses orchestration state;
- rerun may repeat paid calls;
- progress JSON is not linked to DB Jobs, Traces or Extractions;
- there is no explicit call limit;
- failures can be overwritten by a later summary;
- the browser or operator cannot reconstruct exact evidence.

Failure example:

```text
call 1–7 succeed
process exits before writing progress file
rerun calls 1–20 again
case 12 fails
summary marks the remaining cases “not attempted”
previous failure Trace disappears from operator view
```

The controlled Run instead reuses the seven persisted Extractions, retains attempted failures and calls only the explicitly allowed remaining cases.

## 11. Tickets (1–3 hours each)

### T0 — Risk, prediction and state truth table

- define stable identity;
- define invocation versus persistent status;
- define canary and failure rules;
- freeze completion evidence.

### T1 — Run/Case schema and migration

- add persistent execution tables;
- exact 20-case constraint;
- dataset/cohort identity uniqueness;
- Trace/Extraction/Import/Batch foreign keys;
- upgrade/downgrade tests.

### T2 — Preflight

- full formal-dataset validation;
- stable fingerprint;
- input size summary;
- zero provider/repository construction path.

### T3 — Controlled orchestration

- explicit new-call budget;
- reuse without budget consumption;
- deferred cases;
- provider-wide unavailable behavior;
- persistent per-case updates.

### T4 — Resume and provenance

- reuse same Run;
- preserve original extracted provenance;
- preserve prior failure evidence;
- update latest import/source metadata;
- attach one exact Batch.

### T5 — Read-only API

- GET Run detail;
- stable 404;
- no provider execution endpoint;
- OpenAPI guard.

### T6 — Verification and portfolio artifacts

- full regression;
- migration round trip;
- ADR, contracts, learning record, interview questions and Demo.

### T7 — Live learning execution

Reserved for the learner:

- run Preflight on the accepted dataset;
- choose and run 1–3 live canary cases;
- inspect three cases and Traces;
- decide whether to continue;
- complete all 20 manual judgments.

## 12. Scope guard

Do not add:

- automatic Review decisions or issue labels;
- automatic model approval;
- Match, Eligibility, Ranking or Skill Gap;
- queue workers, Redis or Celery;
- browser-triggered provider execution;
- unbounded retry/backoff;
- distributed locking or multi-user scheduling;
- reviewer authentication/RBAC;
- multi-agent architecture;
- automated job application or recruiter messaging.
