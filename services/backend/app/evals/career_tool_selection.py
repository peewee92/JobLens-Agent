"""Deterministic vNext 1.1 Tool Selection Eval.

This module owns the Eval boundary only.  It consumes Agent A's frozen Core
chain unchanged -- ``CareerIntentRouter`` -> ``CareerAgentToolSelector`` ->
``CareerAgentToolRegistry`` -- and never implements a second router, selector,
or tool registry of its own.

A Tool Selection gate must not be satisfied by the coarse-grained goal-to-tool
map alone: the selector is deterministic, so feeding it a correct intent proves
nothing about model quality.  What this gate does prove, with zero Provider
calls and zero business writes, is contract behaviour: exact ordered selection,
fail-closed handling of unregistered goals, non-widening of governed job scope,
argument rejection before any workflow runs, and the read-only governance
envelope of every selectable tool.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Mapping

from app.agent.context import CareerAgentContext, CareerAgentJobContext
from app.agent.intent import (
    CareerIntentResolutionContext,
    CareerIntentRouter,
    CareerIntentValidationError,
)
from app.agent.tool_registry import (
    CareerAgentHumanGateRequirement,
    CareerAgentIdempotencyClass,
    CareerAgentProviderCostClass,
    CareerAgentSideEffectClass,
    CareerAgentToolAccess,
    CareerAgentToolDefinition,
    CareerAgentToolError,
    CareerAgentToolName,
    CareerAgentToolRegistry,
    CareerAgentToolRequest,
    JobPreparationRequest,
    RankMatchReportsRequest,
    TargetCohortGapsRequest,
)
from app.agent.tool_selection import (
    CareerAgentToolSelectionError,
    CareerAgentToolSelector,
)


class ToolSelectionEvalCategory(StrEnum):
    CORRECT_TOOL = "correct_tool"
    FORBIDDEN_TOOL = "forbidden_tool"
    UNNECESSARY_TOOL = "unnecessary_tool"
    WRONG_JOB_SCOPE = "wrong_job_scope"
    WRONG_ARGUMENT = "wrong_argument"
    NO_TOOL_ANSWER = "no_tool_answer"


class ToolSelectionEvalOutcome(StrEnum):
    """Terminal classification of one selection turn."""

    SELECTED = "selected"
    NO_TOOL = "no_tool"
    FORBIDDEN_GOAL = "forbidden_goal"
    REJECTED_BY_CONTRACT = "rejected_by_contract"
    INVALID_ARGUMENT = "invalid_argument"


class ToolSelectionEvalNoToolReason(StrEnum):
    SUFFICIENT_FACTS = "sufficient_facts"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"


_RELEASE_MINIMUMS: dict[ToolSelectionEvalCategory, int] = {
    ToolSelectionEvalCategory.CORRECT_TOOL: 10,
    ToolSelectionEvalCategory.FORBIDDEN_TOOL: 8,
    ToolSelectionEvalCategory.UNNECESSARY_TOOL: 6,
    ToolSelectionEvalCategory.WRONG_JOB_SCOPE: 8,
    ToolSelectionEvalCategory.WRONG_ARGUMENT: 6,
    ToolSelectionEvalCategory.NO_TOOL_ANSWER: 6,
}
_RELEASE_MINIMUM_TOTAL = sum(_RELEASE_MINIMUMS.values())

_TERMINAL_WITHOUT_TOOLS = (
    ToolSelectionEvalOutcome.NO_TOOL,
    ToolSelectionEvalOutcome.FORBIDDEN_GOAL,
    ToolSelectionEvalOutcome.REJECTED_BY_CONTRACT,
)

_DEFAULT_DATASET_PATH = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "evals"
    / "career-tool-selection"
    / "career-tool-selection-v1.jsonl"
)


@dataclass(frozen=True, slots=True)
class ToolSelectionEvalContext:
    """Grounded identifiers authorized for a single selection turn."""

    current_job_id: str | None = None
    run_job_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolSelectionEvalExpected:
    """Assertions required of the injected Core selection chain."""

    outcome: ToolSelectionEvalOutcome
    tools: tuple[str, ...] = ()
    reason: ToolSelectionEvalNoToolReason | None = None


@dataclass(frozen=True, slots=True)
class ToolSelectionEvalArgumentProbe:
    """A deliberately malformed request used to prove pre-execution rejection."""

    tool: CareerAgentToolName
    request: CareerAgentToolRequest


@dataclass(frozen=True, slots=True)
class ToolSelectionEvalCase:
    case_id: str
    category: ToolSelectionEvalCategory
    message: str
    context: ToolSelectionEvalContext
    intent_payload: Mapping[str, object]
    expected: ToolSelectionEvalExpected
    argument_probe: ToolSelectionEvalArgumentProbe | None = None


@dataclass(frozen=True, slots=True)
class ToolSelectionEvalGovernance:
    """Governance metadata read back from the Core registry definition."""

    tool: str
    access: str
    side_effect_class: str
    provider_cost_class: str
    human_gate_requirement: str
    timeout_class: str
    idempotency_class: str
    requires_current_job: bool
    requires_explicit_feedback_selection: bool


@dataclass(frozen=True, slots=True)
class ToolSelectionEvalExecution:
    """Selection result plus observable side-effect counters for Eval safety."""

    outcome: ToolSelectionEvalOutcome
    tools: tuple[str, ...] = ()
    reason: ToolSelectionEvalNoToolReason | None = None
    governance: tuple[ToolSelectionEvalGovernance, ...] = ()
    detail: str | None = None
    provider_attempts: int = 0
    provider_completed: int = 0
    business_writes: int = 0
    workflow_invocations: int = 0
    violations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolSelectionEvalCaseResult:
    case_id: str
    passed: bool
    failure_reasons: tuple[str, ...]
    governance: tuple[ToolSelectionEvalGovernance, ...]
    provider_attempts: int
    provider_completed: int
    business_writes: int
    workflow_invocations: int


@dataclass(frozen=True, slots=True)
class ToolSelectionEvalReport:
    total_cases: int
    passed_cases: int
    failed_cases: int
    gate_passed: bool
    provider_attempts: int
    provider_completed: int
    business_writes: int
    workflow_invocations: int
    case_results: tuple[ToolSelectionEvalCaseResult, ...]


@dataclass(frozen=True, slots=True)
class ToolSelectionEvalReplayModel:
    """Deterministic frozen oracle for the Core ``CareerIntentModel`` seam.

    It decodes the cohort's frozen expectation instead of predicting intent, and
    it is never a product router: no Provider is contacted and no message is
    interpreted.  Model-quality Tool Selection accuracy is a separate, Provider
    authorized gate and is deliberately not claimed here.
    """

    payloads: Mapping[str, Mapping[str, object]]

    @classmethod
    def from_cases(
        cls,
        cases: tuple[ToolSelectionEvalCase, ...],
    ) -> "ToolSelectionEvalReplayModel":
        return cls(payloads={case.message: case.intent_payload for case in cases})

    def route(self, user_message: str) -> dict[str, object]:
        return dict(self.payloads[user_message])

    def tampered(
        self,
        user_message: str,
        *,
        goals: tuple[str, ...],
    ) -> "ToolSelectionEvalReplayModel":
        """Return a model whose frozen payload is mutated for one message."""

        payload = dict(self.payloads[user_message])
        payload["goals"] = list(goals)
        return ToolSelectionEvalReplayModel(payloads={**self.payloads, user_message: payload})


class ToolSelectionEvalAdapter:
    """Thin adapter from the frozen Core selection chain to the Eval seam."""

    def __init__(
        self,
        *,
        router: CareerIntentRouter,
        selector: CareerAgentToolSelector,
        registry: CareerAgentToolRegistry,
    ) -> None:
        self.router = router
        self.selector = selector
        self.registry = registry

    def run(self, *, case: ToolSelectionEvalCase) -> ToolSelectionEvalExecution:
        context = _build_agent_context(case.context)
        resolution_context = CareerIntentResolutionContext(
            current_job_id=case.context.current_job_id,
            run_job_ids=case.context.run_job_ids,
        )

        try:
            intent = self.router.route(
                user_message=case.message,
                context=resolution_context,
            )
        except CareerIntentValidationError as exc:
            return ToolSelectionEvalExecution(
                outcome=ToolSelectionEvalOutcome.REJECTED_BY_CONTRACT,
                detail=str(exc),
            )

        try:
            selections = self.selector.select(intent)
        except CareerAgentToolSelectionError as exc:
            return ToolSelectionEvalExecution(
                outcome=ToolSelectionEvalOutcome.FORBIDDEN_GOAL,
                detail=str(exc),
            )

        tools = tuple(selection.tool.name.value for selection in selections)
        governance = tuple(_governance(selection.tool) for selection in selections)

        if case.argument_probe is not None:
            return self._probe_arguments(
                case=case,
                context=context,
                tools=tools,
                governance=governance,
            )

        if not tools:
            return ToolSelectionEvalExecution(
                outcome=ToolSelectionEvalOutcome.NO_TOOL,
                reason=_no_tool_reason(intent),
                governance=governance,
            )

        return ToolSelectionEvalExecution(
            outcome=ToolSelectionEvalOutcome.SELECTED,
            tools=tools,
            governance=governance,
        )

    def _probe_arguments(
        self,
        *,
        case: ToolSelectionEvalCase,
        context: CareerAgentContext,
        tools: tuple[str, ...],
        governance: tuple[ToolSelectionEvalGovernance, ...],
    ) -> ToolSelectionEvalExecution:
        probe = case.argument_probe
        assert probe is not None
        try:
            self.registry.invoke(context=context, tool=probe.tool, request=probe.request)
        except CareerAgentToolError as exc:
            return ToolSelectionEvalExecution(
                outcome=ToolSelectionEvalOutcome.INVALID_ARGUMENT,
                tools=tools,
                governance=governance,
                detail=str(exc),
            )
        return ToolSelectionEvalExecution(
            outcome=ToolSelectionEvalOutcome.INVALID_ARGUMENT,
            tools=tools,
            governance=governance,
            workflow_invocations=1,
            violations=(
                "invalid argument probe was unexpectedly accepted by the tool registry",
            ),
        )


def load_career_tool_selection_eval_dataset(
    path: str | Path = _DEFAULT_DATASET_PATH,
) -> tuple[ToolSelectionEvalCase, ...]:
    """Load a versioned JSONL cohort and enforce frozen release minimums."""

    dataset_path = Path(path)
    cases: list[ToolSelectionEvalCase] = []
    case_ids: set[str] = set()
    for line_number, raw_line in enumerate(
        dataset_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid Tool Selection Eval JSONL at line {line_number}"
            ) from exc
        case = _parse_case(payload, line_number=line_number)
        if case.case_id in case_ids:
            raise ValueError(f"duplicate Tool Selection Eval case id: {case.case_id}")
        case_ids.add(case.case_id)
        cases.append(case)

    messages = Counter(case.message for case in cases)
    duplicated_messages = [message for message, count in messages.items() if count > 1]
    if duplicated_messages:
        raise ValueError(
            "Tool Selection Eval messages must be unique because the replay oracle "
            "is keyed by message: " + ", ".join(sorted(duplicated_messages))
        )

    validate_career_tool_selection_release_dataset(tuple(cases))
    return tuple(cases)


def validate_career_tool_selection_release_dataset(
    cases: tuple[ToolSelectionEvalCase, ...],
) -> None:
    """Prevent a smaller or category-skewed dataset from claiming the gate."""

    if len(cases) < _RELEASE_MINIMUM_TOTAL:
        raise ValueError(
            f"Tool Selection Eval requires at least {_RELEASE_MINIMUM_TOTAL} cases"
        )

    duplicate_ids = [
        case_id
        for case_id, count in Counter(case.case_id for case in cases).items()
        if count > 1
    ]
    if duplicate_ids:
        raise ValueError(
            "duplicate Tool Selection Eval case ids: " + ", ".join(sorted(duplicate_ids))
        )

    category_counts = Counter(case.category for case in cases)
    missing = [
        f"{category.value} >= {minimum} (got {category_counts[category]})"
        for category, minimum in _RELEASE_MINIMUMS.items()
        if category_counts[category] < minimum
    ]
    if missing:
        raise ValueError(
            "Tool Selection Eval dataset category minimums failed: " + "; ".join(missing)
        )


def evaluate_career_tool_selections(
    *,
    adapter: ToolSelectionEvalAdapter,
    cases: tuple[ToolSelectionEvalCase, ...],
    require_release_dataset: bool = True,
) -> ToolSelectionEvalReport:
    """Evaluate an injected Core selection chain with fail-closed guardrails."""

    if not cases:
        raise ValueError("Tool Selection Eval requires at least one case")
    if require_release_dataset:
        validate_career_tool_selection_release_dataset(cases)

    results = tuple(_evaluate_case(adapter=adapter, case=case) for case in cases)
    passed_cases = sum(result.passed for result in results)
    return ToolSelectionEvalReport(
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=len(results) - passed_cases,
        gate_passed=passed_cases == len(results),
        provider_attempts=sum(result.provider_attempts for result in results),
        provider_completed=sum(result.provider_completed for result in results),
        business_writes=sum(result.business_writes for result in results),
        workflow_invocations=sum(result.workflow_invocations for result in results),
        case_results=results,
    )


def _evaluate_case(
    *,
    adapter: ToolSelectionEvalAdapter,
    case: ToolSelectionEvalCase,
) -> ToolSelectionEvalCaseResult:
    failure_reasons: list[str] = []
    try:
        execution = adapter.run(case=case)
    except Exception as exc:  # Core chain failures must be represented per case.
        return ToolSelectionEvalCaseResult(
            case_id=case.case_id,
            passed=False,
            failure_reasons=(f"selection chain raised {type(exc).__name__}: {exc}",),
            governance=(),
            provider_attempts=0,
            provider_completed=0,
            business_writes=0,
            workflow_invocations=0,
        )

    _assert_safety_budgets(execution=execution, failures=failure_reasons)
    _assert_expected_outcome(execution=execution, case=case, failures=failure_reasons)
    _assert_governance_envelope(execution=execution, failures=failure_reasons)

    return ToolSelectionEvalCaseResult(
        case_id=case.case_id,
        passed=not failure_reasons,
        failure_reasons=tuple(failure_reasons),
        governance=execution.governance,
        provider_attempts=execution.provider_attempts,
        provider_completed=execution.provider_completed,
        business_writes=execution.business_writes,
        workflow_invocations=execution.workflow_invocations,
    )


def _assert_safety_budgets(
    *,
    execution: ToolSelectionEvalExecution,
    failures: list[str],
) -> None:
    for field_name, actual in (
        ("provider attempts", execution.provider_attempts),
        ("provider completed", execution.provider_completed),
        ("business writes", execution.business_writes),
        ("workflow invocations", execution.workflow_invocations),
    ):
        if actual != 0:
            failures.append(
                f"{field_name} must be 0 during deterministic Tool Selection Eval, got {actual}"
            )
    failures.extend(execution.violations)


def _assert_expected_outcome(
    *,
    execution: ToolSelectionEvalExecution,
    case: ToolSelectionEvalCase,
    failures: list[str],
) -> None:
    expected = case.expected
    if execution.outcome is not expected.outcome:
        failures.append(
            f"outcome expected {expected.outcome.value}, got {execution.outcome.value}"
        )
    if execution.tools != expected.tools:
        failures.append(f"tools expected {expected.tools!r}, got {execution.tools!r}")
    if execution.reason is not expected.reason:
        failures.append(
            "no-tool reason expected "
            f"{expected.reason.value if expected.reason else None}, "
            f"got {execution.reason.value if execution.reason else None}"
        )
    if expected.outcome in _TERMINAL_WITHOUT_TOOLS and execution.tools:
        failures.append(
            f"{expected.outcome.value} must not select any tool, got {execution.tools!r}"
        )
    if expected.outcome is ToolSelectionEvalOutcome.SELECTED and not execution.tools:
        failures.append("selected outcome must carry at least one tool")


def _assert_governance_envelope(
    *,
    execution: ToolSelectionEvalExecution,
    failures: list[str],
) -> None:
    """Every selectable vNext 1.1 tool must stay inside the read-only envelope."""

    for governance in execution.governance:
        for field_name, expected_value, actual_value in (
            ("access", CareerAgentToolAccess.READ_ONLY.value, governance.access),
            (
                "side_effect_class",
                CareerAgentSideEffectClass.READ_ONLY.value,
                governance.side_effect_class,
            ),
            (
                "provider_cost_class",
                CareerAgentProviderCostClass.NONE.value,
                governance.provider_cost_class,
            ),
            (
                "human_gate_requirement",
                CareerAgentHumanGateRequirement.NONE.value,
                governance.human_gate_requirement,
            ),
            (
                "idempotency_class",
                CareerAgentIdempotencyClass.READ_ONLY.value,
                governance.idempotency_class,
            ),
        ):
            if actual_value != expected_value:
                failures.append(
                    f"tool {governance.tool} {field_name} expected {expected_value}, "
                    f"got {actual_value}"
                )


def _no_tool_reason(intent: object) -> ToolSelectionEvalNoToolReason:
    if getattr(intent, "unsupported_request", None):
        return ToolSelectionEvalNoToolReason.UNSUPPORTED
    if getattr(intent, "needs_clarification", False):
        return ToolSelectionEvalNoToolReason.CLARIFICATION
    return ToolSelectionEvalNoToolReason.SUFFICIENT_FACTS


def _governance(definition: CareerAgentToolDefinition) -> ToolSelectionEvalGovernance:
    return ToolSelectionEvalGovernance(
        tool=definition.name.value,
        access=definition.access.value,
        side_effect_class=definition.side_effect_class.value,
        provider_cost_class=definition.provider_cost_class.value,
        human_gate_requirement=definition.human_gate_requirement.value,
        timeout_class=definition.timeout_class.value,
        idempotency_class=definition.idempotency_class.value,
        requires_current_job=definition.requires_current_job,
        requires_explicit_feedback_selection=definition.requires_explicit_feedback_selection,
    )


def _build_agent_context(context: ToolSelectionEvalContext) -> CareerAgentContext:
    """Build the minimum governed context this Eval turn is allowed to use."""

    current_job = (
        CareerAgentJobContext(
            id=context.current_job_id,
            title="Eval governed current job",
            company="Eval fixture",
            area=None,
        )
        if context.current_job_id is not None
        else None
    )
    return CareerAgentContext(
        usable=True,
        confirmation_boundary="confirmed_profile_v1",
        profile=None,
        search_intent=None,
        current_job=current_job,
        relevant_evidence=(),
        blockers=(),
        blocker_messages=(),
    )


def _parse_case(payload: object, *, line_number: int) -> ToolSelectionEvalCase:
    if not isinstance(payload, dict):
        raise ValueError(f"Tool Selection Eval line {line_number} must be an object")

    case_id = _required_string(payload, "id", line_number=line_number)
    category_raw = _required_string(payload, "category", line_number=line_number)
    try:
        category = ToolSelectionEvalCategory(category_raw)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ToolSelectionEvalCategory)
        raise ValueError(
            f"Tool Selection Eval line {line_number} has invalid category "
            f"{category_raw!r}; expected one of {allowed}"
        ) from exc

    message = _required_string(payload, "message", line_number=line_number)
    context_payload = _object(payload.get("context", {}), field="context", line_number=line_number)
    intent_payload = _object(payload.get("intent"), field="intent", line_number=line_number)
    expected_payload = _object(payload.get("expected"), field="expected", line_number=line_number)

    context = ToolSelectionEvalContext(
        current_job_id=_optional_string(
            context_payload.get("currentJobId"),
            field="context.currentJobId",
            line_number=line_number,
        ),
        run_job_ids=_string_tuple(
            context_payload.get("runJobIds", []),
            field="context.runJobIds",
            line_number=line_number,
        ),
    )

    outcome_raw = _required_string(expected_payload, "outcome", line_number=line_number)
    try:
        outcome = ToolSelectionEvalOutcome(outcome_raw)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ToolSelectionEvalOutcome)
        raise ValueError(
            f"Tool Selection Eval line {line_number} has invalid outcome "
            f"{outcome_raw!r}; expected one of {allowed}"
        ) from exc

    reason_raw = _optional_string(
        expected_payload.get("reason"),
        field="expected.reason",
        line_number=line_number,
    )
    try:
        reason = ToolSelectionEvalNoToolReason(reason_raw) if reason_raw else None
    except ValueError as exc:
        raise ValueError(
            f"Tool Selection Eval line {line_number} has invalid no-tool reason {reason_raw!r}"
        ) from exc

    tools = _string_tuple(
        expected_payload.get("tools", []),
        field="expected.tools",
        line_number=line_number,
    )
    for tool in tools:
        try:
            CareerAgentToolName(tool)
        except ValueError as exc:
            raise ValueError(
                f"Tool Selection Eval line {line_number} references unknown tool {tool!r}"
            ) from exc

    expected = ToolSelectionEvalExpected(outcome=outcome, tools=tools, reason=reason)
    argument_probe = _parse_argument_probe(
        payload.get("argumentProbe"),
        line_number=line_number,
    )
    case = ToolSelectionEvalCase(
        case_id=case_id,
        category=category,
        message=message,
        context=context,
        intent_payload=intent_payload,
        expected=expected,
        argument_probe=argument_probe,
    )
    _validate_case_semantics(case)
    return case


def _parse_argument_probe(
    payload: object,
    *,
    line_number: int,
) -> ToolSelectionEvalArgumentProbe | None:
    if payload is None:
        return None
    probe_payload = _object(payload, field="argumentProbe", line_number=line_number)
    tool_raw = _required_string(probe_payload, "tool", line_number=line_number)
    try:
        tool = CareerAgentToolName(tool_raw)
    except ValueError as exc:
        raise ValueError(
            f"Tool Selection Eval line {line_number} argumentProbe has unknown tool {tool_raw!r}"
        ) from exc
    request_payload = _object(
        probe_payload.get("request"),
        field="argumentProbe.request",
        line_number=line_number,
    )
    return ToolSelectionEvalArgumentProbe(
        tool=tool,
        request=_build_request(request_payload, line_number=line_number),
    )


def _build_request(
    payload: Mapping[str, object],
    *,
    line_number: int,
) -> CareerAgentToolRequest:
    kind = payload.get("kind")
    if kind == "rank_match_reports":
        return RankMatchReportsRequest(
            job_ids=_string_tuple(
                payload.get("jobIds", []),
                field="argumentProbe.request.jobIds",
                line_number=line_number,
            ),
            include_blocked=_optional_bool(payload.get("includeBlocked", False), line_number=line_number),
            top_n=_optional_int(payload.get("topN"), line_number=line_number),
        )
    if kind == "target_cohort_gaps":
        return TargetCohortGapsRequest(
            cohort_id=_required_string(payload, "cohortId", line_number=line_number),
            name=_required_string(payload, "name", line_number=line_number),
            selected_feedback_ids=_string_tuple(
                payload.get("selectedFeedbackIds", []),
                field="argumentProbe.request.selectedFeedbackIds",
                line_number=line_number,
            ),
            selected_job_ids=_string_tuple(
                payload.get("selectedJobIds", []),
                field="argumentProbe.request.selectedJobIds",
                line_number=line_number,
            ),
        )
    if kind == "job_preparation":
        return JobPreparationRequest(
            job_id=_optional_string(
                payload.get("jobId"),
                field="argumentProbe.request.jobId",
                line_number=line_number,
            )
        )
    raise ValueError(
        f"Tool Selection Eval line {line_number} argumentProbe.request has invalid kind {kind!r}"
    )


def _validate_case_semantics(case: ToolSelectionEvalCase) -> None:
    case_id = case.case_id
    expected = case.expected

    if expected.outcome is ToolSelectionEvalOutcome.NO_TOOL and expected.reason is None:
        raise ValueError(f"{case_id}: no_tool outcome requires a no-tool reason")
    if expected.outcome is not ToolSelectionEvalOutcome.NO_TOOL and expected.reason is not None:
        raise ValueError(f"{case_id}: no-tool reason requires the no_tool outcome")
    if expected.outcome in _TERMINAL_WITHOUT_TOOLS and expected.tools:
        raise ValueError(
            f"{case_id}: {expected.outcome.value} must not expect selected tools"
        )
    if expected.outcome is ToolSelectionEvalOutcome.SELECTED and not expected.tools:
        raise ValueError(f"{case_id}: selected outcome requires at least one expected tool")

    if case.category is ToolSelectionEvalCategory.CORRECT_TOOL:
        if expected.outcome is not ToolSelectionEvalOutcome.SELECTED:
            raise ValueError(f"{case_id}: correct_tool case must expect a selection")
    elif case.category is ToolSelectionEvalCategory.FORBIDDEN_TOOL:
        if expected.outcome is not ToolSelectionEvalOutcome.FORBIDDEN_GOAL:
            raise ValueError(f"{case_id}: forbidden_tool case must expect forbidden_goal")
    elif case.category is ToolSelectionEvalCategory.UNNECESSARY_TOOL:
        if expected.reason is not ToolSelectionEvalNoToolReason.SUFFICIENT_FACTS:
            raise ValueError(
                f"{case_id}: unnecessary_tool case must expect sufficient_facts"
            )
    elif case.category is ToolSelectionEvalCategory.WRONG_JOB_SCOPE:
        allowed = (
            ToolSelectionEvalOutcome.REJECTED_BY_CONTRACT,
            ToolSelectionEvalOutcome.NO_TOOL,
        )
        if expected.outcome not in allowed or expected.tools:
            raise ValueError(
                f"{case_id}: wrong_job_scope case must fail closed without selecting a tool"
            )
    elif case.category is ToolSelectionEvalCategory.WRONG_ARGUMENT:
        if expected.outcome is not ToolSelectionEvalOutcome.INVALID_ARGUMENT:
            raise ValueError(
                f"{case_id}: wrong_argument case must expect invalid_argument"
            )
        if case.argument_probe is None:
            raise ValueError(f"{case_id}: wrong_argument case requires an argumentProbe")
    elif case.category is ToolSelectionEvalCategory.NO_TOOL_ANSWER:
        allowed_reasons = (
            ToolSelectionEvalNoToolReason.CLARIFICATION,
            ToolSelectionEvalNoToolReason.UNSUPPORTED,
        )
        if expected.outcome is not ToolSelectionEvalOutcome.NO_TOOL:
            raise ValueError(f"{case_id}: no_tool_answer case must expect no_tool")
        if expected.reason not in allowed_reasons:
            raise ValueError(
                f"{case_id}: no_tool_answer case must expect clarification or unsupported"
            )

    if case.category is not ToolSelectionEvalCategory.WRONG_ARGUMENT and case.argument_probe is not None:
        raise ValueError(f"{case_id}: argumentProbe is only valid for wrong_argument cases")


def _required_string(payload: Mapping[str, object], field: str, *, line_number: int) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Tool Selection Eval line {line_number} requires non-empty {field}"
        )
    return value


def _optional_string(value: object, *, field: str, line_number: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Tool Selection Eval line {line_number} field {field} must be non-empty str | null"
        )
    return value


def _object(value: object, *, field: str, line_number: int) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(
            f"Tool Selection Eval line {line_number} field {field} must be an object"
        )
    return value


def _string_tuple(value: object, *, field: str, line_number: int) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ValueError(
            f"Tool Selection Eval line {line_number} field {field} must be string array"
        )
    return tuple(value)


def _optional_bool(value: object, *, line_number: int) -> bool:
    if not isinstance(value, bool):
        raise ValueError(
            f"Tool Selection Eval line {line_number} field includeBlocked must be bool"
        )
    return value


def _optional_int(value: object, *, line_number: int) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            f"Tool Selection Eval line {line_number} field topN must be int | null"
        )
    return value


__all__ = [
    "ToolSelectionEvalAdapter",
    "ToolSelectionEvalArgumentProbe",
    "ToolSelectionEvalCase",
    "ToolSelectionEvalCaseResult",
    "ToolSelectionEvalCategory",
    "ToolSelectionEvalContext",
    "ToolSelectionEvalExecution",
    "ToolSelectionEvalExpected",
    "ToolSelectionEvalGovernance",
    "ToolSelectionEvalNoToolReason",
    "ToolSelectionEvalOutcome",
    "ToolSelectionEvalReplayModel",
    "ToolSelectionEvalReport",
    "evaluate_career_tool_selections",
    "load_career_tool_selection_eval_dataset",
    "validate_career_tool_selection_release_dataset",
]
