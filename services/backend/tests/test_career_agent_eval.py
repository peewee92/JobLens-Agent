from dataclasses import dataclass

import pytest

from app.agent.context import CareerAgentContext
from app.agent.entrypoint import CareerAgentEntrypointError, CareerAgentGoal, CareerAgentTurn, CareerAgentTurnResult
from app.agent.tool_registry import CareerAgentToolName
from app.evals.career_agent import CareerAgentEvalCase, evaluate_career_agent


@dataclass
class _Entrypoint:
    results: dict[str, CareerAgentTurnResult | Exception]

    def execute(self, turn: CareerAgentTurn) -> CareerAgentTurnResult:
        result = self.results[turn.goal.value]
        if isinstance(result, Exception):
            raise result
        return result


def _context(*, usable: bool = True) -> CareerAgentContext:
    return CareerAgentContext(
        usable=usable,
        confirmation_boundary="confirmed",
        profile=None,
        search_intent=None,
        current_job=None,
        relevant_evidence=(),
        blockers=(),
        blocker_messages=(),
    )


def test_eval_gates_routing_fail_closed_and_grounding() -> None:
    entrypoint = _Entrypoint(results={
        "rank_jobs": CareerAgentTurnResult(
            context=_context(), goal=CareerAgentGoal.RANK_JOBS,
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            output={"items": [{"jobId": "job-1", "evidenceLinks": [{"requirementId": "req-1", "evidenceId": "ev-1"}]}]},
        ),
        "review_gaps": CareerAgentTurnResult(
            context=_context(usable=False), goal=CareerAgentGoal.REVIEW_GAPS,
            tool=None, output=None,
        ),
        "prepare_job": CareerAgentEntrypointError("prepare_job requires governed current job"),
    })

    report = evaluate_career_agent(entrypoint=entrypoint, cases=(
        CareerAgentEvalCase(
            case_id="rank-grounded",
            turn=CareerAgentTurn(goal=CareerAgentGoal.RANK_JOBS, job_ids=("job-1",)),
            expected_tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            required_grounding_keys=("requirementId", "evidenceId"),
        ),
        CareerAgentEvalCase(
            case_id="gap-context-blocked",
            turn=CareerAgentTurn(
                goal=CareerAgentGoal.REVIEW_GAPS,
                cohort_id="cohort-1", cohort_name="Target",
                selected_feedback_ids=("feedback-1",),
            ),
            expected_tool=None,
        ),
        CareerAgentEvalCase(
            case_id="prepare-needs-current-job",
            turn=CareerAgentTurn(goal=CareerAgentGoal.PREPARE_JOB),
            expected_tool=None,
            expect_error=True,
        ),
    ))

    assert report.gate_passed is True
    assert report.passed_cases == 3


def test_eval_fails_when_grounding_reference_is_missing() -> None:
    entrypoint = _Entrypoint(results={
        "rank_jobs": CareerAgentTurnResult(
            context=_context(), goal=CareerAgentGoal.RANK_JOBS,
            tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            output={"items": [{"jobId": "job-1"}]},
        )
    })

    report = evaluate_career_agent(entrypoint=entrypoint, cases=(
        CareerAgentEvalCase(
            case_id="missing-grounding",
            turn=CareerAgentTurn(goal=CareerAgentGoal.RANK_JOBS, job_ids=("job-1",)),
            expected_tool=CareerAgentToolName.RANK_MATCH_REPORTS,
            required_grounding_keys=("requirementId", "evidenceId"),
        ),
    ))

    assert report.gate_passed is False
    assert "missing grounding references" in report.case_results[0].failure_reasons[0]


def test_eval_requires_cases() -> None:
    with pytest.raises(ValueError, match="at least one case"):
        evaluate_career_agent(entrypoint=_Entrypoint(results={}), cases=())
