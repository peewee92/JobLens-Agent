# Loop Guard Eval — vNext 1.1 (Agent B)

Frozen deterministic cohort for the vNext 1.1 bounded-loop Release Gate.

- Dataset: `career-loop-guard-v1.jsonl`
- Runner: `services/backend/app/evals/career_loop_guard.py`
- Tests: `services/backend/tests/test_career_loop_guard_eval.py`
- Core under test: `app/agent/tool_loop.py` (`CareerAgentLoopGuard`, `CareerAgentLoopBudget`)

## What this gate adds over the Core unit tests

Core already unit-tests each mechanism in isolation
(`tests/test_career_agent_tool_loop.py`). This gate deliberately does **not** repeat that.
It exists for what unit tests cannot express:

| Added value | Why a unit test cannot cover it |
|---|---|
| Frozen all-cases cohort with release minimums | A per-unit test cannot stop a skewed or shrunken cohort from claiming the gate |
| **No false stops** (`healthy_progress`) | Nothing in the Core suite asserts the guard *refuses* to stop; an over-conservative guard would regress silently |
| **No unclassified stops** | Proves every stop arrives as a structured `CareerAgentLoopError` with a code, never as a leaked raw exception |
| Exactly-at-budget boundary | Core tests cover exceeding the budget; using it in full must stay legal |
| Per-error-code retry independence | Core covers one code; budgets are keyed per code and that must not silently become global |
| Non-retryable bypasses the retry budget | `max_retries=5` must not resurrect a non-retryable failure |

This gate is deterministic: **zero Provider calls, zero business writes**.

## Composition (26 cases)

| Category | Cases | Terminal outcome |
|---|---|---|
| `max_turns` | 3 | 2 × `budget_exhausted`, 1 × no stop (exactly at budget) |
| `max_tool_calls` | 3 | 2 × `budget_exhausted`, 1 × no stop (exactly at budget) |
| `provider_budget` | 2 | `budget_exhausted` (default budget allows zero provider calls) |
| `retry_bound` | 3 | never stops; asserts retry normalisation outcomes |
| `same_tool` | 3 | 2 × `loop_detected`, 1 × no stop (retry within the bound) |
| `no_progress` | 3 | 1 × `no_progress`, 2 × no stop |
| `unknown_tool` | 3 | never stops; retryable exactly once then terminal |
| `invalid_tool_params` | 3 | never stops; retryable exactly once, non-retryable honoured immediately |
| `healthy_progress` | 3 | **no stop** — the anti-false-stop dimension |

Of the 26 cases, 9 stop and 17 must not. A guard that stops more than this fails the gate.

Notable `healthy_progress` cases:

- `healthy-02` consumes the **entire default budget** (6 turns, 8 tool calls, 22 steps) and
  must still not stop.
- `healthy-03` repeats the same tool with the same arguments but a different input
  fingerprint — a legitimate re-run after new facts, not a loop.

## Case schema

```json
{
  "id": "turns-01",
  "category": "max_turns",
  "budget": { "max_turns": 3 },
  "steps": [{ "type": "turn" }, { "type": "turn" }, { "type": "turn" }, { "type": "turn" }],
  "expected": {
    "stopped": true,
    "stopCode": "budget_exhausted",
    "stopRetryable": false,
    "turnsUsed": 3,
    "toolCallsUsed": 0,
    "providerBudgetUsed": 0,
    "retryOutcomes": [],
    "stepsApplied": 3
  }
}
```

Step types: `turn`, `provider_call`, `tool_call` (`tool` / `argumentsFingerprint` /
`inputFingerprint` / `transientRetry`), `observation` (`stateFingerprint` /
`blockerFingerprint` / `factFingerprint`), `error` (`errorCode` / `errorRetryable`).

**`budget` keys are the Core `CareerAgentLoopBudget` field names verbatim** (snake_case),
so a case maps directly onto `dataclasses.replace(CareerAgentLoopBudget(), **budget)`.
This differs from the camelCase used for Eval-owned fields elsewhere in `data/evals`, and it
is intentional: the budget object is Core's schema, not this Eval's.

`providerBudgetUsed` counts **guard-level provider-call slots consumed**. It is not real
provider activity — the report-level `provider_attempts` / `provider_completed` are always 0.

## Enforced invariants

Gate-level (a single violation fails the whole gate):

- `unclassified_errors == 0` — no raw exception may escape the guard
- `retryable_stops == 0` — a stop must always be terminal
- `healthy_cases_stopped == 0` — no false stop
- `provider_attempts == provider_completed == business_writes == 0`

## Core constraint discovered by this gate

`CareerAgentLoopBudget` requires `max_same_tool_consecutive <= max_tool_calls`. Lowering
`max_tool_calls` without also lowering the same-tool bound raises a raw `ValueError` from
budget construction. The gate caught this during authoring and reports it as an
unclassified error — which is the correct, visible failure mode. Cohort cases now respect
the coupling; no Core change is requested.

## Run

```bash
cd services/backend
uv run pytest -q tests/test_career_loop_guard_eval.py
```

## Findings handed to Core

1. **`stale → terminate` has no representation in the loop guard.** `CareerAgentLoopErrorCode`
   has no stale code, and the guard has no stale concept. That trajectory shape belongs to the
   vNext 1.0 durable runtime path, not to the vNext 1.1 bounded loop. Cycle 4 cannot cover it
   here without Core deciding where staleness is detected.
2. **`unknown tool → replan` is only half-verified.** The guard classifies `unknown_tool` as
   retryable exactly once and then terminal (`unknowntool-01/02`), so a single replan is
   *enabled*. Whether the runtime actually replans, rather than failing, is unverified and
   belongs to the Cycle 4 trajectory gate.
