# Tool Selection Eval — vNext 1.1 (Agent B)

Frozen deterministic cohort for the vNext 1.1 Tool Selection Release Gate
(PRD `docs/product/P1-career-agent-natural-language-tool-loop-prd.md` §15.2).

- Dataset: `career-tool-selection-v1.jsonl`
- Runner: `services/backend/app/evals/career_tool_selection.py`
- Tests: `services/backend/tests/test_career_tool_selection_eval.py`

## What this gate is, and what it is not

`CareerAgentToolSelector` is a deterministic `CareerIntentGoal → CareerAgentToolName`
map. Feeding it a correct intent therefore proves nothing about model quality.

This gate is a **deterministic contract gate**. With zero Provider calls and zero
business writes it proves:

- exact **ordered** tool selection, including multi-goal turns where goals must not
  be collapsed or reordered;
- **fail-closed** handling of goals with no registered tool — including the case
  where a valid goal was already selected before the invalid one appears, so no
  partial selection may leak;
- that Tool Selection **never widens governed job scope**;
- that malformed arguments are **rejected before any workflow executes**;
- the **read-only governance envelope** of every selectable tool.

It does **not** measure model-quality selection accuracy (correct vs unnecessary
tool chosen by a planner, or no-tool answers when facts already suffice). Those
require a Provider and are a separate, explicitly authorized gate. PRD §16's
"Intent goal accuracy ≥ 95%" belongs to that gate, not to this one.

## Composition (44 cases)

| Category | Cases | Terminal outcome asserted |
|---|---|---|
| `correct_tool` | 10 | `selected` (2 multi-goal, 1 triple-goal, order preserved) |
| `forbidden_tool` | 8 | `forbidden_goal` (`review_application`, `unknown`) |
| `unnecessary_tool` | 6 | `no_tool` / `sufficient_facts` |
| `wrong_job_scope` | 8 | 5 × `rejected_by_contract`, 3 × `no_tool` / `clarification` |
| `wrong_argument` | 6 | `invalid_argument` (2 per registered tool) |
| `no_tool_answer` | 6 | 3 × `clarification`, 3 × `unsupported` |

Release minimums are enforced by `validate_career_tool_selection_release_dataset`;
a smaller or skewed cohort cannot claim the gate. Case IDs are stable and unique,
and messages are unique because the replay oracle is keyed by message.

## Case schema

```json
{
  "id": "correct-07",
  "category": "correct_tool",
  "message": "Rank these, then tell me the gaps.",
  "context": { "runJobIds": ["job-301", "job-302"] },
  "intent": {
    "goals": ["rank_jobs", "review_gaps"],
    "referenced_job_ids": [],
    "current_job_required": false,
    "needs_clarification": false,
    "clarification_question": null,
    "unsupported_request": null
  },
  "expected": { "outcome": "selected", "tools": ["rank_match_reports", "target_cohort_gaps"], "reason": null }
}
```

- `intent` is the frozen oracle payload fed to the **real** `CareerIntentRouter`
  model seam. It is not a prediction.
- `context` is the only governed scope the turn may use.
- `expected.outcome` classifies the terminal result; `expected.tools` asserts what
  the selector selected; `expected.reason` is only set for `no_tool`.
- `argumentProbe` (only on `wrong_argument` cases) carries a deliberately malformed
  request that the **real** `CareerAgentToolRegistry` must reject before invoking
  the workflow.

## Outcome vocabulary

| Outcome | Meaning |
|---|---|
| `selected` | Selector returned one or more registered tools, in goal order |
| `no_tool` | Selector returned no tool; `reason` distinguishes facts/clarification/unsupported |
| `forbidden_goal` | Goal has no registered tool; selector raised, nothing leaked |
| `rejected_by_contract` | Core intent contract rejected the turn before selection |
| `invalid_argument` | Tool was selected but the request was rejected pre-execution |

## Enforced safety invariants

- Provider attempts / completions = 0
- Business writes = 0
- **Workflow invocations = 0** — the registry is never reached with an acceptable
  request, so no business code runs during this gate
- Every selected tool must be `read_only` / `provider_cost: none` /
  `human_gate: none` / `idempotency: read_only`

## Run

```bash
cd services/backend
uv run pytest -q tests/test_career_tool_selection_eval.py
```

No live Provider, real SQLite runtime DB, profile/job data, or business state is
used by this Eval.

## Known contract gaps surfaced

1. **No registered tool can exercise `cost action → PendingAction`.** All three
   registry definitions declare `human_gate_requirement: none` and
   `provider_cost_class: none`, so PRD §15.3's cost-approval trajectory shape
   cannot be produced end-to-end from a user message. `CareerAgentExecutionGate`
   itself does implement the pending-action path — the gap is in the registry's
   tool set, and it is handed to Core rather than worked around here.
2. **Model-quality selection accuracy is unmeasured** by this gate and needs a
   separately authorized Provider run.
