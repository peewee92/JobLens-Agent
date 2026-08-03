# ADR-0019: Profile Eval Human Review and Accepted Baseline

- Status: Accepted
- Date: 2026-08-03

## Context

Profile Extraction Eval now persists immutable runs, case-level results, quality metrics, Trace links and versioned gate decisions. A run can be technically eligible for review, but technical eligibility is not the same as a human approval to use that run as the official comparison baseline.

Mutating `profile_eval_runs` with an `accepted` boolean would mix execution facts with later governance decisions and would lose reviewer, rationale and decision time.

## Decision

### Separate immutable facts

- `ProfileEvalRun` records model/workflow execution facts.
- `ProfileEvalReview` records one human governance decision for a run.
- A run can have at most one formal Review.
- Review decisions are `accepted` or `rejected`.

### Review eligibility

- Fixture runs cannot receive formal governance Reviews.
- A live run may be rejected regardless of gate result.
- A live run may be accepted only when `gatePassed=true` and `releaseEligible=true`.
- Reviewer and review notes are required.

### Accepted baseline

The current accepted baseline is the run referenced by the latest `accepted` Review, ordered by `reviewedAt` and Review ID for deterministic ties.

Reading the accepted baseline re-checks:

- Review is accepted;
- Run mode is live;
- Gate passed;
- Run is release eligible.

Accepting a newer run changes the current baseline without deleting or overwriting older Reviews.

### CLI behavior

`run_profile_eval --accepted-baseline`:

- is only valid for a live Provider;
- resolves the accepted baseline before constructing or invoking the Provider workflow;
- exits with code 1 when no accepted baseline exists;
- writes no Trace or Eval Run on preflight failure.

## Consequences

### Positive

- Technical quality and governance approval remain distinguishable.
- Review history is immutable and auditable.
- Fixture results cannot be promoted into production baselines.
- Later runs can compare against an explicitly accepted human baseline.

### Trade-offs

- Local single-user reviewer identity is self-declared, not authenticated.
- One Review per run means a decision cannot be silently overwritten; corrections require a future superseding governance design.
- The latest accepted Review becomes baseline even when its run is older than another accepted run; review intent takes precedence over execution time.

## Not included

- authentication or reviewer permissions;
- multi-person approval;
- Review revocation or superseding decisions;
- automatic deployment;
- Web review dashboard;
- a real credential-backed live Eval result.

## Verification

- Application and database tests for accept/reject rules;
- API 201/404/409/422 behavior;
- immutable Review row and unique run constraint;
- accepted baseline switching with history retention;
- CLI preflight tests proving zero Trace/Run on failure;
- Alembic 0006 upgrade/downgrade and drift checks;
- architecture tests preserving Router/Application/Repository boundaries.
