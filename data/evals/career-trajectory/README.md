# Trajectory / Trace Replay Eval — vNext 1.1 (Agent B)

Frozen cohort for the vNext 1.1 governed-loop trajectory gate (PRD §15.3 / §16).

- Dataset: `career-trajectory-v1.jsonl` (24 cases)
- Runner: `services/backend/app/evals/career_trajectory.py`
- Tests: `services/backend/tests/test_career_trajectory_eval.py`
- Core under test: `app/agent/governed_loop_runtime.py`

---

## Headline finding: the vNext 1.1 loop is not a retry loop

PRD §15.3 lists **ten** multi-turn trajectory shapes and requires **at least 30 cases**.
Empirical probing of the frozen `CareerAgentGovernedLoopRuntime` shows it is a
**single-pass, ordered, bounded executor**:

> `run()` iterates the selected tools **exactly once**. There is no retry loop, no
> replan step, no interrupt/resume, no stale detection, and no cost- or
> approval-gated tool.

Therefore only **3 of the 10 shapes are fully reachable**, 2 are reachable in part,
and **5 cannot be produced end to end**. This gate reports that through a
machine-checked ledger (`career_trajectory_shape_coverage()`) rather than
manufacturing cases that would fake coverage.

**The gate therefore explicitly reports `prd_153_shape_coverage_complete = False`
and `prd_153_case_minimum_met = False`. vNext 1.1's trajectory Release Gate is NOT
met, and this cohort must not be cited as evidence that it is.**

### Shape coverage ledger

| # | PRD §15.3 shape | Status | Gap |
|---|---|---|---|
| 1 | `Ranking → Finish` | **covered** | — |
| 2 | `Ranking → HITL → Gap` | partial | GAP-6 |
| 3 | `Ranking → Gap → Preparation` | **covered** | — |
| 4 | `Tool empty → clarification` | **blocked** | GAP-5 |
| 5 | `invalid params → corrected retry` | partial | GAP-7 |
| 6 | `transient error → bounded retry` | **blocked** | GAP-7 |
| 7 | `unknown tool → replan → recover/fail` | **blocked** | GAP-8 |
| 8 | `same tool loop → stopped` | **covered** | — |
| 9 | `stale → terminate` | **blocked** | GAP-3 |
| 10 | `cost action → PendingAction` | **blocked** | GAP-1 |

Every non-covered entry carries a reason and a gap id in code, and a test enforces
that, so the ledger cannot silently drift.

### Why each blocked/partial shape cannot be produced

| Gap | Shape | Observed evidence | Why |
|---|---|---|---|
| GAP-5 | `Tool empty → clarification` | empty goals → `status=completed`, `trace=intent_routed > finished` | An intent that selects no tool **completes silently**. `clarification_required` is only reachable when the intent already carries `needs_clarification`, so "tool empty implies clarification" is not implemented. |
| GAP-6 | `Ranking → HITL → Gap` | rank+gaps → `completed` | The two-tool ordering is covered, but **no interrupt/resume state exists** in the 1.1 loop. HITL lives in the vNext 1.0 LangGraph durable runtime. |
| GAP-7 | `transient error → bounded retry`, `invalid params → corrected retry` | malformed args → `failed/invalid_tool_params` | Invalid params fail closed structurally, but **nothing re-invokes a tool**. A corrected retry would have to be caller-driven across separate runs. |
| GAP-8 | `unknown tool → replan` | unregistered goal → `failed/**invalid_tool_params**` | A selection failure is caught as a plan error, so `CareerAgentLoopErrorCode.UNKNOWN_TOOL` is **unreachable on this path** — and there is no replan step. |
| GAP-3 | `stale → terminate` | no stale status, code, or check | Staleness is detected in the vNext 1.0 LangGraph path. Core must decide where staleness is detected before this can be evaluated in the 1.1 loop. |
| GAP-1 | `cost action → PendingAction` | all 3 tools report `side_effect=read_only, cost=none, gate=none` | `CareerAgentExecutionGate` **does** implement the pending-action path, but no registered tool can require cost or approval, so the branch is unreachable from a user message. |

---

## What this gate does prove

For the 24 reachable trajectories, with **zero Provider calls and zero business writes**:

- exact terminal status and **ordered trace events** (24 cases, 10 trace families);
- the trace vocabulary is **closed** — no chain-of-thought or unknown event can appear;
- every trace fingerprint is a sha256 digest, so no raw message/JD/Resume text is persisted;
- **trace replay determinism** — identical frozen input yields identical trace fingerprints;
- business code is reached **exactly** when the trajectory says so (8 trajectories must reach it 0 times).

### Composition (24 cases / 10 trace families)

| Family | Cases | Terminal outcome |
|---|---|---|
| `completed_single` | 3 | `completed` — one tool |
| `completed_multi` | 3 | `completed` — two tools, order preserved |
| `completed_triple` | 2 | `completed` — three tools, order preserved |
| `clarification` | 2 | `clarification_required` |
| `unsupported` | 2 | `unsupported` |
| `blocked` | 2 | `blocked` (context not usable) |
| `invalid_intent_output` | 2 | `failed` / `invalid_intent_output` |
| `invalid_tool_params` | 4 | `failed` / `invalid_tool_params` (4 distinct causes) |
| `loop_detected` | 2 | `failed` / `loop_detected` |
| `budget_exhausted` | 2 | `failed` / `budget_exhausted` mid-trajectory |

## Gate-level invariants

A single violation fails the whole gate:

- `unclassified_errors == 0` — the runtime must fail through a governed result
- `trace_leaks == 0` — closed vocabulary and sha256-only fingerprints
- `unstable_traces == 0` — replay determinism
- `provider_attempts == provider_completed == business_writes == 0`

## Case schema

```json
{
  "id": "traj-loop-01",
  "family": "loop_detected",
  "message": "Rank these and rank them again.",
  "shapes": ["same_tool_loop_stopped"],
  "context": { "runJobIds": ["job-1", "job-2"] },
  "intent": {
    "goals": ["rank_jobs", "rank_jobs"],
    "referenced_job_ids": [],
    "current_job_required": false,
    "needs_clarification": false,
    "clarification_question": null,
    "unsupported_request": null
  },
  "plannedRequests": [
    { "tool": "rank_match_reports",
      "factFingerprint": "<sha256>",
      "normalizedParams": [["job_ids", "job-1|job-2"]],
      "request": { "kind": "rank_match_reports", "jobIds": ["job-1", "job-2"] } }
  ],
  "expected": {
    "status": "failed",
    "errorCode": "loop_detected",
    "trace": ["intent_routed",
              "tool_selected:rank_match_reports", "tool_called:rank_match_reports",
              "tool_result:rank_match_reports",
              "tool_selected:rank_match_reports", "failed:rank_match_reports"],
    "toolResults": 1,
    "workflowInvocations": 1
  }
}
```

Trace events are rendered as `event` or `event:tool`. `tool_selected`, `tool_called`,
`pending_action` and `tool_result` **must** name their tool; `failed` **may** name its
tool. `budget` keys are the Core `CareerAgentLoopBudget` field names verbatim
(snake_case), as in the Loop Guard cohort.

## Run

```bash
cd services/backend
uv run pytest -q tests/test_career_trajectory_eval.py
```

## Additional findings handed to Core

1. **`fact_fingerprint` is persisted verbatim and never validated.**
   `CareerAgentPlannedToolRequest.fact_fingerprint` only has to be non-empty, and the
   runtime copies it into the trace as `input_fingerprint`. A caller that passed raw
   JD or Resume text would therefore write it straight into the trace. This cohort
   supplies sha256 values to pin the intended contract, but the runtime does not
   enforce it. (Severity: low today, because the only caller is in-repo.)

2. **Trace attribution is inconsistent for the same error code.**
   A missing plan produces `failed` **without** tool attribution, while an argument
   rejection produces `failed:<tool>` — both under `invalid_tool_params`. Frozen as-is
   in this cohort; flagged so Core can make attribution uniform or declare it intentional.

3. **A duplicated goal is the only way to trigger `loop_detected` here.**
   Because each goal maps to a distinct tool, the repeat-call guard can only fire when
   the intent itself repeats a goal. This is worth confirming as intended.

## Boundary with the vNext 1.0 trajectory cohort

The vNext 1.0 `LG-3` gate (`data/evals/` + `app/evals/career_agent_runtime*.py`, 20 cases)
covers **LangGraph durable checkpoint** trajectories over SQLite, including HITL
approve/edit/reject and stale transitions. This cohort covers the **vNext 1.1 governed
loop trace** and does not duplicate it. Case IDs are unique across both cohorts.
