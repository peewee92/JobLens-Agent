# P0-3B-1｜Requirement Eval Run Persistence and Quality Gate

Status: implemented and verified on 2026-08-03

## Current real product slice

```text
Versioned Requirement Eval dataset
→ real Requirement Workflow
→ one Trace per case
→ deterministic metrics and Gate
→ immutable Eval Run + Case Results
→ optional baseline comparison
→ read-only API for quality evidence
```

This slice stops before Requirement human acceptance, Match, Ranking, Skill Gap, Agent orchestration, batch scheduling or automatic release.

## Learning target for this slice

### Backend

- FastAPI Router → Application Use Case → Repository Port → SQLAlchemy Adapter;
- Unit of Work and transaction ownership;
- immutable run/case persistence;
- Alembic schema evolution and database constraints;
- read model and API response separation;
- baseline comparison without mutating historical results.

### Agent engineering

- why an Agent/LLM output cannot certify its own correctness;
- why Fixture Eval proves pipeline repeatability but not live model quality;
- deterministic Gate vs human review;
- Eval Case → Trace linkage for failure reproduction;
- why downstream Match must wait for evidence-backed Requirement quality.

## Facts, inferences, assumptions and unknowns

### Confirmed facts

- Phase 3A already persists versioned JobRequirement Extraction Runs and Requirements.
- The Requirement Eval dataset contains 10 cases and the fixture provider currently passes all 10.
- Each Eval case already produces a Trace Run ID.
- Requirement Eval currently returns an in-memory report and the CLI only prints it.
- There is no Requirement Eval Run table or read API.
- Profile Eval already has an immutable Run/Case persistence pattern that can be reused without merging the two domains.

### Inferences

- Match should not begin until a live Requirement provider can produce inspectable, comparable Eval evidence.
- Persisting Eval runs is the smallest useful prerequisite for later human review and accepted baselines.
- Requirement Eval should remain a separate domain model because its metrics and failure diagnostics differ from Profile Eval.

### Assumptions

- SQLite remains the MVP database.
- The current single-user local environment does not require reviewer identity/authentication in this slice.
- `mode=fixture` is derived from provider `fixture`; all non-fixture allowed providers are treated as `live`.
- A live run is `releaseEligible` only when its deterministic Gate passes; this does not mean human-approved.

### Unknowns / explicitly not claimed

- Real OpenAI Requirement extraction quality, latency and cost.
- Whether the current 10-case dataset represents the target job market sufficiently.
- Whether the current thresholds are the correct production release thresholds.
- Whether normalization aliases such as React.js → React are adequate across all roles.
- Whether a live run should later require 20 real-job human review before acceptance.

## Risk assessment

### Business risk: high

Bad Requirement facts will contaminate Eligibility, Match, Ranking, Gap and Resume guidance. A false `must_have` can incorrectly block a job; a missing constraint can create misleading recommendations.

### Learning risk: high

The main failure mode is copying the Profile Eval implementation mechanically without understanding:

- what belongs in a domain-specific Eval record;
- where the transaction begins and ends;
- why Trace is separate from Eval persistence;
- why fixture success cannot set live release eligibility;
- why baseline comparison is derived, not persisted as mutable truth.

## Human-first core mechanisms

Before reading the completed implementation, the learner should handwrite or predict:

1. the truth table for `mode × gatePassed → releaseEligible`;
2. the transaction boundary for running 10 LLM cases and persisting one Eval Run;
3. whether a failed persistence transaction should delete already-written Trace rows, and why;
4. the fields required to reproduce and compare an Eval Run six months later;
5. why a numeric quality metric is not itself a user-facing probability.

These are the core mechanisms. The Agent may implement repetitive schemas, adapters, API mappings, exports and documentation, but the learner must be able to reconstruct and defend the five decisions above.

## Engineering completion standard

| Standard | Required evidence |
|---|---|
| one immutable Eval Run is stored | database rows in `requirement_eval_runs` and `requirement_eval_case_results` |
| every case remains traceable | API response contains each `traceRunId`; FK permits Trace retention semantics |
| Fixture cannot qualify live release | test + DB check constraint + API field `releaseEligible=false` |
| live Gate pass can become review-eligible | unit test for `mode=live`, `gatePassed=true`, `releaseEligible=true` |
| baseline comparison is reproducible | second Run references `baselineRunId`; detail API returns metric deltas |
| invalid baseline is rejected | use-case/CLI test with stable not-found error |
| run history is inspectable | `GET /api/v1/requirement-evals` and `GET /api/v1/requirement-evals/{id}` |
| failed cases explain failure | case result stores missing requirements, wrong importance, forbidden capabilities and error |
| schema can upgrade and downgrade | Alembic migration test and `alembic check` |
| existing behavior is not regressed | full backend test suite |

## Learning completion standard

The learner can explain, without reading the code:

- why provider execution is outside the Eval database transaction;
- why Trace writes survive even if final Eval persistence fails;
- why Fixture and Live are separate modes;
- how the Gate metrics are calculated and what each misses;
- why `baselineRunId` points to an immutable historical Run;
- why human review remains a separate next slice.

Evidence: oral/written answers to the review questions in the learning record.

## Portfolio completion standard

The repository and demo show:

- an actual 10-case Eval Run stored in SQLite;
- a list/detail API response with quality metrics and Trace IDs;
- a degraded extractor failing with explainable per-case evidence;
- a second run compared against a baseline;
- a clear warning that Fixture success is not live model validation;
- architecture and ADR explaining the release boundary.

## User value hypothesis

A persisted, comparable Requirement quality record prevents JobLens from silently promoting a weak model/prompt into Match. The immediate user value is indirect but critical: later job recommendations can be traced to a Requirement extractor version whose failures were measured rather than assumed.

## Minimal knowledge only

This slice requires only:

- Repository and Unit of Work roles;
- SQLAlchemy parent/child persistence;
- Alembic upgrade/downgrade;
- immutable run records;
- deterministic Eval metrics and baseline deltas;
- FastAPI dependency injection and response models.

It does not require LangChain, multi-agent design, vector search, background queues, cloud deployment or model fine-tuning.

## Common wrong implementation

```python
report = run_requirement_eval(...)
if report.gate_passed:
    settings.requirement_model_is_safe = True
```

Why it fails:

- a Fixture Run can set a production safety flag;
- the result is mutable global state rather than an immutable record;
- no case-level failure or Trace can be inspected;
- changing the dataset or thresholds loses provenance;
- there is no human review boundary;
- one lucky run can silently change downstream behavior.

## Failure case to preserve

A degraded extractor returns only the first Requirement from each JD. The Workflow succeeds and writes Trace, but capability recall drops below threshold. The Eval Run must persist as failed with per-case missing Requirement labels; it must not become release-eligible.

## Tickets (each 1–3 hours)

### T1 — Contract and application model

- define Requirement Eval Run/Case read-write models;
- define query repository and Unit of Work ports;
- define mode and stable errors;
- add run/list/get use cases.

### T2 — Database and migration

- add immutable run/case ORM models;
- add metric, mode and release eligibility constraints;
- add baseline self-reference and Trace linkage;
- add Alembic upgrade/downgrade.

### T3 — Runner persistence and comparison

- wrap existing evaluator in `RunRequirementEvalUseCase`;
- map case diagnostics into persisted records;
- compute `releaseEligible` from mode + Gate only;
- derive baseline metric deltas on read.

### T4 — API and CLI

- add list/detail read endpoints;
- add dependency wiring and stable 404 mapping;
- update CLI to persist and print Eval Run ID;
- support explicit baseline Run ID.

### T5 — Verification

- fixture pass persistence test;
- degraded live failure test;
- baseline comparison test;
- invalid baseline test;
- API list/detail/not-found tests;
- migration and architecture tests;
- full backend regression.

### T6 — Learning and portfolio artifacts

- ADR for immutable Requirement Eval Runs;
- learning record with prediction, explanation and review questions;
- demo script and interview questions;
- update README and roadmap.

## Scope guard

Do not add in this slice:

- Requirement human review or accepted baseline endpoint;
- live provider credentials or model changes;
- 20-job manual review UI;
- Match/Eligibility/Ranking;
- batch queues, retries or scheduling;
- Agent tools or multi-agent orchestration;
- Web dashboard.

## Required artifacts at completion

- tests;
- ADR;
- learning record;
- interview questions;
- demo instructions;
- Diff review with explicit unverified items.

## Implementation result

All six tickets were completed without expanding into Requirement human review, Match, a Web dashboard, background jobs or Agent orchestration.

### Evidence produced

- Migration `20260803_0008` creates immutable Run and Case Result tables and cleanly downgrades to `20260803_0007`;
- Fixture CLI produced Run `reqeval_ae51f68c6d9742f5a6b825c57aae3077` with 10/10 cases, 100% capability recall, 100% importance accuracy, Gate passed and `releaseEligible=false`;
- database constraints reject `fixture + releaseEligible=true`;
- a degraded extractor persists explainable missing Requirement failures;
- a provider failure keeps Case → error Trace links;
- a simulated final persistence failure leaves 10 diagnostic Traces and zero partial Eval Run/Case rows;
- a missing baseline is rejected before any Workflow or Trace execution;
- list/detail/404/OpenAPI contracts are covered;
- `alembic check` reports no schema drift;
- full backend regression: 226 passed.

### Canonical artifacts

- ADR: `docs/decisions/0022-requirement-eval-runs-and-live-release-eligibility.md`;
- learning record, quiz, interview questions and Demo: `docs/implementation/P0-3B-Requirement-Eval-Learning-Record.md`;
- API contract: `docs/integration/REQUIREMENT-EVAL-API-CONTRACT.md`.

## Independent Diff review

### Reviewed boundaries

- Router only maps HTTP and depends on application use cases;
- Application/Eval code imports no SQLAlchemy or ORM models;
- Repository performs mapping/querying but no commit/rollback;
- Unit of Work owns the final atomic persistence transaction;
- Provider/Trace execution remains outside that transaction;
- Fixture/Live release semantics are enforced in application and database;
- read API does not expose raw JD text;
- no Match, Review, Agent or UI behavior was added.

### Review findings corrected

1. A circular import was found because the Requirement Eval package entry point eagerly imported use cases that imported the Repository Port. The package entry point was reduced to models/errors, and routers import use cases explicitly.
2. Full regression found one Phase 3A metadata test with a hard-coded table set. It was updated to include the two new tables, after which 226/226 tests passed.
3. `docs/learning/` and `docs/dev-journal/` are intentionally gitignored. The canonical tracked learning artifact was placed under `docs/implementation/` and the root README link was corrected to avoid a broken portfolio link.

## Explicitly unverified

- live OpenAI Requirement extraction quality;
- 20 real-job manual acceptance;
- Requirement human Review and accepted baseline;
- target-market coverage of the current 10-case dataset;
- production threshold calibration;
- cost, P50/P95 latency and retry policy;
- Web review experience;
- Eligibility, Match, Ranking or Career Agent integration.

The feature is engineering-complete, but Requirement model quality is not yet human-approved. Phase 4 must remain blocked until Phase 3B-2 produces live and human evidence.
