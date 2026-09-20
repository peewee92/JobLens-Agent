# Trajectory / Trace Replay Eval — vNext 1.1 (Agent B)

Frozen cohort for the vNext 1.1 governed-loop trajectory gate (PRD §15.3 / §16).

- Dataset: `career-trajectory-v1.jsonl` (**38 cases**, 15 trace families)
- Runner: `services/backend/app/evals/career_trajectory.py`
- Tests: `services/backend/tests/test_career_trajectory_eval.py`
- Core under test: `app/agent/governed_loop_runtime.py`

---

## Revision history

| Revision | Core baseline | Coverage | Note |
|---|---|---|---|
| v1 | `9a8fe34` | 3 covered / 2 partial / 5 blocked | Original cohort (24 cases). Reported that the loop is single-pass with no retry/replan/stale. |
| **v2 (current)** | **`e54d296`** | **8 covered / 1 partial / 1 blocked** | Re-run after Agent A's release-gate blocker remediation. GAP-3/5/7/8 closed; cohort grown to 38 cases to meet PRD §15.3's ≥30. |

Case IDs are stable across revisions except for the 14 added in v2.

---

## Current coverage ledger

| # | PRD §15.3 shape | Status | Gap |
|---|---|---|---|
| 1 | `Ranking → Finish` | covered | — |
| 2 | `Ranking → HITL → Gap` | **partial** | GAP-6 |
| 3 | `Ranking → Gap → Preparation` | covered | — |
| 4 | `Tool empty → clarification` | covered | — |
| 5 | `invalid params → corrected retry` | covered | — |
| 6 | `transient error → bounded retry` | covered | — |
| 7 | `unknown tool → replan → recover/fail` | covered | — |
| 8 | `same tool loop → stopped` | covered | — |
| 9 | `stale → terminate` | covered | — |
| 10 | `cost action → PendingAction` | **blocked** | GAP-1 |

`prd_153_case_minimum_met = True` (38 ≥ 30).
`prd_153_shape_coverage_complete = False` — one partial and one blocked remain, so the
vNext 1.1 trajectory Release Gate is still **not** fully met.

### The two remaining gaps

**GAP-6 — `Ranking → HITL → Gap` is only half-representable.**
The two-tool ordering `Ranking → Gap` is covered, but the HITL interrupt between them is
not: `CareerAgentGovernedLoopStatus` has no interrupt state and the runtime has no resume
path. HITL lives in the vNext 1.0 LangGraph durable runtime. This needs a product decision
about whether vNext 1.1 should re-expose HITL, not a Core patch.

**GAP-1 — no registered tool can require cost or human approval.**
All three registry tools report `side_effect=read_only, cost=none, gate=none`, so the
`pending_action` branch is unreachable from a user message even though
`CareerAgentExecutionGate` implements it. Per Agent A's guidance this must **not** be
faked: add a cost-gated tool only when a real mature provider workflow legitimately
belongs in the registry.

---

## What the remediated shapes now prove

| Shape | Observed trace | Business-code reach |
|---|---|---|
| `tool_empty → clarification` | `intent_routed > clarification` | 0 — no tool executes |
| `invalid params → corrected retry` | `intent_routed > tool_selected:X > recovery:X > tool_called:X > tool_result:X > finished` | 1 |
| `transient error → bounded retry` | `… > tool_selected:X > recovery:X > tool_called:X > tool_result:X > finished` | 2 (one faulted attempt + one success) |
| `transient error` exhausted | `… > tool_selected:X > recovery:X > failed:X` (`transient_network`) | 2, then terminal |
| `unknown tool → replan` | `intent_routed > recovery > tool_selected:X > … > finished` | 1 |
| `unknown tool` exhausted | `intent_routed > recovery > failed` (`unknown_tool`) | 0 |
| `stale → terminate` before execution | `intent_routed > tool_selected:X > failed:X` (`stale_state`) | **0** |
| `stale` **after** a transient recovery | `… > tool_selected:X > recovery:X > failed:X` (`stale_state`) | **1** — the retry is stopped before it re-executes |
| `stale` on a later tool | `… > tool_result:rank > tool_selected:gaps > failed:gaps` | 1 — partial results preserved |

The third-to-last row is the one that matters most: it is the direct evidence that Core
closes the window where facts change *during* recovery. The workflow ran once for the
faulted attempt and was **not** re-entered after staleness was detected.

## Case schema (v2 additions)

```json
{
  "id": "traj-stale-02",
  "family": "stale_terminate",
  "message": "Rank these unless the facts shift mid-retry.",
  "shapes": ["stale_terminate"],
  "context": { "runJobIds": ["job-1", "job-2"] },
  "intent": { "goals": ["rank_jobs"], "...": "..." },
  "plannedRequests": [ { "tool": "rank_match_reports", "...": "..." } ],
  "staleChecks": [false, true],
  "transientFaults": { "rank_match_reports": [true] },
  "expected": {
    "status": "failed",
    "errorCode": "stale_state",
    "trace": ["intent_routed", "tool_selected:rank_match_reports",
              "recovery:rank_match_reports", "failed:rank_match_reports"],
    "toolResults": 0,
    "workflowInvocations": 1
  }
}
```

Injection fields (all optional, each restricted to its family by loader validation):

| Field | Family | Meaning |
|---|---|---|
| `staleChecks` | `stale_terminate` | One boolean per staleness-guard call; past the script the guard reports fresh |
| `transientFaults` | `transient_retry`, `stale_terminate` | One boolean per workflow attempt; `true` raises `ConnectionError` |
| `recoveryPlans` | `corrected_retry` | Plans the recovery planner returns in order, then refuses |
| `replanGoals` | `unknown_tool_replan` | Goal sets the unknown-tool replanner returns in order, then refuses |

`recoveryPlans` and `replanGoals` are what make the retry/replan paths observable with
zero Provider calls: the Eval supplies frozen corrective input, and Core decides whether
to accept it and how to trace it.

## Composition (38 cases / 15 families)

| Family | Cases | Terminal outcome |
|---|---|---|
| `completed_single` | 3 | `completed` — one tool |
| `completed_multi` | 3 | `completed` — two tools, order preserved |
| `completed_triple` | 2 | `completed` — three tools, order preserved |
| `clarification` | 2 | `clarification_required` (intent already asked) |
| `tool_empty` | 2 | `clarification_required` (no tool selected) |
| `unsupported` | 2 | `unsupported` |
| `blocked` | 2 | `blocked` |
| `invalid_intent_output` | 2 | `failed` / `invalid_intent_output` |
| `invalid_tool_params` | 4 | `failed` / `invalid_tool_params` (no recovery planner) |
| `loop_detected` | 2 | `failed` / `loop_detected` |
| `budget_exhausted` | 2 | `failed` / `budget_exhausted` mid-trajectory |
| `transient_retry` | 3 | 2 recovered, 1 bounded failure |
| `corrected_retry` | 3 | recovered `completed` |
| `unknown_tool_replan` | 3 | 2 recovered, 1 bounded failure |
| `stale_terminate` | 3 | `failed` / `stale_state` |

## Gate-level invariants

A single violation fails the whole gate:

- `unclassified_errors == 0` — the runtime must fail through a governed result
- `trace_leaks == 0` — closed vocabulary (`intent_routed`, `clarification`, `unsupported`,
  `blocked`, `recovery`, `tool_selected`, `tool_called`, `pending_action`, `tool_result`,
  `failed`, `finished`) and sha256-only fingerprints
- `unstable_traces == 0` — replay determinism across two identical runs
- `provider_attempts == provider_completed == business_writes == 0`

## Run

```bash
cd services/backend
uv run pytest -q tests/test_career_trajectory_eval.py
```

---

## Findings handed to Core (still open)

1. **A corrected plan must also change `normalizedParams`.**
   `CareerAgentLoopGuard.record_tool_call` keys loop detection on
   `(tool, arguments_fingerprint, input_fingerprint)`, and `arguments_fingerprint` is derived
   from `plan.normalized_params`. A recovery planner that returns a corrected request without
   changing `normalized_params` is therefore rejected as `loop_detected` and the recovery is
   lost. This was observed while authoring `traj-correct-03` and is frozen in the cohort by
   giving the recovered plan distinct normalized params.
   *Recommendation:* either document this as a hard requirement of
   `CareerAgentLoopRecoveryPlanner`, or include the full request payload in the loop key.

2. **`fact_fingerprint` is now validated — earlier finding closed.**
   `CareerAgentPlannedToolRequest.__post_init__` now requires a 64-character lowercase
   sha256 digest, so the previous "raw text could be persisted into the trace" risk is gone.

3. **A missing plan still loses tool attribution.**
   `plan is None` yields `failed` with no tool, whereas an argument rejection yields
   `failed:<tool>` — both under `invalid_tool_params`. Frozen as-is.

## Boundary with the vNext 1.0 trajectory cohort

The vNext 1.0 `LG-3` gate (20 cases) covers **LangGraph durable checkpoint** trajectories
over SQLite, including HITL approve/edit/reject and stale transitions. This cohort covers
the **vNext 1.1 governed loop trace** and does not duplicate it.
