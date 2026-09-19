import pytest

from app.agent.intent import (
    CareerIntent,
    CareerIntentGoal,
    CareerIntentModel,
    CareerIntentResolutionContext,
    CareerIntentRouter,
    CareerIntentResolver,
    CareerIntentValidationError,
)


class _StaticIntentModel(CareerIntentModel):
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.messages: list[str] = []

    def route(self, user_message: str) -> dict[str, object]:
        self.messages.append(user_message)
        return self.payload


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


def test_router_preserves_ordered_single_and_multi_goal_model_output() -> None:
    model = _StaticIntentModel(
        {
            "goals": ["rank_jobs", "review_gaps"],
            "referenced_job_ids": [],
            "current_job_required": False,
            "needs_clarification": False,
            "clarification_question": None,
            "unsupported_request": None,
            "confidence": 0.93,
            "reasoning_summary": "先排序，再分析共同差距。",
        }
    )
    router = CareerIntentRouter(model=model)

    intent = router.route(
        user_message="先选出最值得投的岗位，再看看共同缺什么。",
        context=CareerIntentResolutionContext(run_job_ids=("job-1", "job-2")),
    )

    assert model.messages == ["先选出最值得投的岗位，再看看共同缺什么。"]
    assert intent.goals == (CareerIntentGoal.RANK_JOBS, CareerIntentGoal.REVIEW_GAPS)
    assert intent.needs_clarification is False


def test_router_grounds_current_job_and_fails_closed_when_context_is_missing() -> None:
    model = _StaticIntentModel(
        {
            "goals": ["prepare_job"],
            "referenced_job_ids": [],
            "current_job_required": True,
            "needs_clarification": False,
            "clarification_question": None,
            "unsupported_request": None,
            "confidence": 0.9,
            "reasoning_summary": "用户要求准备当前岗位。",
        }
    )
    router = CareerIntentRouter(model=model)

    grounded = router.route(
        user_message="这个岗位面试前怎么准备？",
        context=CareerIntentResolutionContext(
            current_job_id="job-current",
            run_job_ids=("job-current", "job-other"),
        ),
    )
    missing = router.route(
        user_message="这个岗位面试前怎么准备？",
        context=CareerIntentResolutionContext(run_job_ids=("job-other",)),
    )

    assert grounded.referenced_job_ids == ("job-current",)
    assert grounded.needs_clarification is False
    assert missing.goals == ()
    assert missing.referenced_job_ids == ()
    assert missing.needs_clarification is True
    assert missing.clarification_question


def test_router_rejects_clarification_that_still_carries_executable_goal() -> None:
    model = _StaticIntentModel(
        {
            "goals": ["rank_jobs"],
            "needs_clarification": True,
            "clarification_question": "你希望分析哪一批岗位？",
            "reasoning_summary": "缺少岗位范围。",
        }
    )
    router = CareerIntentRouter(model=model)

    with pytest.raises(CareerIntentValidationError, match="clarification cannot carry executable goals"):
        router.route(
            user_message="帮我看看",
            context=CareerIntentResolutionContext(),
        )


def test_router_rejects_unsupported_action_without_executable_goal() -> None:
    model = _StaticIntentModel(
        {
            "goals": [],
            "referenced_job_ids": [],
            "current_job_required": False,
            "needs_clarification": False,
            "clarification_question": None,
            "unsupported_request": "automated_job_application",
            "confidence": 0.99,
            "reasoning_summary": "用户要求自动投递。",
        }
    )
    router = CareerIntentRouter(model=model)

    intent = router.route(
        user_message="直接帮我把这些岗位全部投了。",
        context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
    )

    assert intent.goals == ()
    assert intent.unsupported_request == "automated_job_application"


def test_router_rejects_malformed_or_unknown_model_output() -> None:
    router = CareerIntentRouter(model=_StaticIntentModel({"goals": ["invent_tool"]}))

    with pytest.raises(CareerIntentValidationError, match="invalid intent model output"):
        router.route(
            user_message="做点什么",
            context=CareerIntentResolutionContext(run_job_ids=("job-1",)),
        )
