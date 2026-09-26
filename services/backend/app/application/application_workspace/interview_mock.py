"""Grounded Interview / Mock contracts for vNext 1.2.

This slice deliberately stays provider-free: questions are deterministic prompts over
released JobRequirement facts, and answer review verifies only explicit Evidence IDs.
It never invents STAR details, metrics, or hiring probability.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.application.job_preparation.bundle import BuildJobPreparationBundleUseCase
from app.application.job_preparation.interview_question_facts import InterviewEvidenceStatus


class InterviewMockBlockedError(RuntimeError):
    pass


class InterviewAnswerGroundingStatus(StrEnum):
    GROUNDED = "grounded"
    PARTIALLY_GROUNDED = "partially_grounded"
    UNGROUNDED = "ungrounded"


@dataclass(frozen=True, slots=True)
class InterviewMockQuestion:
    question_id: str
    requirement_id: str
    requirement_text: str
    preparation_priority: str
    evidence_status: str
    allowed_evidence_ids: tuple[str, ...]
    prompt: str


@dataclass(frozen=True, slots=True)
class InterviewMockQuestionSet:
    workspace_id: str
    job_id: str
    source_profile_id: str
    source_profile_version: int
    requirement_extraction_id: str
    questions: tuple[InterviewMockQuestion, ...]


@dataclass(frozen=True, slots=True)
class InterviewAnswerReview:
    workspace_id: str
    question_id: str
    requirement_id: str
    grounding_status: InterviewAnswerGroundingStatus
    accepted_evidence_ids: tuple[str, ...]
    rejected_evidence_ids: tuple[str, ...]
    feedback: tuple[str, ...]
    retry_recommended: bool
    provider_calls: int = 0
    db_writes: int = 0


class WorkspaceQuery(Protocol):
    def get(self, workspace_id: str): ...


class BuildInterviewMockQuestionSetUseCase:
    """Turn existing Interview Facts into executable, deterministic practice prompts."""

    def __init__(self, *, workspaces: WorkspaceQuery, preparation: BuildJobPreparationBundleUseCase) -> None:
        self._workspaces = workspaces
        self._preparation = preparation

    def execute(self, workspace_id: str) -> InterviewMockQuestionSet:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise InterviewMockBlockedError("application_workspace_not_found")
        bundle = self._preparation.execute(workspace.job_id)
        if not bundle.facts_usable or bundle.interview_facts is None:
            raise InterviewMockBlockedError("interview_facts_not_ready")
        snapshot = workspace.source_snapshot
        if (
            bundle.profile_id != snapshot.profile_id
            or bundle.profile_version != snapshot.profile_version
            or bundle.extraction_id != snapshot.requirement_extraction_id
        ):
            raise InterviewMockBlockedError("application_workspace_facts_stale")
        facts = bundle.interview_facts
        if not facts.facts_usable:
            raise InterviewMockBlockedError("interview_facts_not_ready")

        questions = tuple(
            InterviewMockQuestion(
                question_id=f"iq_{item.requirement_id}",
                requirement_id=item.requirement_id,
                requirement_text=item.requirement_text,
                preparation_priority=item.preparation_priority.value,
                evidence_status=item.evidence_status.value,
                allowed_evidence_ids=item.evidence_ids,
                prompt=self._prompt_for(item.requirement_text, item.evidence_status),
            )
            for item in facts.items
        )
        if not questions:
            raise InterviewMockBlockedError("interview_question_set_empty")
        return InterviewMockQuestionSet(
            workspace_id=workspace.workspace_id,
            job_id=workspace.job_id,
            source_profile_id=snapshot.profile_id,
            source_profile_version=snapshot.profile_version,
            requirement_extraction_id=snapshot.requirement_extraction_id,
            questions=questions,
        )

    @staticmethod
    def _prompt_for(requirement_text: str, evidence_status: InterviewEvidenceStatus) -> str:
        if evidence_status is InterviewEvidenceStatus.SUPPORTED:
            return f"请结合你已确认的真实经历，说明你如何满足这项岗位要求：{requirement_text}"
        return f"这项岗位要求目前缺少已确认经历支撑。请只说明你的真实情况，不要补造经历：{requirement_text}"


class ReviewInterviewMockAnswerUseCase:
    """Check answer provenance without pretending to semantically grade free-form prose."""

    def __init__(self, *, question_sets: BuildInterviewMockQuestionSetUseCase) -> None:
        self._question_sets = question_sets

    def execute(
        self,
        *,
        workspace_id: str,
        question_id: str,
        answer_text: str,
        evidence_ids: tuple[str, ...],
    ) -> InterviewAnswerReview:
        if not answer_text.strip():
            raise InterviewMockBlockedError("interview_answer_empty")
        question_set = self._question_sets.execute(workspace_id)
        question = next((item for item in question_set.questions if item.question_id == question_id), None)
        if question is None:
            raise InterviewMockBlockedError("interview_question_not_found")

        allowed = set(question.allowed_evidence_ids)
        accepted = tuple(dict.fromkeys(evidence_id for evidence_id in evidence_ids if evidence_id in allowed))
        rejected = tuple(dict.fromkeys(evidence_id for evidence_id in evidence_ids if evidence_id not in allowed))
        feedback: list[str] = []
        if rejected:
            feedback.append("回答引用了不属于该岗位要求的已确认 Evidence，请删除或改用允许的 Evidence。")
        if not accepted:
            feedback.append("当前回答没有引用该岗位要求下的已确认 Evidence；请补充真实经历，或明确说明暂无相关经历。")
        if accepted and not rejected:
            feedback.append("回答已关联到该岗位要求下的已确认 Evidence；可继续优化表达结构，但不要新增未经确认的事实或指标。")

        if accepted and not rejected:
            grounding_status = InterviewAnswerGroundingStatus.GROUNDED
        elif accepted:
            grounding_status = InterviewAnswerGroundingStatus.PARTIALLY_GROUNDED
        else:
            grounding_status = InterviewAnswerGroundingStatus.UNGROUNDED
        return InterviewAnswerReview(
            workspace_id=workspace_id,
            question_id=question.question_id,
            requirement_id=question.requirement_id,
            grounding_status=grounding_status,
            accepted_evidence_ids=accepted,
            rejected_evidence_ids=rejected,
            feedback=tuple(feedback),
            retry_recommended=grounding_status is not InterviewAnswerGroundingStatus.GROUNDED,
        )
