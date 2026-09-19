import pytest

from app.agent.intent import (
    CareerIntent,
    CareerIntentGoal,
    CareerIntentResolutionContext,
    CareerIntentResolver,
    CareerIntentValidationError,
)


def test_intent_preserves_order_and_resolves_explicit_jobs_within_scope() -> None:
    resolver = CareerIntentResolver()

    intent = resolver.resolve(
        intent=CareerIntent(
            goals=(CareerIntentGoal.RANK_JOBS, CareerIntentGoal.REVIEW_GAPS),
            referenced_job_ids=("job-2", "job-1", "job-2"),
            reasoning_summary="先排序，再分析共同差距。",
        ),
        context=CareerIntentResolutionContext(run_job_ids=("job-1", "job-2", "job-3")),
    )

    assert intent.goals == (CareerIntentGoal.RANK_JOBS, CareerIntentGoal.REVIEW_GAPS)
    assert intent.referenced_job_ids == ("job-2", "job-1")
    assert intent.needs_clarification is False
    assert intent.unsupported_request is None


def test_current_job_reference_is_grounded_from_context() -> None:
    resolver = CareerIntentResolver()

    intent = resolver.resolve(
        intent=CareerIntent(
            goals=(CareerIntentGoal.PREPARE_JOB,),
            current_job_required=True,
            reasoning_summary="用户要求准备当前岗位。",
        ),
        context=CareerIntentResolutionContext(
            current_job_id="job-current",
            run_job_ids=("job-current", "job-other"),
        ),
    )

    assert intent.referenced_job_ids == ("job-current",)
    assert intent.needs_clarification is False


def test_missing_current_job_fails_closed_to_clarification() -> None:
    resolver = CareerIntentResolver()

    intent = resolver.resolve(
        intent=CareerIntent(
            goals=(CareerIntentGoal.PREPARE_JOB,),
            current_job_required=True,
            reasoning_summary="用户引用了当前岗位。",
        ),
        context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
    )

    assert intent.referenced_job_ids == ()
    assert intent.needs_clarification is True
    assert intent.clarification_question


def test_job_outside_frozen_run_scope_is_rejected_instead_of_guessed() -> None:
    resolver = CareerIntentResolver()

    with pytest.raises(CareerIntentValidationError, match="outside the governed run scope"):
        resolver.resolve(
            intent=CareerIntent(
                goals=(CareerIntentGoal.PREPARE_JOB,),
                referenced_job_ids=("job-outside",),
                reasoning_summary="用户显式引用岗位。",
            ),
            context=CareerIntentResolutionContext(run_job_ids=("job-1", "job-2")),
        )


def test_unsupported_request_cannot_carry_executable_goals() -> None:
    with pytest.raises(CareerIntentValidationError, match="unsupported request cannot carry executable goals"):
        CareerIntent(
            goals=(CareerIntentGoal.RANK_JOBS,),
            unsupported_request="automated_job_application",
            reasoning_summary="用户要求自动投递。",
        )


def test_reasoning_summary_is_bounded_audit_text() -> None:
    with pytest.raises(CareerIntentValidationError, match="reasoning_summary"):
        CareerIntent(
            goals=(CareerIntentGoal.RANK_JOBS,),
            reasoning_summary="x" * 501,
        )
