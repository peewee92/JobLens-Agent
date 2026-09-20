# Trajectory / Trace Replay Eval — vNext 1.1 (Agent B)

Frozen cohort for the vNext 1.1 governed-loop and durable-dispatch trajectory gate
(PRD §15.3 / §16).

- Dataset: `career-trajectory-v1.jsonl` (**46 cases**, 16 trace families)
- Runner: `services/backend/app/evals/career_trajectory.py`
- Tests: `services/backend/tests/test_career_trajectory_eval.py`
- Core under test: `app/agent/governed_loop_runtime.py`, `app/agent/runtime_dispatch.py`

---

## Revision history

| Revision | Core baseline | Cases | Coverage |
|---|---|---|---|
| v1 | `9a8fe34` | 24 | 3 covered / 2 partial / 5 blocked |
| v2 | `e54d296` | 38 | 8 covered / 1 partial / 1 blocked |
| **v3 (current)** | **`c1de1ae`** | **46** | **9 covered / 0 partial / 1 blocked** |

v3 adds the `durable_dispatch` family: the runner now drives the real
`CareerAgentRuntimeDispatcher` into the real `CareerAgentHitlService` over a throwaway
SQLite checkpoint store, so `Ranking → HITL → Gap` is covered by a real durable run
rather than a stub.

---

## Current coverage ledger

| # | PRD §15.3 shape | Status | Gap |
|---|---|---|---|
| 1 | `Ranking → Finish` | covered | — |
| 2 | `Ranking → HITL → Gap` | **covered** | — |
| 3 | `Ranking → Gap → Preparation` | covered | — |
| 4 | `Tool empty → clarification` | covered | — |
| 5 | `invalid params → corrected retry` | covered | — |
| 6 | `transient error → bounded retry` | covered | — |
| 7 | `unknown tool → replan → recover/fail` | covered | — |
| 8 | `same tool loop → stopped` | covered | — |
| 9 | `stale → terminate` | covered | — |
| 10 | `cost action → PendingAction` | **blocked** | GAP-1 |

`prd_153_case_minimum_met = True` (46 ≥ 30).
`prd_153_shape_coverage_complete = False` — **GAP-1 is the only remaining shape.**

### GAP-1 — no registered tool can require cost or human approval

All three registry tools report `side_effect=read_only, cost=none, gate=none`, so the
`pending_action` branch is unreachable from a user message even though
`CareerAgentExecutionGate` implements it.

This is deliberately **not** worked around. Per the agreed product boundary: add a
cost-gated tool only when a real, mature, provider-backed workflow legitimately belongs
in the registry. Manufacturing a fake paid tool to turn this cell green would destroy
the meaning of the gate.

---

## How the durable HITL dispatch leg is driven

`durable_dispatch` cases drive the real chain:

```
CareerIntent(goals=(rank_jobs, review_gaps))
  → CareerAgentRuntimeDispatcher.run
  → CareerAgentHitlService.start        (real SQLite checkpoint store)
  → Ranking workflow                    (real)
  → durable interrupt
  → CareerAgentHitlService.resume       (constructed FRESH over the same SQLite file)
  → stale validation readback           (ranking invoked a second time)
  → Gap workflow                        (real)
  → completed
```

**The resume always runs through a newly constructed `CareerAgentHitlService` over the
same SQLite path.** If the interrupt only lived in memory, the resume would fail — so a
passing case is direct evidence of real durable persistence, not just of a service
object surviving in a fixture.

The governed loop is a *spy*: every durable case asserts `governed_loop_invocations == 0`,
which is what proves the handoff replaces the loop instead of double-running Ranking.

### Observed behaviour (frozen in the cohort)

| Case | Decision | Observed |
|---|---|---|
| `traj-dispatch-01` | approve, `topN=1` | `interrupted` → `completed` / `skill_gap_completed`, confirmed `job-1`, ranking **2**, gaps **1**, governed **0** |
| `traj-dispatch-02` | approve, `topN=2` of 3 | proposed and confirmed `job-1, job-2` |
| `traj-dispatch-03` | edit → `job-2` | confirmed `job-2` (the human's edit, not the proposal) |
| `traj-dispatch-04` | **reject** | `cancelled` / `target_cohort_rejected`, confirmed `()`, gaps **0** — the Gap workflow is never reached |
| `traj-dispatch-05` | goals `(rank_jobs, review_gaps, prepare_job)` | route = **governed_loop**, governed 1, ranking 0 |
| `traj-dispatch-06` | goals `(review_gaps, rank_jobs)` | route = **governed_loop**, governed 1, ranking 0 |
| `traj-dispatch-07` | referenced job outside run scope | `CareerIntentValidationError`, ranking/gaps/governed all **0** |
| `traj-dispatch-08` | no governed job scope | `dispatch_error`, ranking/gaps/governed all **0** |

Two findings worth keeping visible:

1. **Dispatch is order-sensitive.** `(rank_jobs, review_gaps)` goes to durable HITL, but
   `(review_gaps, rank_jobs)` and `(rank_jobs, review_gaps, prepare_job)` go to the
   governed loop. The dispatcher matches an exact goal tuple, not a set. Cases 05 and 06
   pin that boundary so it cannot drift silently.
2. **Every dispatch error fails closed before execution** — zero Ranking, zero Gap, zero
   governed-loop calls. Cases 07 and 08 pin it.
3. **`ranking_invocations == 2` on the approve path** is expected: the initial Ranking plus
   the stale-validation readback. It is asserted explicitly so a future change to stale
   validation cannot silently change the trajectory.

## Composition (46 cases / 16 families)

| Family | Cases | Terminal outcome |
|---|---|---|
| `completed_single` | 3 | `completed` — one tool |
| `completed_multi` | 3 | `completed` — two tools, order preserved |
| `completed_triple` | 2 | `completed` — three tools, order preserved |
| `clarification` | 2 | `clarification_required` (intent asked) |
| `tool_empty` | 2 | `clarification_required` (no tool selected) |
| `unsupported` | 2 | `unsupported` |
| `blocked` | 2 | `blocked` |
| `invalid_intent_output` | 2 | `failed` / `invalid_intent_output` |
| `invalid_tool_params` | 4 | `failed` / `invalid_tool_params` |
| `loop_detected` | 2 | `failed` / `loop_detected` |
| `budget_exhausted` | 2 | `failed` / `budget_exhausted` |
| `transient_retry` | 3 | 2 recovered, 1 bounded failure |
| `corrected_retry` | 3 | recovered `completed` |
| `unknown_tool_replan` | 3 | 2 recovered, 1 bounded failure |
| `stale_terminate` | 3 | `failed` / `stale_state` |
| **`durable_dispatch`** | **8** | 4 × `durable_hitl`, 2 × `governed_loop`, 2 × dispatch error |

## Case schema — dispatch fields

```json
{
  "id": "traj-dispatch-01",
  "family": "durable_dispatch",
  "driver": "durable_dispatch",
  "shapes": ["ranking_hitl_gap"],
  "message": "先选最值得投的，再确认后分析差距。",
  "context": { "runJobIds": ["job-1", "job-2"] },
  "intent": { "goals": ["rank_jobs", "review_gaps"], "...": "..." },
  "dispatch": { "threadId": "thread-traj-dispatch-01", "runId": "run-...",
                "requestId": "request-...", "topN": 1, "resume": "approve" },
  "expected": {
    "status": "durable_hitl",
    "errorCode": null,
    "trace": [],
    "toolResults": 0,
    "workflowInvocations": 3,
    "dispatch": {
      "dispatchKind": "durable_hitl",
      "startStatus": "interrupted", "startStep": "target_cohort_confirmation",
      "interruptPersisted": true, "proposedTargetJobIds": ["job-1"],
      "resumeStatus": "completed", "resumeStep": "skill_gap_completed",
      "confirmedTargetJobIds": ["job-1"],
      "rankingInvocations": 2, "gapInvocations": 1,
      "governedLoopInvocations": 0, "providerCalls": 0
    }
  }
}
```

`driver` defaults to `governed_loop`, so the 38 governed-loop cases are unchanged.
`trace` must be **empty** for dispatch cases: their trace is derived from observed state
(`dispatch:… > start:… > step:… > interrupt:… > ranking:… > gaps:… > governed:… >
provider:… > resume:… > resume_step:… > confirmed:…`) and must never be hand-authored.
Dispatch cases may not carry governed-loop injections (`staleChecks`, `transientFaults`,
`recoveryPlans`, `replanGoals`) or `plannedRequests`, and the loader enforces that.

## Gate-level invariants

- `unclassified_errors == 0`
- `trace_leaks == 0` — closed vocabularies for both drivers, sha256-only fingerprints
- `unstable_traces == 0` — replay determinism across two identical runs
- `provider_attempts == provider_completed == business_writes == 0`

## Run

```bash
cd services/backend
uv run pytest -q tests/test_career_trajectory_eval.py
```

---

## Findings handed to Core

1. **`GAP-6` is closed by a real durable run, but the dispatcher's route is a brittle exact
   tuple match.** `intent.goals == (RANK_JOBS, REVIEW_GAPS)` means a natural multi-goal turn
   such as `(rank_jobs, review_gaps, prepare_job)` silently falls back to the governed loop.
   That may be intended, but it is worth a deliberate decision recorded in the dispatcher,
   because the difference is invisible to the user.
2. **A corrected plan must also change `normalizedParams`** (carried over from v2). Loop
   detection keys on `(tool, arguments_fingerprint, input_fingerprint)`, and
   `arguments_fingerprint` derives from `normalized_params`. A recovery that only changes the
   request is rejected as `loop_detected`.
3. **`fact_fingerprint` is now validated** as a 64-char lowercase sha256 digest — earlier
   finding closed.
4. **A missing plan still loses tool attribution** (`failed` with no tool vs `failed:<tool>`
   for an argument rejection, both under `invalid_tool_params`). Frozen as-is.

## Boundary with the vNext 1.0 trajectory cohort

The vNext 1.0 `LG-3` gate covers 20 durable LangGraph trajectories. This cohort overlaps it
only in the dispatch leg, and asserts things LG-3 does not: the dispatcher route decision,
that the governed loop is **not** invoked, the order-sensitivity boundary, and replay
determinism of the dispatch trace.
