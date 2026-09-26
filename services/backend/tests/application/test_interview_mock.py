from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.application.application_workspace.interview_mock import (
    BuildInterviewMockQuestionSetUseCase,
    InterviewAnswerGroundingStatus,
    InterviewMockBlockedError,
    ReviewInterviewMockAnswerUseCase,
)
from app.application.application_workspace.models import ApplicationWorkspaceSourceSnapshot
from app.application.job_preparation.interview_question_facts import (
    InterviewEvidenceStatus,
    InterviewPreparationPriority,
    InterviewQuestionFactItem,
    InterviewQuestionFacts,
)
from app.domain.job_requirements import RequirementImportance, RequirementType


class WorkspaceRepo:
    def __init__(self, workspace):
        self.workspace = workspace

    def get(self, workspace_id):
        return self.workspace if workspace_id == self.workspace.workspace_id else None


class Preparation:
    def __init__(self, bundle):
        self.bundle = bundle

    def execute(self, job_id):
        assert job_id == self.bundle.job_id
        return self.bundle


def _workspace():
    return SimpleNamespace(
        workspace_id="ws_1",
        job_id="job_1",
        source_snapshot=ApplicationWorkspaceSourceSnapshot(
            "prof_1", 3, "intent_1", 2, "req_1", "match_1"
        ),
    )


def _bundle(*, profile_version=3):
    facts = InterviewQuestionFacts(
        job_id="job_1",
        facts_usable=True,
        profile_id="prof_1",
        profile_version=profile_version,
        extraction_id="req_1",
        items=(
            InterviewQuestionFactItem(
                requirement_id="r1",
                requirement_type=RequirementType.SKILL,
                requirement_text="具备 Python 工程实践",
                importance=RequirementImportance.MUST_HAVE,
                normalized_capability="Python",
                preparation_priority=InterviewPreparationPriority.HIGH,
                evidence_status=InterviewEvidenceStatus.SUPPORTED,
                profile_skill_ids=("s1",),
                evidence_ids=("ev1",),
                evidence_summaries=("在真实项目中使用 Python",),
            ),
            InterviewQuestionFactItem(
                requirement_id="r2",
                requirement_type=RequirementType.SKILL,
                requirement_text="具备 Ray 实践",
                importance=RequirementImportance.PREFERRED,
                normalized_capability="Ray",
                preparation_priority=InterviewPreparationPriority.MEDIUM,
                evidence_status=InterviewEvidenceStatus.MISSING,
                profile_skill_ids=(),
                evidence_ids=(),
                evidence_summaries=(),
            ),
        ),
        blockers=(),
    )
    return SimpleNamespace(
        job_id="job_1",
        facts_usable=True,
        profile_id="prof_1",
        profile_version=profile_version,
        extraction_id="req_1",
        interview_facts=facts,
    )


def _question_sets(*, profile_version=3):
    return BuildInterviewMockQuestionSetUseCase(
        workspaces=WorkspaceRepo(_workspace()),
        preparation=Preparation(_bundle(profile_version=profile_version)),
    )


def test_question_set_reuses_released_interview_facts_and_exposes_only_confirmed_evidence():
    result = _question_sets().execute("ws_1")

    assert [item.requirement_id for item in result.questions] == ["r1", "r2"]
    assert result.questions[0].allowed_evidence_ids == ("ev1",)
    assert result.questions[1].allowed_evidence_ids == ()
    assert "不要补造经历" in result.questions[1].prompt


def test_question_set_fails_closed_when_workspace_snapshot_is_stale():
    with pytest.raises(InterviewMockBlockedError, match="application_workspace_facts_stale"):
        _question_sets(profile_version=4).execute("ws_1")


def test_answer_review_accepts_only_evidence_grounded_for_that_requirement():
    review = ReviewInterviewMockAnswerUseCase(question_sets=_question_sets()).execute(
        workspace_id="ws_1",
        question_id="iq_r1",
        answer_text="我在项目中使用 Python 完成了后端能力。",
        evidence_ids=("ev1",),
    )

    assert review.grounding_status is InterviewAnswerGroundingStatus.GROUNDED
    assert review.accepted_evidence_ids == ("ev1",)
    assert review.rejected_evidence_ids == ()
    assert review.retry_recommended is False
    assert review.provider_calls == 0
    assert review.db_writes == 0


def test_answer_review_rejects_cross_requirement_or_invented_evidence_and_recommends_retry():
    review = ReviewInterviewMockAnswerUseCase(question_sets=_question_sets()).execute(
        workspace_id="ws_1",
        question_id="iq_r1",
        answer_text="我做过相关工作。",
        evidence_ids=("ev_other",),
    )

    assert review.grounding_status is InterviewAnswerGroundingStatus.UNGROUNDED
    assert review.accepted_evidence_ids == ()
    assert review.rejected_evidence_ids == ("ev_other",)
    assert review.retry_recommended is True
