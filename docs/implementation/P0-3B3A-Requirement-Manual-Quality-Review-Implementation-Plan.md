# P0-3B-3A｜Requirement Manual Quality Review Batch

Status: planned and implementation in progress on 2026-08-03

## Current real project feature

Create a human quality-review batch from persisted JobRequirement Extraction versions, inspect each exact extraction against its original Job description, record one immutable judgment per case, and derive an auditable batch summary.

```text
Latest persisted JobRequirement Extractions
→ select 1–20 exact extraction versions
→ freeze one coherent provider/model/prompt cohort
→ inspect JD + extracted Requirements + Trace ID
→ accept or reject each case once
→ aggregate issue codes and completion state
→ identify whether the batch is valid 20-job release evidence
```

This slice gathers human evidence. It does **not** automatically approve a model, mutate the accepted Requirement Eval baseline, or begin Match.

## Learning goal

Use one real product slice to master the minimum backend and Agent-engineering knowledge for human model-quality evidence:

- snapshot consistency: why a batch freezes `extractionId`, not only `jobId`;
- cohort consistency: why one batch cannot mix provider/model/prompt versions;
- append-only human labels and database uniqueness;
- derived aggregate state instead of mutable counters;
- stale-evidence detection when a newer extraction appears;
- difference between practice evidence and release evidence;
- Server/Client boundaries for a review workflow;
- proving completion with DB rows, API responses, UI behavior and an end-to-end smoke.

## Business risk

Risk level: **high**.

A misleading manual review process can produce false confidence even when the underlying extractor is poor. Major risks:

- reviewing a different extraction version from the one later promoted;
- mixing several model/prompt versions in one acceptance rate;
- selecting only easy or similar jobs;
- allowing reviewers to overwrite earlier judgments silently;
- treating a 3-case practice batch as production evidence;
- ignoring that a newer extraction made the batch stale;
- auto-generating human decisions with an Agent.

The most dangerous outcome is a polished dashboard that claims “95% quality” without a coherent, current, manually reviewed sample.

## Learning risk

Risk level: **high**.

The learner may skip the core ability by letting the Agent:

- choose all issue labels;
- decide accepted/rejected cases;
- infer missing requirements without personally comparing the JD;
- accept a model based only on aggregate metrics;
- treat seeded smoke data as real human review.

The Agent may implement the review system, but the learner must perform real case judgments later.

## Core mechanisms the learner should predict first

Before reading the implementation Diff, answer:

1. Why must a case store `extractionId` as well as `jobId`?
2. If a new extraction is created after the batch, should old reviews disappear?
3. Why should one batch reject mixed model or prompt versions?
4. Why is `reviewedCount` better derived than incremented on the Batch row?
5. Can an accepted case contain issue codes?
6. Why must a rejected case contain at least one issue code?
7. Why may a 5-job batch exist but never count as formal release evidence?
8. Why can UI button rules not replace backend validation?
9. Why must the Agent not fill human review decisions?
10. What sampling bias remains even after exactly 20 cases are reviewed?

## Core work reserved for the learner

The learner must personally perform or explain:

- classify each real case as accepted/rejected;
- identify missing, unsupported or wrongly classified Requirements;
- explain why the frozen extraction version is the evidence unit;
- explain batch cohort and stale-evidence rules;
- choose a representative 20-job sample later;
- decide whether observed issue distribution is acceptable for release.

## Peripheral work the development Agent may complete

- ORM/Alembic boilerplate;
- Repository and Unit of Work adapters;
- API/Pydantic mapping;
- Web forms, checkboxes and route handlers;
- deterministic aggregate calculations;
- test fixtures and smoke seed data;
- ADR, API contract and learning-record structure.

## Facts, inference, assumptions and unknowns

### Confirmed facts

- Local development DB currently contains zero Jobs, Requirement Extractions, Eval Runs or Reviews.
- JobRequirement Extraction versions are immutable and retain provider/model/prompt/Trace provenance.
- Requirement Eval automatic Gate and human Accepted Baseline governance already exist.
- No credential-backed OpenAI Requirement quality run has been verified in this session.
- No 20-real-job human review has been completed.

### Inference

- The next trustworthy step is to build the manual evidence workflow before Match.
- The exact extraction version is the correct review unit because Job IDs may have several immutable extraction versions.
- A batch must be a coherent model/prompt cohort for its summary to be interpretable.
- Review history should remain even if later extractions make it stale.

### Assumptions

- MVP remains local and single-user; reviewer name is free text.
- SQLite remains the database.
- A batch may contain 1–20 cases so the learner can practice incrementally.
- Formal release evidence requires exactly 20 cases, all reviewed, all still current, and provider not equal to `fixture`.
- Case decisions are immutable; correcting a mistake requires a new batch.

### Unknowns

- The future real-job sample composition.
- Real OpenAI Provider quality, cost and latency.
- Whether 20 cases are statistically representative across job families.
- Reviewer authentication, RBAC and identity verification.
- The final quality threshold for promoting a model.
- Whether future teams need review amendment/versioning rather than immutable single decisions.

## User value hypothesis

Before JobLens tells a user which job is worth applying to, the operator needs evidence that the Requirement facts are reliable on real jobs. A version-frozen review batch makes the evidence inspectable and prevents later model changes from silently rewriting what was reviewed.

Observable value:

- reviewers know exactly which extraction version they judged;
- original JD, Requirements and Trace ID are visible together;
- issue types are structured and aggregatable;
- a small practice batch is visibly different from valid 20-job evidence;
- a newer extraction makes the batch visibly stale rather than erasing history.

## Completion standards

### Engineering completion

| Standard | Required evidence |
|---|---|
| batch freezes exact versions | DB FK to extraction + API response + immutable case test |
| batch rejects duplicate or missing extraction IDs | Application tests + 422 API |
| one batch is one provider/model/prompt cohort | policy test + stable 422 |
| one immutable judgment per case | DB unique constraint + duplicate test + 409 API |
| accepted case has no issue codes | validation test + 422 API |
| rejected case has issue code(s) | validation test + 422 API |
| aggregate counts are derived | repository tests + detail API response |
| newer extraction marks old case stale | persistence test + API/UI behavior |
| formal evidence requires 20 complete current non-Fixture cases | summary tests + UI label |
| reviewer sees JD, Requirements and Trace | detail API + SSR page + smoke |
| browser writes only through same-origin proxy | architecture test |
| no half-written batch/review | forced persistence failure tests |
| no regression | full Backend + Web tests, typecheck and build |

### Learning completion

The learner can explain without code:

- snapshot vs current state;
- cohort consistency;
- why aggregate counters are derived;
- immutable judgment trade-offs;
- practice batch vs release evidence;
- stale-batch semantics;
- remaining sampling bias;
- why the Agent cannot supply human labels.

Evidence: written answers in the learning record and final review questions.

### Portfolio completion

Repository contains:

- ADR for version-frozen manual quality evidence;
- migration and architecture diagrams/text;
- API contract and curl examples;
- allowed/forbidden transition tests;
- Web creation/review workflow;
- real-process smoke using explicitly labeled seeded data;
- Demo script and unverified-items section.

### User-value completion

A reviewer can complete:

```text
open candidate extractions
→ select a coherent batch
→ create immutable batch snapshot
→ open one case
→ compare JD and extracted Requirements
→ submit accepted/rejected with issue codes
→ see batch progress and issue summary
→ see practice/current/stale/formal-evidence state
```

Every step must correspond to an API response, DB record, Trace reference or visible UI behavior.

## Minimal knowledge for this slice

### Snapshot identity

```text
jobId
  identifies the long-lived Job

extractionId
  identifies the exact Requirement interpretation being reviewed
```

A review that stores only `jobId` becomes ambiguous after re-extraction.

### Cohort consistency

All cases in a batch must share:

```text
provider
model
extractorVersion
promptVersion
```

Otherwise aggregate quality mixes different systems.

### Derived state

Do not maintain mutable counters such as `reviewed_count += 1`. Derive them from immutable Case Review rows. This prevents drift after retries or transaction failures.

### Formal evidence rule

```text
formalEvidenceEligible =
  sampleSize == 20
  AND reviewedCount == 20
  AND staleCaseCount == 0
  AND provider != fixture
```

This means the batch is structurally valid evidence, not that model quality passed.

## Common wrong implementation

```python
batch = ReviewBatch(job_ids=request.job_ids)
batch.acceptance_rate = model.score(batch.jobs)
```

Why it fails:

- `jobId` does not freeze the reviewed extraction;
- the Agent replaces human judgment;
- mixed model versions can enter one batch;
- mutable rates can drift from case records;
- small or biased samples look official;
- no Trace or issue evidence supports the number.

Failure case:

The user reviews 20 jobs. Ten are re-extracted with a new prompt before release. The system stores only Job IDs and still displays “18/20 accepted,” even though half of the promoted extraction outputs were never reviewed.

## Tickets (1–3 hours each)

### T0 — Contract and truth table

- freeze batch/case/review models;
- define issue-code vocabulary;
- define practice/formal/stale semantics;
- write prediction questions and completion standards.

### T1 — Schema and persistence

- add batches, batch cases and immutable case reviews;
- exact extraction/job foreign keys;
- unique case index and one-review-per-case constraint;
- migration upgrade/downgrade and metadata checks.

### T2 — Application policies

- list latest extraction candidates;
- create coherent batch from 1–20 extraction IDs;
- validate accepted/rejected issue rules;
- derive progress, issue counts, stale count and evidence eligibility;
- transaction-failure and concurrency tests.

### T3 — Backend API

- GET candidates;
- POST/GET batch list and detail;
- POST immutable case review;
- stable 404/409/422 errors;
- no provider execution in HTTP request.

### T4 — Web workflow

- manual review batch list/create screen;
- candidate selection with cohort metadata;
- batch detail with JD, Requirements, Trace and case form;
- same-origin write routes;
- policy/helper and architecture tests.

### T5 — Runtime evidence

- seed explicitly fake practice data under `APP_ENV=test`;
- start real FastAPI and production Next;
- create batch, review cases and verify summary/stale/formal labels;
- clean temporary processes and DB.

### T6 — Portfolio and learning artifacts

- ADR;
- API contract;
- learning record;
- interview questions;
- Demo script;
- roadmap/README update;
- independent Diff review and explicit unknowns.

## Scope guard

Do not add:

- actual OpenAI credentials or provider calls;
- Agent-generated review decisions;
- automatic baseline promotion;
- Match, Eligibility or Ranking;
- batch scheduling or queues;
- reviewer authentication/RBAC;
- statistical confidence claims;
- editable Review history;
- more than 20 cases per batch;
- multi-agent architecture.
