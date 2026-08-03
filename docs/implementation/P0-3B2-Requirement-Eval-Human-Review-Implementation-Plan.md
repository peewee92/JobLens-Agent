# P0-3B-2｜Requirement Eval Human Review & Accepted Baseline

Status: implemented and verified on 2026-08-03

## Current real project feature

Turn a persisted, release-eligible **Live Requirement Eval Run** into an immutable human governance decision, and expose the latest accepted Run as the official Requirement Extraction baseline.

```text
Live Requirement Eval Run
→ inspect metrics, failed cases and Trace IDs
→ human accept / reject
→ immutable Review
→ latest accepted live baseline
→ later live Eval compares against accepted baseline
```

This slice intentionally stops before Single Job Match.

## Learning goal

Use one real feature to master the minimum backend and Agent-engineering knowledge needed for trustworthy model release governance:

- automatic Gate vs human approval vs official baseline;
- Application policy that is independent from HTTP and ORM;
- immutable one-to-one Review persistence;
- Repository / Unit of Work transaction boundary;
- querying the latest valid accepted baseline;
- deriving UI actions from backend state instead of duplicating business truth;
- proving completion with tests, database records, API responses and UI behavior.

## Business risk

Risk level: **high**.

A wrong acceptance can promote a Requirement extractor that:

- upgrades optional wording to `must_have`;
- invents requirements not grounded in the JD;
- normalizes capabilities incorrectly;
- causes future Match, Ranking and Skill Gap decisions to be systematically wrong.

The dangerous failure is not an HTTP error. It is a successful-looking Review that approves a low-quality model.

## Learning risk

Risk level: **medium-high**.

The main learning risks are:

1. copying Profile Eval Review mechanically without understanding the policy;
2. treating a database row as proof that human review was meaningful;
3. confusing `gatePassed`, `releaseEligible`, `accepted` and `baseline`;
4. putting acceptance policy in React or FastAPI instead of Application;
5. believing simulated-live tests prove real OpenAI quality.

## Core mechanisms the learner should predict first

Before reading the implementation Diff, answer these on paper:

1. Can a Fixture Run be rejected? Why or why not?
2. Can a failed Live Run be rejected? Can it be accepted?
3. Should `releaseEligible=true` mean `accepted=true`?
4. Why must one Run have at most one Review?
5. If two Runs are accepted, which one is the baseline?
6. What should happen if Review persistence fails after policy validation?
7. Should the Web form decide acceptance rules, or only display allowed actions?
8. Why does an accepted baseline still not prove the next model version is safe?

These are the core training tasks. The Agent may implement boilerplate after the truth table is defined, but the learner must be able to explain the answers and trade-offs.

## Peripheral work the development Agent may complete

- SQLAlchemy column and relationship boilerplate;
- Alembic migration syntax;
- Pydantic response mapping;
- FastAPI dependency wiring;
- Next.js proxy route, form state and styling reuse;
- repetitive integration-test fixtures;
- README and API-contract updates.

## Facts, inference, assumptions and unknowns

### Confirmed facts

- Requirement Eval Runs and Case Results are immutable and persisted.
- Each Case is linked to a Requirement Workflow Trace when available.
- Fixture and Live modes are separated.
- Fixture Runs are never release-eligible.
- A Live Run is release-eligible only when the deterministic Gate passes.
- Requirement Review and Accepted Baseline were absent at the start of this slice and are now implemented.
- Profile Eval already had a similar governance path that was studied, not blindly copied.

### Inference

- Requirement Eval should use the same governance vocabulary as Profile Eval to reduce operator confusion.
- A rejected Live Run is still valuable evidence and should remain queryable.
- Accepted baseline should be derived from immutable Reviews, not stored as a mutable global pointer.

### Assumptions

- Local MVP remains single-user and reviewer identity is free text.
- SQLite remains the MVP database.
- `openai` is the only current real Requirement Provider label; tests may use `simulated-live` by constructing the use case directly.
- The most recently reviewed accepted valid Run is the official baseline.

### Unknowns

- No OpenAI credential-backed Requirement Eval has been verified in this session.
- No 20-real-job manual review has been completed.
- Reviewer authentication, RBAC and audit identity are not implemented.
- The quality dataset may not cover all job categories or ambiguous Chinese wording.
- Cost and latency thresholds are not part of the current Gate.

## User value hypothesis

A user deciding which jobs to apply for needs the JobRequirement fact base to be stable and trustworthy. Requiring an explicit human acceptance before a model version becomes the official baseline reduces the chance that silent extraction regressions contaminate Match and Ranking.

Observable value:

- the operator can see failed cases and Trace IDs;
- the operator cannot accidentally accept Fixture or Gate-failed Runs;
- the acceptance decision is immutable and auditable;
- later live runs can compare against a human-approved baseline.

## Completion standards

### Engineering completion

| Standard | Required evidence |
|---|---|
| one immutable Review per Run | DB unique constraint + duplicate-review test + HTTP 409 |
| Fixture cannot receive official Review | Application test + HTTP 422 + disabled UI actions |
| failed Live Run can only be rejected | policy test + API response + UI action test |
| eligible Live Run can be accepted or rejected | Application tests + API 201 + persisted DB row |
| accepted baseline is latest valid accepted Live Run | repository test + GET API response |
| Run detail exposes Review | API detail test + Web detail behavior |
| CLI resolves accepted baseline before provider execution | Fixture/missing-baseline process tests + repository comparison tests; successful credential-backed run remains unverified |
| no raw JD leaked | API serialization test |
| no half-written Review | forced persistence-failure transaction test |
| no architecture leakage | AST architecture tests |
| no regression | full backend tests + Web tests + production build |

### Learning completion

The learner can explain without reading code:

- the four-state distinction: Gate / release eligibility / Review / baseline;
- why rejection is allowed for failed Live Runs;
- why Fixture cannot receive official Review;
- why accepted baseline is a query over immutable history;
- where transaction ownership belongs;
- why UI permissions are only a user-experience guard;
- why simulated-live tests do not validate provider quality.

Evidence: written answers in the learning record and final oral/self-review questions.

### Portfolio completion

The repository contains:

- an ADR with the governance state machine;
- API contract and curl examples;
- tests showing allowed and forbidden transitions;
- a Web screen that displays case evidence and Review state;
- a demo script proving Fixture refusal, Live acceptance and baseline retrieval;
- explicit unverified items.

### User-value completion

A reviewer can complete this path:

```text
open Requirement Eval history
→ open one Live Run
→ inspect failed cases and Trace IDs
→ accept or reject once
→ see immutable Review
→ see accepted baseline status
```

Every step must map to an API response or visible UI behavior.

## Minimal knowledge for this slice

### State distinction

```text
gatePassed
  deterministic dataset threshold result

releaseEligible
  automatic permission to enter human acceptance review

review.decision
  immutable human governance judgment

accepted baseline
  latest accepted, valid Live Run used for future comparison
```

### Transaction rule

Policy reads may happen before the transaction. The single Review insert must happen in one short Unit of Work. A failed commit must produce zero Review rows.

### Baseline query rule

Do not mutate a global `current_baseline_id`. Query immutable accepted Reviews joined with valid Live Runs, ordered by `reviewed_at DESC, review.id DESC`.

## Common wrong implementation

```python
if run.gate_passed:
    run.is_baseline = True
```

Why it fails:

- Fixture can pass the Gate;
- automatic metrics replace human judgment;
- mutable flags erase governance history;
- concurrent updates can produce ambiguous current state;
- there is no reviewer, note or review timestamp;
- future code cannot distinguish automatic and human evidence.

Failure case:

A Fixture Run scores 10/10. The implementation marks it baseline. Match begins using a fake deterministic extractor and all later evaluation appears stable, while no real model has ever been reviewed.

## Tickets (1–3 hours each)

### T0 — Contract and truth table

- freeze allowed Review transitions;
- define Review and Accepted Baseline response shapes;
- write implementation plan and prediction questions.

### T1 — Schema and migration

- add `requirement_eval_reviews`;
- one-to-one FK to `requirement_eval_runs`;
- decision check constraint and ordering index;
- upgrade/downgrade tests.

### T2 — Application policy and persistence

- Review models and errors;
- Review Repository and Unit of Work;
- accept/reject use case;
- latest accepted baseline query;
- transaction-failure test.

### T3 — Backend API and CLI

- POST Review endpoint;
- GET accepted baseline endpoint;
- include Review in Run detail;
- stable 404/409/422 errors;
- `--accepted-baseline` CLI option.

### T4 — Web review workflow

- Requirement Eval contracts and backend fetchers;
- history page and detail page;
- Review form and same-origin POST route;
- action policy helper and unit tests;
- accepted baseline summary.

### T5 — Verification and independent Diff review

- focused backend tests;
- full backend regression;
- Web unit tests and production build;
- migration drift check;
- inspect Diff for leaked raw data, duplicated policy and unverified claims.

### T6 — Portfolio and learning artifacts

- ADR;
- learning record and interview questions;
- API contract;
- demo steps;
- README and roadmap updates.

## Completion evidence

| Standard | Evidence |
|---|---|
| immutable one-to-one Review | `requirement_eval_reviews` unique constraint, duplicate Use Case test and HTTP 409 |
| Fixture cannot receive Review | Application test, API 422, Web action test and real-process Smoke |
| failed Live can only be rejected | Application/API tests and real-process rejected Review |
| eligible Live can be accepted | persisted Review test, API 201 and real-process accepted Review |
| latest accepted valid Run is baseline | Repository ordering test, baseline API test and SSR baseline card |
| Review appears in Run detail | API detail assertion and accepted/rejected detail Smoke |
| raw JD stays private | API serialization assertions and public contract architecture guards |
| Review transaction is atomic | forced persistence-failure test leaves zero Review rows |
| migration is reproducible | 0009 upgrade/downgrade, FK/constraint/type assertions and `alembic check` |
| Backend regression | 244 tests passed |
| Web regression | 31 tests, TypeScript typecheck and production Next build passed |
| full product path | FastAPI + production Next + temporary SQLite Smoke passed |

## Discovered failure and correction

The first 0009 migration used `VARCHAR(100)` for `eval_run_id`, while the referenced Run primary key and ORM used `VARCHAR(90)`. All behavior tests still passed. `alembic check` detected the drift. The migration was corrected, the local database was downgraded and re-upgraded, and a column-length assertion was added to the migration test.

## Learning status

Engineering and portfolio artifacts are complete. Learning completion remains conditional on the learner answering the prediction and review questions in `P0-3B2-Requirement-Eval-Human-Review-Learning-Record.md` without reading the implementation.

## Explicitly unverified

- credential-backed OpenAI Requirement Eval quality;
- a successful real-provider CLI run using `--accepted-baseline`;
- manual review of 20 real jobs;
- authenticated reviewer identity and RBAC;
- dataset representativeness, cost and latency release thresholds;
- readiness to begin Single Job Match.

## Scope guard

Do not add:

- real provider credentials;
- changes to Prompt, model or Requirement normalization;
- 20-job manual review data;
- reviewer authentication/RBAC;
- Match, Eligibility or Ranking;
- background jobs, retries or scheduling;
- Multi-Agent or Career Agent;
- a generic evaluation platform abstraction.
