# ADR-0023｜Requirement Eval Human Review and Accepted Baseline

- Status: Accepted
- Date: 2026-08-03
- Scope: Requirement Extraction evaluation governance

## Context

ADR-0022 introduced immutable Requirement Eval Runs, Case Results, Trace links, deterministic Gates and `releaseEligible`.

That was necessary but insufficient. A Gate can prove only that one configured workflow met one dataset threshold. It cannot prove that:

- the dataset covers representative real jobs;
- `must_have / preferred / bonus` classifications are operationally acceptable;
- normalized capabilities preserve the original JD meaning;
- failures were inspected by a human;
- the model version is approved as the official comparison baseline.

Automatically promoting every Gate-passed Run would collapse four different facts into one:

```text
gatePassed
releaseEligible
human accepted
current official baseline
```

## Decision

### 1. Add one immutable Review per Requirement Eval Run

A Review contains:

- `decision`: `accepted | rejected`;
- reviewer;
- notes;
- reviewed timestamp;
- immutable link to one Eval Run.

The database enforces one Review per Run with a unique constraint.

### 2. Fixture Runs cannot receive official Reviews

Fixture Runs prove deterministic pipeline behavior only. Neither acceptance nor rejection is an official governance statement for Fixture data.

### 3. Failed Live Runs may be rejected but not accepted

A rejected Run is useful audit evidence. Acceptance requires:

```text
mode = live
AND gatePassed = true
AND releaseEligible = true
AND no existing Review
```

### 4. Accepted baseline is derived from immutable history

Do not store a mutable global `current_requirement_baseline_id`.

The official baseline is the latest Review satisfying:

```text
review.decision = accepted
run.mode = live
run.gatePassed = true
run.releaseEligible = true
```

Ordering:

```text
reviewed_at DESC
review.id DESC
```

This preserves all previous accepted baselines and allows audit/reconstruction.

### 5. Application owns policy; UoW owns transaction

FastAPI and React do not implement acceptance policy.

The Application Use Case:

- loads Run state;
- checks existing Review;
- validates reviewer/notes;
- enforces Fixture/Live and Gate rules;
- creates one Review;
- commits through a short Review Unit of Work.

Repository adapters do not call commit or rollback.

### 6. Web action rules are UX guards, not authority

The Web disables impossible actions and explains why, but the Backend remains authoritative. Direct POST requests still receive stable 404/409/422 responses.

### 7. Live CLI may select the human-accepted baseline

`run_requirement_eval --accepted-baseline` is allowed only for a Live Provider Eval. The baseline lookup happens before provider setup or Workflow execution, so missing baseline produces no Trace and no new Eval Run.

## State table

| Run | Accept | Reject | Baseline candidate |
|---|---:|---:|---:|
| Fixture, Gate pass | no | no | no |
| Fixture, Gate fail | no | no | no |
| Live, Gate fail | no | yes | no |
| Live, Gate pass, release eligible | yes | yes | yes only after accepted Review |
| Any already reviewed Run | no | no | existing immutable decision remains |

## Consequences

### Positive

- automatic quality evidence and human judgment remain distinct;
- accepted baseline has reviewer identity and notes;
- rejected Live Runs remain useful audit history;
- duplicate or overwritten decisions are prevented;
- future Eval comparisons can use a formally accepted baseline;
- Web and CLI share the same backend facts.

### Costs

- another table, Repository and Unit of Work;
- an operator must inspect cases and Trace evidence;
- current free-text reviewer identity is not strong authentication;
- a human can still make a poor decision.

## Rejected alternatives

### Automatically mark every Gate-passed Run as baseline

Rejected because Fixture can pass and metrics cannot replace human review.

### Mutable baseline pointer

Rejected because it hides history and adds state synchronization problems.

### Allow Review edits

Rejected because changing a governance decision should create a new Eval Run and Review, not rewrite history.

### Put acceptance logic in React

Rejected because clients are bypassable and multiple clients would diverge.

## Verification

- Application tests for Fixture/live acceptance matrix;
- unique Review DB constraint and duplicate HTTP 409;
- forced persistence failure leaves zero Review rows;
- accepted-baseline repository and API tests;
- raw JD fields excluded from public responses;
- CLI guards for Fixture and missing Live accepted baseline;
- Web action tests and same-origin architecture guards;
- production Next build;
- FastAPI + Next smoke for history → cases → reject/accept → baseline;
- Alembic upgrade/downgrade and drift check.

## Explicitly not proven

- OpenAI Requirement quality;
- 20-real-job manual acceptance;
- authenticated reviewer identity or RBAC;
- dataset representativeness;
- cost and latency release thresholds;
- safety of starting Match.
