# ADR-0033: Requirement Acceptance Execution Lease

- Status: Accepted
- Date: 2026-08-05

## Context

Live Requirement Acceptance uses a read-only readiness check followed by a paid Provider execution. Two operator processes can read the same Run state before either process records an attempt. Readiness alone therefore cannot prevent duplicate Provider calls, duplicate Trace evidence or exceeding the cumulative Canary budget.

A long database transaction around Provider calls would serialize work, but it would also hold locks across slow external I/O. An in-process lock or local file lock would not protect multiple Backend/CLI processes consistently.

## Decision

Before import, extraction or Trace creation, `PrepareRequirementAcceptanceBatchUseCase` must acquire one short-lived database lease for the stable execution identity:

```text
datasetFingerprint
+ title
+ reviewer
+ provider
+ model
+ extractorVersion
+ promptVersion
```

The identity is hashed and stored in `requirement_acceptance_execution_leases` with:

- an opaque owner token;
- acquisition timestamp;
- expiration timestamp.

Acquisition is an atomic conditional write:

- create the lease when no row exists;
- replace it only when the existing lease has expired;
- otherwise reject the execution before import, Provider, Trace or attempt side effects.

The default lease duration is 30 minutes. Before each new Provider call, the current owner must atomically renew the lease with the same owner token; an expired or replaced owner is stopped before that call. Normal success and handled failure release the lease. A crashed process leaves a lease that can be reclaimed after expiration. Release requires the same owner token, so an old process cannot delete a newer owner's lease.

## Consequences

- Only one execution may operate on the same acceptance identity at a time.
- Readiness remains advisory; the lease is the final side-effect concurrency gate.
- Different datasets, reviewers, titles or extraction cohorts may still execute independently.
- A crashed execution can temporarily block retry until lease expiration.
- A process that runs longer than the lease duration may lose ownership; this is surfaced as an attention-required execution error rather than silently treated as success.

## Verification

The implementation must prove:

1. a second active owner is rejected;
2. only the current owner can renew, and an expired lease can be atomically reclaimed;
3. a lost owner is stopped before its next Provider call;
4. the rejected execution creates no new import, Trace or attempt;
5. normal success and business failure leave no lease row;
6. the migration can upgrade and downgrade cleanly.
