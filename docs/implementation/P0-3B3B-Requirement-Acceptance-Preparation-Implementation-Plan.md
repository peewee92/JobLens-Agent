# P0-3B-3B｜Real Requirement Acceptance Preparation

Status: implemented and verified on 2026-08-04

## Current real project feature

Turn one Collector `requirement_manual_quality_review` dataset into a version-frozen Requirement manual-review batch without silently skipping failed jobs or creating duplicate model evidence.

```text
Collector ready dataset (20 selected JDs)
→ validate formal input gate
→ import/update the exact 20 Jobs
→ resolve persisted Job IDs
→ reuse a current same-cohort Extraction when safe
→ otherwise run one Requirement Extraction per Job
→ keep successful partial progress when another Job fails
→ create or reuse one exact 20-case Review Batch
→ learner manually accepts/rejects every case in Web UI
```

This slice prepares evidence. It does not make human review decisions, approve a model, start Match, or claim that a `ready` Collector dataset proves model quality.

## Learning goal

Master the minimum backend and Agent-engineering mechanisms needed to turn real inputs into auditable human-review work:

- application orchestration versus domain capability;
- idempotent reuse based on input hash and full cohort identity;
- partial failure and resumable progress;
- immutable Extraction versions and stale evidence;
- why batch creation happens only after all 20 latest Extractions exist;
- why a CLI may invoke a slow provider while an HTTP request should not;
- proving work through Import rows, Trace rows, Extraction rows, Batch rows and UI read models.

## Risk assessment

### Business risk: high

A broken preparation flow can:

- review outputs generated from a different JD than the imported source;
- mix provider/model/prompt versions in one acceptance rate;
- hide failed cases and create a biased 19-case batch;
- rerun all 20 model calls and waste cost;
- create duplicate batches that look like separate evidence;
- mark fixture output as production evidence.

### Learning risk: high

The learner may skip the core skill by asking the Agent to:

- decide which extracted Requirements are correct;
- label all issue codes;
- explain only the happy path while ignoring partial failures;
- treat successful CLI output as quality approval;
- memorize code without understanding input-hash and cohort reuse rules.

## Core mechanisms the learner must predict first

Before reading the Diff, write your prediction for these questions:

1. Why is `source URL` not enough to decide whether an old Extraction can be reused?
2. Which four cohort fields must match before reuse?
3. When Job 12 fails after Jobs 1–11 succeed, should the first 11 Extractions roll back?
4. Why must the Review Batch not be created with only 19 successful cases?
5. Why does a second run reuse successful Extractions instead of calling the model again?
6. When should a new Extraction make an old Review Batch stale?
7. Why is this workflow a CLI/application orchestration rather than a long synchronous browser request?
8. Why can a fixture batch validate engineering but never prove model quality?

## Core work reserved for the learner

The learner must personally:

- answer the prediction questions before studying the implementation;
- inspect at least three real JD/Extraction pairs end to end;
- manually accept or reject all 20 real cases;
- select issue codes and write review notes without Agent-generated judgments;
- explain the reuse key and partial-failure policy;
- decide whether the observed acceptance rate and issue distribution are acceptable for release.

## Peripheral work the development Agent may complete

- dataset envelope validation;
- import/extraction/batch orchestration code;
- deterministic reuse checks;
- CLI plumbing and formatted summary;
- test fixtures, failure injection and database assertions;
- ADR, API/CLI documentation, learning record and Demo checklist;
- independent Diff review and regression execution.

## Facts, inference, assumptions and unknowns

### Confirmed facts

- Collector v1.4.5 produced 20 accepted independent JD samples and passed formal input validation.
- Job import, immutable Requirement Extraction, Trace, version-frozen manual Review Batch and Web review UI already exist.
- Extraction currently operates one Job at a time.
- Batch creation already rejects stale or mixed-cohort Extractions.
- No credential-backed 20-job live Requirement review has been completed.

### Inference

- The missing product slice is orchestration from accepted Collector data to a review-ready Batch.
- Successful per-Job Extractions should remain persisted when a later Job fails so a rerun can resume.
- Reuse is safe only when the persisted JD hash and complete extraction cohort match.
- Exact duplicate batches should be reused rather than created again.

### Assumptions

- The workflow runs locally and synchronously from a CLI.
- A formal input dataset contains exactly 20 selected Jobs.
- The source dataset is trusted only after deterministic envelope and per-job checks pass.
- Importing the same Jobs again is expected to update source evidence without duplicating Jobs.
- The reviewer identity remains a free-text local MVP field.

### Unknowns

- Live Provider credentials and network availability.
- Live model quality, latency, token cost and rate limits across these 20 JDs.
- Whether production later needs a queue, cancellation, backoff or distributed lease.
- The final release threshold after human review.
- Whether future batches need stratified sampling beyond Collector near-duplicate removal.

## User value hypothesis

A reviewer should be able to turn one accepted Collector export into a trustworthy review queue with one command, rerun safely after a provider failure, and know exactly which Job, Trace and Extraction version each judgment refers to.

Observable value:

- no manual copying of 20 Job IDs;
- failed cases are visible rather than silently omitted;
- reruns avoid duplicate model calls when evidence is unchanged;
- the resulting Batch appears in the existing Web review page;
- every case links to one frozen Extraction and Trace.

## Completion standards

### Engineering completion

| Standard | Required evidence |
|---|---|
| reject non-ready, malformed or selected-near-duplicate datasets before import | validation tests; zero JobImport rows |
| import exactly the selected 20 jobs | Import API/read model and DB row counts |
| map each dataset row to one unique persisted Job | import-item assertions; source-identity collision test; zero Extraction rows |
| reuse only same-input same-cohort latest Extraction | application test and unchanged Trace/Extraction counts on rerun |
| changed persisted JD immediately invalidates old review evidence | candidate list exclusion + Batch stale API/read-model test before replacement Extraction |
| persist successful partial progress | injected case failure; DB contains prior Extraction/Trace rows |
| fail fast on provider-wide unavailability | one failed Trace; remaining cases not attempted; zero Batch rows |
| do not create incomplete batch | failure test; zero Batch rows |
| rerun resumes and creates one 20-case batch | second-run test; 19 reused + 1 extracted + one Batch |
| avoid exact duplicate batch creation | third-run test; same Batch ID and unchanged Batch count |
| fixture cannot be confused with formal evidence | CLI guard and Batch summary `formalEvidenceEligible=false` |
| current Batch is visible to existing Web UI | repository/API response and Web route smoke |
| no hidden provider call in browser request | CLI-only architecture test/documented boundary |
| no regression | full Backend/Web/Collector tests, typecheck, build, migration check |

### Learning completion

The learner can explain without reading code:

- input identity versus source URL identity;
- full cohort identity;
- why partial progress is committed per Job;
- why incomplete batches are forbidden;
- reuse versus re-extraction;
- immutable history and stale Batch semantics;
- fixture engineering evidence versus live quality evidence;
- why manual labels cannot be delegated to the Agent.

### Portfolio completion

Repository contains:

- this implementation plan;
- an ADR for resumable acceptance preparation;
- application orchestration and CLI;
- happy-path, idempotency and partial-failure tests;
- runtime evidence using an explicitly labeled fixture run;
- learning record with prediction answers left for the learner;
- interview questions and a 3–5 minute Demo script;
- explicit unverified live-provider items.

### User-value completion

```text
run one command with an accepted Collector dataset
→ see import/extracted/reused/failed counts
→ receive one Batch ID only when all 20 are ready
→ open the existing manual-review UI
→ inspect JD + Requirements + Trace
→ personally submit immutable judgments
```

## Minimal knowledge for this slice

### Safe Extraction reuse key

```text
persisted description SHA-256
+ provider
+ model
+ extractorVersion
+ promptVersion
+ latest Extraction for that Job
```

A matching URL alone is insufficient because the JD or model configuration may have changed.

### Partial failure policy

Each Extraction and Trace is its own completed evidence unit. If case 12 fails, cases 1–11 remain valid and reusable. The Review Batch is the all-or-nothing release-preparation boundary and is created only after all 20 latest Extractions exist.

### Common wrong implementation

```python
for job in jobs:
    extraction_ids.append(extract(job))
create_batch(extraction_ids)
```

Why it fails:

- every rerun spends money on all Jobs;
- no input/cohort reuse check;
- a swallowed exception can create a biased 19-case Batch;
- duplicate runs create duplicate Batches;
- no structured summary explains what was reused or failed.

Failure case:

The provider times out on Job 12. The first run already paid for Jobs 1–11. A naive second run calls all 20 again, then creates a new Batch even though an identical Batch already exists. Cost doubles and reviewers cannot tell which Batch is authoritative.

## Tickets (1–3 hours each)

### T0 — Contract and prediction sheet

- freeze dataset requirements, reuse truth table and failure policy;
- define completion evidence and scope guard.

### T1 — Dataset validator and result models

- validate formal Collector envelope, content hashes and exactly 20 independent eligible Jobs;
- define extracted/reused/failed case results.

### T2 — Resumable application orchestration

- import and resolve 20 persisted Job IDs;
- compare description hash and complete cohort;
- extract only missing/stale cases;
- retain successful partial progress.

### T3 — Batch idempotency

- create only after 20 successes;
- reuse an exact existing Batch instead of duplicating it.

### T4 — CLI

- read JSON, enforce fixture safety, compose repositories/workflows;
- print Import, Extraction, Trace and Batch evidence.

### T5 — Tests and runtime smoke

- malformed input;
- successful 20-case fixture path;
- second-run reuse;
- injected failure and resume;
- duplicate Batch prevention;
- local fixture smoke against a temporary SQLite database.

### T6 — Portfolio and learning artifacts

- ADR;
- learning record;
- interview questions;
- Demo script;
- Diff review and unverified items.

## Scope guard

Do not add:

- Match, Eligibility, Ranking, Skill Gap or resume generation;
- automatic human review decisions;
- automatic model approval or accepted baseline promotion;
- queue workers, Redis, Celery or distributed scheduling;
- browser-triggered long-running provider execution;
- retry storms or unbounded automatic retries;
- reviewer authentication/RBAC;
- multi-agent architecture;
- automated job application or recruiter messaging.
