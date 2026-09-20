from __future__ import annotations

import json
from dataclasses import replace

import pytest

# This regression was written before the runner existed so the missing Trajectory
# gate was observable first; the runner now satisfies it.
from app.evals.career_trajectory import (
    CareerTrajectoryEvalCase,
    CareerTrajectoryEvalDriver,
    CareerTrajectoryShape,
    CareerTrajectoryShapeStatus,
    career_trajectory_shape_coverage,
    evaluate_career_trajectories,
    load_career_trajectory_eval_dataset,
    validate_career_trajectory_release_dataset,
)

_NON_EXECUTING_FAMILIES = (
    "clarification",
    "unsupported",
    "blocked",
    "invalid_intent_output",
)


def test_release_dataset_meets_trajectory_family_minimums() -> None:
    cases = load_career_trajectory_eval_dataset()
    counts: dict[str, int] = {}
    for case in cases:
        counts[case.family] = counts.get(case.family, 0) + 1

    assert len(cases) == 24
    assert counts == {
        "completed_single": 3,
        "completed_multi": 3,
        "completed_triple": 2,
        "clarification": 2,
        "unsupported": 2,
        "blocked": 2,
        "invalid_intent_output": 2,
        "invalid_tool_params": 4,
        "loop_detected": 2,
        "budget_exhausted": 2,
    }


def test_release_dataset_validation_rejects_missing_family_minimums() -> None:
    cases = load_career_trajectory_eval_dataset()

    with pytest.raises(ValueError, match="at least 24"):
        validate_career_trajectory_release_dataset(cases=(cases[0],))


def test_trajectory_gate_passes_for_frozen_cohort_against_real_core() -> None:
    cases = load_career_trajectory_eval_dataset()

    report = evaluate_career_trajectories(driver=CareerTrajectoryEvalDriver(), cases=cases)

    failures = {
        result.case_id: result.failure_reasons
        for result in report.case_results
        if not result.passed
    }
    assert failures == {}
    assert report.gate_passed is True
    assert report.total_cases == 24
    assert report.unclassified_errors == 0
    assert report.trace_leaks == 0
    assert report.unstable_traces == 0
    assert report.provider_attempts == 0
    assert report.provider_completed == 0
    assert report.business_writes == 0


def test_trajectory_gate_reports_incomplete_prd_153_coverage() -> None:
    cases = load_career_trajectory_eval_dataset()

    report = evaluate_career_trajectories(driver=CareerTrajectoryEvalDriver(), cases=cases)

    assert report.covered_shapes == 3
    assert report.partial_shapes == 2
    assert report.blocked_shapes == 5
    assert report.covered_shapes + report.partial_shapes + report.blocked_shapes == 10
    assert report.prd_153_shape_coverage_complete is False
    assert report.prd_153_case_minimum_met is False


def test_every_covered_and_partial_shape_is_evidenced_by_a_case() -> None:
    cases = load_career_trajectory_eval_dataset()
    referenced = {shape for case in cases for shape in case.shapes}

    for item in career_trajectory_shape_coverage():
        if item.status is not CareerTrajectoryShapeStatus.BLOCKED:
            assert item.shape in referenced, f"{item.shape.value} has no evidencing case"


def test_every_uncovered_shape_carries_a_reason_and_gap_id() -> None:
    for item in career_trajectory_shape_coverage():
        assert item.evidence
        if item.status is CareerTrajectoryShapeStatus.COVERED:
            assert item.reason is None
            assert item.gap_id is None
        else:
            assert item.reason, f"{item.shape.value} needs a reason"
            assert item.gap_id, f"{item.shape.value} needs a gap id"


def test_coverage_ledger_covers_all_ten_prd_shapes() -> None:
    shapes = [item.shape for item in career_trajectory_shape_coverage()]

    assert len(shapes) == 10
    assert set(shapes) == set(CareerTrajectoryShape)


def test_trace_replay_is_deterministic_for_every_case() -> None:
    cases = load_career_trajectory_eval_dataset()
    driver = CareerTrajectoryEvalDriver()

    for case in cases:
        execution = driver.run(case=case)
        assert execution.replay_stable is True, case.case_id
        assert execution.trace_fingerprints


def test_trace_fingerprints_are_digests_and_vocabulary_is_closed() -> None:
    cases = load_career_trajectory_eval_dataset()

    report = evaluate_career_trajectories(driver=CareerTrajectoryEvalDriver(), cases=cases)

    assert report.trace_leaks == 0
    for result in report.case_results:
        assert result.execution.trace_leak is None
        for event in result.execution.trace:
            assert event.split(":", 1)[0] in {
                "intent_routed", "clarification", "unsupported", "blocked",
                "tool_selected", "tool_called", "pending_action", "tool_result",
                "failed", "finished",
            }


def test_business_code_is_reached_exactly_when_the_trajectory_says_so() -> None:
    cases = load_career_trajectory_eval_dataset()
    driver = CareerTrajectoryEvalDriver()

    for case in cases:
        execution = driver.run(case=case)
        assert execution.workflow_invocations == case.expected.workflow_invocations, case.case_id


def test_non_executing_trajectories_never_reach_business_code() -> None:
    cases = load_career_trajectory_eval_dataset()
    non_executing = tuple(case for case in cases if case.family in _NON_EXECUTING_FAMILIES)
    assert len(non_executing) == 8

    report = evaluate_career_trajectories(
        driver=CareerTrajectoryEvalDriver(),
        cases=non_executing,
        require_release_dataset=False,
    )

    assert all(result.passed for result in report.case_results)
    assert all(
        result.execution.workflow_invocations == 0 for result in report.case_results
    )


def test_failed_trajectories_after_a_successful_tool_still_report_their_results() -> None:
    cases = load_career_trajectory_eval_dataset()
    partial = tuple(
        case
        for case in cases
        if case.expected.status == "failed" and case.expected.tool_results > 0
    )
    assert len(partial) == 4

    report = evaluate_career_trajectories(
        driver=CareerTrajectoryEvalDriver(),
        cases=partial,
        require_release_dataset=False,
    )

    assert all(result.passed for result in report.case_results)


def test_gate_reports_mislabelled_trace_for_exactly_one_case() -> None:
    cases = load_career_trajectory_eval_dataset()
    first = cases[0]
    tampered = (
        replace(first, expected=replace(first.expected, trace=("intent_routed", "finished"))),
    ) + cases[1:]

    report = evaluate_career_trajectories(driver=CareerTrajectoryEvalDriver(), cases=tampered)

    failed = [result for result in report.case_results if not result.passed]
    assert report.gate_passed is False
    assert len(failed) == 1
    assert failed[0].case_id == first.case_id
    assert any("trace expected" in reason for reason in failed[0].failure_reasons)


def test_unstable_trace_replay_is_reported_as_a_violation() -> None:
    cases = load_career_trajectory_eval_dataset()

    class _FlakyDriver(CareerTrajectoryEvalDriver):
        def run(self, *, case: CareerTrajectoryEvalCase):  # type: ignore[override]
            return replace(super().run(case=case), replay_stable=False)

    report = evaluate_career_trajectories(
        driver=_FlakyDriver(),
        cases=(cases[0],),
        require_release_dataset=False,
    )

    assert report.gate_passed is False
    assert report.unstable_traces == 1
    assert any("replay" in reason for reason in report.case_results[0].failure_reasons)


def test_trace_leak_is_reported_as_a_violation() -> None:
    cases = load_career_trajectory_eval_dataset()

    class _LeakyDriver(CareerTrajectoryEvalDriver):
        def run(self, *, case: CareerTrajectoryEvalCase):  # type: ignore[override]
            return replace(super().run(case=case), trace_leak="raw JD text in trace")

    report = evaluate_career_trajectories(
        driver=_LeakyDriver(),
        cases=(cases[0],),
        require_release_dataset=False,
    )

    assert report.gate_passed is False
    assert report.trace_leaks == 1
    assert any("trace leak" in reason for reason in report.case_results[0].failure_reasons)


def test_trajectory_eval_requires_at_least_one_case() -> None:
    with pytest.raises(ValueError, match="at least one case"):
        evaluate_career_trajectories(
            driver=CareerTrajectoryEvalDriver(),
            cases=(),
            require_release_dataset=False,
        )


def test_loader_rejects_unknown_shape(tmp_path) -> None:
    path = tmp_path / "cohort.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "bad-1",
                "family": "completed_single",
                "message": "Rank these.",
                "shapes": ["teleport_then_finish"],
                "intent": {"goals": ["rank_jobs"], "referenced_job_ids": [],
                           "current_job_required": False, "needs_clarification": False,
                           "clarification_question": None, "unsupported_request": None},
                "plannedRequests": [],
                "expected": {"status": "completed", "errorCode": None,
                             "trace": ["intent_routed", "finished"],
                             "toolResults": 0, "workflowInvocations": 0},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown PRD shape"):
        load_career_trajectory_eval_dataset(str(path))


def test_loader_rejects_trace_event_outside_the_vocabulary(tmp_path) -> None:
    path = tmp_path / "cohort.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "bad-2",
                "family": "completed_single",
                "message": "Rank these.",
                "shapes": [],
                "intent": {"goals": ["rank_jobs"], "referenced_job_ids": [],
                           "current_job_required": False, "needs_clarification": False,
                           "clarification_question": None, "unsupported_request": None},
                "plannedRequests": [],
                "expected": {"status": "completed", "errorCode": None,
                             "trace": ["thought", "finished"],
                             "toolResults": 0, "workflowInvocations": 0},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not in the trace vocabulary"):
        load_career_trajectory_eval_dataset(str(path))


def test_loader_rejects_budget_field_that_is_not_a_core_budget_field(tmp_path) -> None:
    path = tmp_path / "cohort.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "bad-3",
                "family": "completed_single",
                "message": "Rank these.",
                "shapes": [],
                "budget": {"maxTurns": 2},
                "intent": {"goals": ["rank_jobs"], "referenced_job_ids": [],
                           "current_job_required": False, "needs_clarification": False,
                           "clarification_question": None, "unsupported_request": None},
                "plannedRequests": [],
                "expected": {"status": "completed", "errorCode": None,
                             "trace": ["intent_routed", "finished"],
                             "toolResults": 0, "workflowInvocations": 0},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown field"):
        load_career_trajectory_eval_dataset(str(path))
