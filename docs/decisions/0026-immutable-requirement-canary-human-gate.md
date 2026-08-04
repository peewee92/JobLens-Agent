# ADR-0026｜Immutable Requirement Canary Human Gate

- Status: Accepted
- Date: 2026-08-04
- Scope: credential-backed Requirement acceptance execution control

## Context

ADR-0025 introduced persistent Acceptance Runs, explicit per-command call limits and resumable Case state. That prevented one accidental unbounded command, but did not enforce the intended human-in-the-loop workflow across several commands.

A user could run:

```text
max=1
max=1
max=1
max=17
```

Every command satisfied its local limit while the fourth cumulative call and all remaining spend occurred without human inspection.

The system also lacked a durable answer to:

- who approved expansion;
- which exact Canary cases were inspected;
- which Trace and Extraction versions supported the decision;
- whether a later request overwrote a stop decision;
- whether the backend or only the CLI enforced the policy.

## Decision

### 1. Enforce the Canary boundary cumulatively per Run

For OpenAI Runs:

```text
first 1–3 cumulative attempted calls: allowed under explicit budget
fourth cumulative call: blocked until human decision = continue
human decision = stop: all future execution for this Run blocked
```

Reuse and deferral do not count as provider attempts. Failed calls do count because cost/time was consumed and a Trace exists.

### 2. Application owns the gate

The CLI may provide an early message, but `PrepareRequirementAcceptanceBatchUseCase` is authoritative. Any future caller must pass the same business rule.

The gate runs before Job Import and before any provider call, so a blocked command creates no new Import, Trace or Extraction evidence.

### 3. Add one immutable Canary Review per Run

A Canary Review stores:

- decision: `continue | stop`;
- reviewer;
- substantive notes;
- server-derived reviewed Case IDs;
- server-derived Extraction IDs;
- server-derived Trace IDs;
- review timestamp;
- immutable Run link.

The database enforces one Review per Run.

### 4. The Backend derives the evidence snapshot

The request does not provide reviewed IDs. The Backend selects every attempted Case in the Run at review time and freezes its references.

This prevents a client from claiming it inspected a different set of evidence.

### 5. Review is allowed after 1–3 cumulative Provider attempts

The operator may stop early after one poor result or continue after one strong result. A review is invalid when:

- no Provider call was attempted;
- more than three cumulative Provider calls were already attempted;
- an attempted case lacks a Trace;
- reviewer differs from the Run owner;
- notes are too short;
- `continue` has no successfully persisted Extraction;
- the Run already has a decision or Batch;
- provider is not OpenAI.

### 6. `stop` ends the Run without deleting history

A stopped Run remains queryable with all Imports, Cases, Traces, errors and the human decision. A new experiment requires a distinct Run identity rather than rewriting the stopped one.

### 7. Short human commands may use HTTP; provider execution remains CLI-owned

Add:

```http
POST /api/v1/requirement-acceptance-runs/{runId}/canary-review
```

Do not add an HTTP command to start or resume provider work. The decision is a short database transaction; provider execution is long-running and cost-bearing.

## State semantics

```text
pending                  no operational progress
partial                  progress exists, Canary cap not yet reached or approved
awaiting_canary_review   >=3 attempted calls, no decision, no Batch
stopped                  immutable decision = stop
ready                    20 successful current Extractions and Batch attached
```

A `continue` decision does not mean the model passed quality review. It only permits controlled execution to continue.

## Consequences

### Positive

- repeated small commands cannot bypass the human gate;
- approval is auditable and evidence-grounded;
- stop is durable;
- duplicate decisions are rejected at Application and database levels;
- the fourth call is blocked before additional persistence or spend;
- human judgment remains distinct from model execution and final model approval.

### Costs

- one table, migration, repository command and API endpoint;
- an operator must inspect evidence and leave notes;
- a stopped Run cannot be reopened;
- JSON snapshots do not provide foreign-key enforcement for every referenced ID;
- single-operator concurrency remains an explicit assumption.

## Rejected alternatives

### Keep only the CLI `max` option

Rejected because multiple commands bypass a per-command limit.

### Let the Agent approve automatically

Rejected because the gate exists to preserve independent human judgment.

### Store only a boolean `canary_approved`

Rejected because it loses reviewer, notes and exact evidence provenance.

### Accept reviewed IDs from the client

Rejected because the client could claim evidence it did not inspect.

### Allow decision edits

Rejected because governance history must not be silently rewritten.

### Add queue workers and distributed locks now

Rejected as out of MVP scope. The current system documents the single-operator assumption and the unresolved concurrent stop-versus-worker-start race.

## Verification

- cumulative fourth-call gate test;
- first-command `>3` rejection test;
- unchanged Import and Trace counts when blocked;
- continue path creates one Review and later one Batch;
- stop path prevents future execution;
- duplicate Review 409 and DB unique constraint;
- invalid reviewer/notes 422;
- API snapshots exact Case/Extraction/Trace IDs;
- OpenAPI contains review POST but no provider-execution POST;
- migration 0012 downgrade to 0011 and re-upgrade;
- full Backend/Web/Collector regression and Alembic drift check.

## Explicitly not proven

- real OpenAI quality, cost or latency;
- authenticated reviewer identity;
- distributed concurrency safety;
- whether one Canary approval is enough for production scale;
- 20-case human Requirement acceptance;
- model release eligibility or Match readiness.
