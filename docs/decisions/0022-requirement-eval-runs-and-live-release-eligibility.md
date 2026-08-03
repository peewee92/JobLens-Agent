# ADR-0022｜Requirement Eval Runs and Live Release Eligibility

- Status: Accepted
- Date: 2026-08-03
- Scope: Phase 3B-1 Requirement quality governance

## Context

Phase 3A established a versioned `JobRequirement` fact base, deterministic grounding validation, Trace, a 10-case Eval dataset and a CLI report. The Eval result was transient: it existed only in process memory and terminal output.

That was insufficient for the next product boundary. Requirement Extraction feeds Eligibility, Match, Ranking, Skill Gap, Resume and Interview workflows. A weak extractor can therefore amplify one error across the whole product. Before Match begins, JobLens needs durable evidence answering:

- which dataset, provider, model, prompt and extractor version were evaluated;
- what every case produced;
- which cases failed and why;
- which Trace reproduces each case;
- whether quality improved or regressed against a historical baseline;
- whether the run is even eligible for human release review.

## Decision

Persist each Requirement Eval execution as an immutable parent Run plus immutable Case Results.

```text
Requirement Eval Dataset
→ Requirement Workflow per case
→ Trace per case
→ deterministic metrics and Gate
→ one immutable RequirementEvalRun
→ immutable RequirementEvalCaseResults
→ optional baseline comparison on read
```

### Run provenance

A Run stores:

- dataset version;
- mode (`fixture` or `live`);
- provider and model;
- extractor, prompt and gate versions;
- optional immutable baseline Run ID;
- aggregate metrics;
- Gate result;
- release eligibility;
- timestamp.

### Case evidence

A Case Result stores:

- case ID;
- Trace Run ID;
- Workflow success;
- pass/fail;
- missing expected Requirements;
- wrong importance classifications;
- forbidden capabilities observed;
- actual Requirement labels;
- stable error text when execution or grounding fails.

Raw JD text, `originalText` and `evidenceSpan` are not returned by the Eval read API. Detailed model output remains inspectable through the linked Trace under the existing Trace privacy boundary.

### Fixture vs live

`fixture` proves that Dataset → Workflow → Validator → Trace → Gate → Persistence is deterministic and reproducible. It does not prove production model quality.

A Run is `releaseEligible` only when:

```text
mode == live AND gatePassed == true
```

This invariant is enforced in both the application runner and a database check constraint.

`releaseEligible=true` is not approval. Human review and an accepted Requirement baseline remain a separate future slice.

### Baseline comparison

A Run may reference a previous immutable Requirement Eval Run as `baselineRunId`. Metric deltas are derived on read rather than stored as mutable truth.

A missing baseline is rejected before any Workflow execution or Trace write.

### Transaction boundary

Provider execution and per-case Trace writes happen before the short Eval persistence transaction. The final Run and all Case Results are committed atomically in one Requirement Eval Unit of Work.

Trace transactions remain separate. If final Eval persistence fails, diagnostic Trace evidence is intentionally retained rather than rolled back with the report.

## Alternatives considered

### Reuse Profile Eval tables

Rejected. Profile and Requirement Eval metrics, case diagnostics and future human review semantics differ. A generic table would become a large nullable schema and weaken type-specific invariants.

### Save only aggregate metrics

Rejected. Aggregate pass rate cannot explain which capability, importance label or forbidden fact failed, and cannot reproduce the issue through Trace.

### Let the current model/prompt update a global `safe` flag

Rejected. This is mutable, unauditable, allows Fixture to certify production quality and loses dataset/model/prompt provenance.

### Persist baseline deltas

Rejected. Deltas are derived from two immutable Runs. Persisting them duplicates data and can drift if comparison rules evolve.

## Consequences

### Positive

- Requirement quality becomes queryable evidence rather than terminal output.
- Each failure is linked to a reproducible Trace.
- Fixture and live quality claims are mechanically separated.
- Baseline regressions can be detected before Match begins.
- The design is ready for a later immutable human Review and accepted baseline.

### Costs

- Adds two tables, a repository/UoW pair, application models and API contracts.
- Eval history increases local SQLite size.
- Current 10-case thresholds still require live validation and human calibration.

## Verification

- Fixture 10/10 Run persists 1 Run, 10 Case Results and 10 Traces while remaining non-release-eligible.
- Degraded extractor persists failed cases with missing Requirement labels and negative baseline deltas.
- Provider failure persists failed cases linked to error Traces.
- Database rejects `fixture + releaseEligible=true`.
- Missing baseline produces no Trace and no Eval Run.
- List/detail API exposes provenance, metrics, case diagnostics and comparison without raw JD.
- Alembic upgrade/downgrade and full backend regression pass.

## Deferred

- live OpenAI Requirement Eval;
- 20 real-job human review;
- Requirement Review/accepted baseline tables and API;
- Web quality review page;
- threshold calibration;
- cost/latency/retry metrics;
- Eligibility and Match.
