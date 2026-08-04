# ADR-0025｜Persistent Requirement Acceptance Runs and Canary Control

- Status: Accepted
- Date: 2026-08-04
- Scope: credential-backed Requirement Extraction acceptance execution

## Context

ADR-0024 introduced resumable orchestration from a formal Collector dataset to a frozen 20-case Requirement Review Batch. It safely reused current same-cohort Extractions and preserved successful partial progress.

That was necessary but still left three operational gaps:

1. one live command could call all 20 Jobs before the first output was inspected;
2. the orchestration itself had no durable Run/Case state between invocations;
3. operators could reconstruct results only indirectly from Import, Trace and Extraction rows.

For a learning-oriented managed Agent, “the command is resumable” is weaker than:

```text
preflight is safe
call budget is explicit
progress is persistent
failures are not overwritten
review batch is created only from complete current evidence
```

## Decision

### 1. Add persistent Acceptance Run and Case records

One Run freezes:

- stable dataset fingerprint;
- source version and latest observed export timestamp;
- title and reviewer;
- provider/model/extractor/prompt cohort;
- first and latest Import IDs;
- optional Review Batch ID;
- exactly 20 ordered Case records.

One Case records:

- source URL, title, company and description SHA-256;
- persisted Job ID;
- operational status;
- attempt count;
- Extraction ID and Trace ID;
- last attempted error evidence.

The Run is operational evidence. It does not replace immutable Trace, Extraction or human Review records.

### 2. Define stable dataset identity from evidence, not export time

The fingerprint includes ordered stable source and content evidence:

```text
version
URL / optional sourceJobId
title
company
sourceVersion
descriptionHash
```

`generatedAt` is stored as source metadata but excluded from the fingerprint. Re-exporting the same evidence resumes the same Run; changing a JD, source identity, title or company creates a different identity.

### 3. Require explicit live-call budget

OpenAI execution requires `--max-new-extractions`.

The limit counts only actual new provider calls in the current invocation. Safe same-input/same-cohort reuse consumes no budget. Failed calls consume budget because a provider request occurred.

Recommended first live invocation: 1–3 cases.

### 4. Preserve invocation facts and historical facts separately

The CLI result reports what happened now:

```text
reused / extracted / failed / deferred
```

The persistent Run preserves provenance across all invocations:

- a Case originally extracted by this Run remains `extracted` when later reused;
- a prior failed Trace/error is not erased by a later budget-deferred invocation;
- a later successful extraction may replace the failed operational state while immutable Trace history remains.

### 5. Use per-Case short transactions

Trace and Extraction retain their existing transaction boundaries. After each Case result, the Run Case is updated in a separate short transaction.

Crash window:

```text
Trace/Extraction committed
→ process exits
→ Run Case not updated
```

Recovery is safe: rerun finds the current same-cohort Extraction, reuses it, and repairs the Run Case without another provider call.

### 6. Keep Review Batch as the all-or-nothing boundary

No Batch is attached unless all 20 cases resolve to current same-cohort Extractions and there are no failed or deferred cases in the invocation.

An exact existing Batch is reused. The Run stores its Batch ID after creation/reuse.

### 7. Expose read-only progress over HTTP

Add:

```http
GET /api/v1/requirement-acceptance-runs/{runId}
```

The response exposes operational metadata, counts, Case status, Trace IDs, Extraction IDs and errors. It does not expose full JD text or provider secrets.

No HTTP endpoint starts or resumes provider execution in this slice. Long-running cost-bearing work remains CLI-owned.

## State semantics

| Persistent Case state | Meaning |
|---|---|
| `pending` | no invocation has resolved or attempted this Case yet |
| `deferred` | current execution intentionally made no call because budget/provider policy stopped it |
| `failed` | a real attempted operation failed; Trace/error evidence exists when the failure reached Workflow tracing |
| `extracted` | this Run created the current successful Extraction in one of its invocations |
| `reused` | the Run adopted a successful current Extraction that existed before this Run |

Run state is derived:

```text
pending = all cases pending
ready = Batch attached and all 20 cases successful
partial = every other persisted condition
```

## Consequences

### Positive

- live cost is explicitly bounded;
- first outputs can be inspected before continuing;
- progress survives shell/process restarts;
- exact failure evidence is inspectable;
- repeated invocations do not rewrite historical provenance;
- operators can query progress without starting provider work;
- one Batch remains tied to one complete current cohort.

### Costs

- two additional tables and a migration;
- more state-transition tests;
- local operators must keep the same title/reviewer to resume the same Run;
- concurrent intentional execution of the same Run remains outside the local single-user MVP;
- the CLI remains a manual operational step.

## Rejected alternatives

### Call all 20 Jobs in one command by default

Rejected because it prevents canary inspection and creates unmanaged cost/risk.

### Include `generatedAt` in the fingerprint

Rejected because re-export time is metadata, not evidence identity, and would create duplicate Runs.

### Store only a JSON progress file

Rejected because it is not transactionally linked to Jobs, Traces, Extractions, Imports or Batches.

### Rewrite every successful Case to `reused` on later invocations

Rejected because it destroys the fact that this Run originally created the Extraction and paid the call.

### Replace failed state with deferred state

Rejected because “not attempted now” must not erase a prior real attempted failure and Trace.

### Add a browser POST to start the 20-case job

Rejected for the local MVP because request lifetime, cancellation, retries and cost ownership are not yet modeled. A future queue may add an HTTP command while preserving this Run contract.

### Add Redis/Celery/distributed lease now

Rejected as scope expansion. Persistent local Run semantics should be proven before introducing distributed infrastructure.

## Verification

- Preflight zero-construction/zero-write test;
- stable fingerprint test across timestamp-only re-export;
- 3-case canary, 17-case resume and zero-call repeat test;
- provider unavailable and partial-failure tests;
- prior failure preservation test;
- invocation versus persistent provenance test;
- GET Run API/OpenAPI/404 tests;
- migration constraint and downgrade tests;
- full Backend, Web and Collector regressions;
- Alembic drift check.

## Explicitly not proven

- real OpenAI quality, token cost or latency;
- provider rate-limit behavior;
- concurrency safety across multiple operators/processes intentionally starting the same Run;
- queue cancellation and lease recovery;
- authenticated reviewer identity;
- 20-case human acceptance;
- readiness to start Match.
