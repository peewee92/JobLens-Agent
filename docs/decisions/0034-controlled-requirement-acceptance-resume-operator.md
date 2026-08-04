# ADR-0034: Controlled Requirement Acceptance Resume Operator

- Status: Accepted
- Date: 2026-08-05

## Context

Requirement Acceptance already supports:

```text
formal dataset
→ 1–3 live Canary attempts
→ immutable human Continue/Stop review
→ resumable Preparation use case
```

The domain use case correctly blocks a fourth live attempt until an immutable Continue exists. However, calling the generic Preparation CLI after Continue does not explicitly bind one operational command to:

- the canonical private dataset;
- the exact persisted Run;
- the exact immutable Continue review;
- the current incomplete Case count;
- one explicit new-Provider-call budget;
- the session manifest and post-execution evidence.

A Continue decision authorizes the Run to proceed. It does not by itself prove that a later shell command still points to the same evidence or that the requested budget is appropriate for the remaining work.

## Decision

Add a dedicated `operate_requirement_acceptance_resume` command for every post-Continue live resume invocation.

The command has a read-only Plan mode and an explicit Execute mode. Execute mode requires all of:

```text
canonical fingerprint-addressed private dataset
AND readiness.nextAction == resume_run
AND providerExecutionAllowed == true
AND existing Run identity matches readiness
AND --expected-run-id matches the persisted Run
AND immutable Canary decision == continue
AND --expected-canary-review-id matches that decision
AND immutable reviewed Case / Extraction / Trace evidence is structurally complete
AND pre-first-resume current pointers match the frozen review snapshot
AND explicit budget <= incomplete Case count
AND --execute-resume
AND --confirm-reviewed-canary-and-live-cost
```

The domain Preparation use case remains the source of business execution. The Resume Operator only enforces the operational safety boundary, invokes the stable use case and verifies the resulting Run/Attempt/Trace/Batch evidence.

Readiness command previews route:

- `run_canary` to the explicit Canary Operator plan;
- `resume_run` to the explicit Resume Operator plan.

They no longer recommend the generic Preparation CLI for live operational work.

## Evidence contract

Before execution, the command records:

- Dataset file SHA-256 and byte count;
- Readiness summary;
- Run ID and Canary Review ID;
- attempted/completed/remaining counts;
- secret-free Session Manifest.

After execution, it verifies:

- the same Run ID;
- the same immutable Canary Review ID;
- historical Review IDs remain authoritative when later retries update current Case pointers;
- per-Case `attemptCount` deltas;
- Extraction and Trace IDs;
- explicit attempt budget;
- unchanged dataset bytes;
- next action: another controlled resume or Manual Review Batch.

Execution leases from ADR-0033 remain the final concurrency gate. A lease conflict is rejected before Provider/Trace/Attempt side effects.

## Consequences

- Human approval and machine execution are connected by immutable IDs rather than operator memory.
- Partial resumes are allowed and produce the next explicit resume command.
- A completed 20-Case Run hands off to Manual Review without another Provider command.
- The generic Preparation CLI remains useful for fixture engineering and lower-level recovery, but is not the recommended live operator entry point.
- The command does not prove model quality. The final quality conclusion still requires 20 manual Case judgments.

## Rejected alternatives

### Reuse the generic Preparation CLI directly

Rejected because it does not require explicit Run/Review IDs or produce the complete operator evidence envelope.

### Automatically resume immediately after Continue

Rejected because the human decision and later Provider cost must remain separate explicit actions.

### Automatically run all remaining Cases

Rejected because operators must retain an explicit bounded budget for each external side-effect invocation.

## Verification

The implementation must prove:

1. plan mode performs no Provider execution;
2. missing or mismatched Run/Review evidence blocks before Runtime construction;
3. a post-Review retry may update current Case pointers without invalidating frozen historical Review IDs;
4. Stop or non-resume readiness cannot execute;
5. requested budget cannot exceed incomplete Case count;
6. partial resume records only the observed Attempt deltas and returns another resume command;
7. final resume returns the frozen Manual Review Batch URL;
8. execution-lease conflict records zero post-execution evidence;
9. the persisted Continue review remains unchanged through resume.
