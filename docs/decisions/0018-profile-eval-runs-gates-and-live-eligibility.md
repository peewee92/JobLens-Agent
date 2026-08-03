# ADR-0018: Persist Profile Eval Runs, Version Quality Gates, and Separate Live Eligibility

- Status: Accepted
- Date: 2026-08-03

## Context

Profile Extraction already had:

- a 10-case redacted dataset;
- deterministic assertions;
- one Workflow Trace per case;
- a CLI that printed pass/fail.

Terminal output was not enough for model governance. It could not answer:

- which model/prompt/dataset/gate produced a result;
- which cases failed and why;
- which Trace belongs to a failed case;
- whether a new run regressed from a baseline;
- whether a passing run used Fixture or a real provider.

The environment does not currently provide a live model credential. A Fixture 10/10 must never be represented as proof that a live model is production-ready.

## Decision

### 1. Persist immutable Run and Case Result records

Add:

```text
profile_eval_runs
profile_eval_case_results
```

One Run stores provenance, aggregate metrics and the gate result. One Case Result stores stable failures, expected/actual values and an optional `trace_run_id`.

Dataset resume text is not copied into these tables.

### 2. Version the gate

The first gate is `profile-eval-gate-v1`:

```text
casePassRate          >= 0.90
workflowSuccessRate   == 1.00
skillRecall           >= 0.95
yearsAccuracy         >= 0.90 when applicable
forbiddenFactRate     == 0.00
```

A threshold change requires a new gate version. Historical results keep the semantics used at execution time.

### 3. Separate gate pass from release eligibility

```text
gatePassed
= metrics satisfy the configured gate

releaseEligible
= mode == live AND gatePassed
```

Fixture runs can and should pass CI. They can never be release-eligible.

### 4. Keep case-level evidence

Aggregate metrics are useful for automation but insufficient for review. Every run keeps:

- stable failure codes;
- failure reasons;
- expected and actual skills;
- expected and actual years;
- observed forbidden terms;
- the Workflow Trace run ID when available.

### 5. Persist an optional baseline relationship

A run may reference one earlier run. The read model computes metric deltas. The Application validates the baseline before invoking the provider, and the database also enforces the self-reference.

### 6. Keep execution in CLI, review in a read-only API

Execution remains an explicit local/CI command:

```bash
uv run python -m scripts.run_profile_eval
```

Review uses:

```http
GET /api/v1/profile-evals
GET /api/v1/profile-evals/{evalRunId}
```

The read API never returns resume text or resume hashes.

## Consequences

### Positive

- model/prompt/dataset/gate provenance becomes auditable;
- failed cases link to Workflow Trace;
- regression against a baseline becomes explicit;
- CI Fixture evidence and live model evidence cannot be confused;
- future Requirement/Match evals have a concrete pattern to learn from.

### Costs

- two new SQLite tables and one migration;
- Trace rows are committed before the aggregate Eval Run, so a catastrophic Eval persistence failure can leave ungrouped Traces;
- the current gate is intentionally simple and dataset-specific;
- no live quality conclusion is possible without runtime credentials.

## Rejected alternatives

### Store only a numeric score

Rejected because it hides the failure distribution and breaks explainability.

### Treat Fixture 10/10 as model approval

Rejected because Fixture validates code paths, not provider behavior.

### Put thresholds only in CI YAML

Rejected because historical runs would lose the exact decision semantics.

### Automatically choose or deploy the best model

Rejected as premature. Human review of failed cases and Trace remains required.

## Follow-up

Before Phase 3 begins:

1. configure a real provider and model;
2. run the 10-case live Eval;
3. review every failed Case Result and Trace;
4. compare against an accepted baseline;
5. only proceed when a live run is gate-passing and manually reviewed.
