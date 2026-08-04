# P0-3B-3D｜Requirement Canary Human Gate

Status: implemented and verified on 2026-08-04

## 1. Current real project feature

Require a human go/stop judgment after the first 1–3 live Requirement Extraction attempts and before the fourth cumulative OpenAI call for the same frozen Acceptance Run.

```text
formal 20-JD dataset
→ controlled Run
→ 1–3 cumulative live calls
→ inspect Job + Extraction + Trace
→ immutable human decision: continue | stop
→ continue: allow remaining controlled calls
→ stop: block this Run permanently
→ 20 current same-cohort Extractions
→ exact Manual Review Batch
```

This slice does not judge Requirement correctness automatically, execute a real provider in the development session, approve a model, or start Match.

## 2. Learning goal

Master the minimum backend and Agent-engineering mechanisms behind human-in-the-loop release control:

- per-command limits versus cumulative Run limits;
- why human approval is a business invariant, not a CLI hint;
- immutable human decisions and database uniqueness;
- server-derived evidence snapshots;
- command state versus historical facts;
- short human command endpoints versus long provider execution;
- optimistic single-operator assumptions and future lease boundaries;
- proving a gate with DB rows, API errors, Trace counts and absence of new provider work.

## 3. Risk assessment

### Business risk: high

Without this gate, an operator can bypass a 3-call Canary by running:

```text
1 + 1 + 1 + 17
```

Each command respects its local limit, but the Run reaches 20 calls without anyone inspecting the first outputs. Other risks:

- a stop decision can be overwritten later;
- the client can claim it inspected evidence it never saw;
- a duplicate request creates conflicting decisions;
- the fourth call occurs before approval because policy lives only in the CLI;
- a decision references current mutable Job state rather than frozen Trace/Extraction evidence;
- a polished Batch is created even though no one approved provider expansion.

### Learning risk: high

The learner may delegate the exact judgment the feature exists to preserve. The Agent must not:

- choose `continue` or `stop`;
- write the human notes;
- decide that missing Requirements are acceptable;
- infer that three successful HTTP calls prove model quality;
- approve the model or begin Match.

## 4. Core mechanisms reserved for the learner

Before reading the Diff, the learner must write a prediction table for:

| Existing Run | Attempted calls | Review | Requested new calls | Expected result |
|---|---:|---|---:|---|
| none | 0 | none | 4 | ? |
| partial | 2 | none | 1 | ? |
| partial | 2 | none | 2 | ? |
| partial | 3 | none | 1 | ? |
| partial | 1 | continue | 19 | ? |
| partial | 1 | stop | 1 | ? |
| ready | 20 | none, legacy | 1 | ? |

The learner must personally:

- inspect the Canary Job descriptions, Requirement outputs and Trace references;
- choose `continue` or `stop`;
- write the review notes;
- explain why the selected evidence is enough or insufficient;
- complete the later 20-case Requirement quality review;
- decide whether issue distribution allows Match work to begin.

## 5. Peripheral work delegated to the development Agent

- ORM and Alembic boilerplate;
- persistence/query ports and Unit of Work wiring;
- API/Pydantic mapping;
- cumulative gate calculations;
- unique-constraint error mapping;
- deterministic evidence snapshot construction;
- tests, migration smoke, ADR, learning record and Demo script;
- independent Diff review.

## 6. Facts, inference, assumptions and unknowns

### Confirmed facts

- P0-3B-3C persists one Run and 20 operational Cases.
- OpenAI commands already require an explicit `maxNewExtractions` value.
- That limit was per command, not cumulative across one Run.
- Run Case rows contain attempt count, Trace ID and Extraction ID.
- Provider execution is CLI-owned; the Run API was read-only.
- No real OpenAI credentials or 20-case human results were available in this session.

### Inference

- The fourth cumulative call is the correct enforcement boundary for a 1–3 case Canary.
- The decision must be immutable because it is governance evidence.
- The reviewed evidence set must be derived by the Backend from attempted Cases.
- A short human decision is suitable for HTTP even though long provider execution is not.
- A stop decision should end this specific frozen Run rather than delete history.

### Assumptions

- Local MVP has one operator and no intentionally concurrent execution process.
- The Run reviewer is the only reviewer allowed to submit its Canary decision.
- One decision per Run is sufficient for this phase.
- Review after 1, 2 or 3 attempts is allowed.
- `continue` requires at least one successful Extraction and every attempted case must have a Trace.

### Unknowns

- Real model output quality and cost.
- Whether production needs multiple staged approvals beyond one Canary gate.
- Authenticated identity and RBAC.
- Concurrent stop/continue versus worker-start race behavior.
- Queue, lease, cancellation and retry requirements.
- Final release threshold after all 20 human decisions.

## 7. User value hypothesis

An operator should be unable to spend on a fourth live extraction for the same Run until they have inspected the available Canary evidence and left an auditable decision.

Observable value:

- the Run reports `awaiting_canary_review` after three unreviewed attempts;
- the fourth call is rejected before a new Import, Trace or Extraction;
- the review freezes exact Case, Trace and Extraction IDs;
- `continue` unlocks controlled expansion;
- `stop` prevents future calls for that Run;
- duplicate or changed decisions are rejected;
- the later Manual Review Batch still requires 20 separate human quality judgments.

## 8. Completion standards

### Engineering completion

| Standard | Required evidence |
|---|---|
| first live command cannot request more than 3 calls | Application test; zero Import/Trace |
| cumulative fourth call requires approval | gate test; unchanged Import/Trace counts |
| decision snapshots server-derived evidence | DB/API reviewed Case/Trace/Extraction arrays |
| review is immutable | DB unique constraint + duplicate 409 |
| reviewer must own the Run | 422 API/Application test |
| notes are substantive | minimum-length test |
| continue needs inspectable model evidence | at least one Extraction + all attempted Traces test |
| continue unlocks remaining calls | same Run ID; 3 reused + 17 extracted; one Batch |
| stop blocks future execution | gate error before Import; unchanged Trace count |
| Run status exposes gate state | GET API `awaiting_canary_review` / `stopped` |
| browser still cannot start provider execution | OpenAPI has no execution POST |
| migration is reversible | 0012 → 0011 → head test |
| no regression | full Backend/Web/Collector tests, build and Alembic check |

### Learning completion

The learner can explain without reading code:

- per-command versus cumulative limit;
- why Application owns the gate;
- why a review snapshots IDs instead of only free-text notes;
- why decision history is immutable;
- why stop blocks this Run but does not erase it;
- why API may accept a short decision but not start long provider execution;
- what race remains under the single-operator assumption;
- why Canary approval is not model release approval.

### Portfolio completion

Repository contains:

- implementation plan;
- ADR;
- migration and persistence model;
- state-machine and API tests;
- API contract and curl examples;
- learning record and interview questions;
- Demo script showing bypass prevention, continue and stop;
- explicit unverified items.

### User-value completion

```text
run 1–3 live Canary calls
→ GET Run and inspect referenced evidence
→ POST immutable continue/stop decision
→ continue: CLI may resume under explicit budget
→ stop: CLI fails before Import/provider work
```

## 9. Minimal knowledge for this slice

### Per-command limit is not a cumulative policy

```text
command A max=1
command B max=1
command C max=1
command D max=17
```

Every command is locally valid. Only persisted `attemptedCalls` can enforce the Run-level boundary.

### Evidence snapshot

The client submits only:

```text
decision
reviewer
notes
```

The Backend derives:

```text
reviewedCaseIds
reviewedExtractionIds
reviewedTraceRunIds
```

This prevents the client from claiming a different evidence set.

### Gate truth

```text
new Run + requested > 3                  → block
attempted < 3 + request within remainder → allow
attempted >= 3 + no review               → block
review = continue                        → allow explicit controlled budget
review = stop                            → block permanently for this Run
ready legacy Run                         → read/reuse without new work
```

## 10. Common wrong implementation

```python
if request.max_new_extractions <= 3:
    run_provider_calls(request.max_new_extractions)
```

Why it fails:

- four separate commands bypass the rule;
- no persisted decision exists;
- no evidence IDs prove what the reviewer inspected;
- stop cannot prevent the next command;
- UI/CLI policy can be bypassed by another caller.

Failure case:

```text
09:00  max=1 → output not inspected
09:05  max=1 → output not inspected
09:10  max=1 → output not inspected
09:15  max=17 → all remaining calls execute
```

The logs say every command respected its limit, but the business guarantee is false.

## 11. Tickets (1–3 hours each)

### T0 — Truth table and scope

- define cumulative call boundary;
- define continue/stop semantics;
- define learner-owned judgment.

### T1 — Persistence contract

- add immutable Canary Review table;
- unique Run decision;
- snapshot Case/Extraction/Trace IDs;
- migration up/down.

### T2 — Human decision policy

- validate reviewer, notes and attempted evidence;
- allow one decision only;
- derive evidence server-side.

### T3 — Application gate

- enforce first-command and cumulative limits;
- continue unlock;
- stop block before Import.

### T4 — Short HTTP command

- GET exposes review/gate status;
- POST review with stable 404/409/422 errors;
- no provider execution route.

### T5 — Failure and transition tests

- bypass attempt;
- continue path;
- stop path;
- duplicate decision;
- invalid reviewer/notes;
- migration round trip.

### T6 — Portfolio artifacts and Diff review

- ADR/API contract/learning record;
- Demo and interview questions;
- regression suite;
- explicit unverified concurrency boundary.

## 12. Scope guard

Do not add:

- real provider credentials or calls;
- automatic continue/stop decisions;
- Web-triggered provider execution;
- model approval or Match;
- multi-stage approvals;
- editable Review history;
- authentication/RBAC;
- Redis/Celery/queue/lease infrastructure;
- automatic retries;
- multi-agent architecture.
