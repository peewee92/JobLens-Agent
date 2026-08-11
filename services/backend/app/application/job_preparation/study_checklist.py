"""Deterministic pre-interview study checklist facts."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.job_preparation.interview_question_facts import (
    InterviewEvidenceStatus,
    InterviewQuestionFacts,
)
from app.domain.job_requirements import RequirementImportance, RequirementType


class StudyChecklistNeed(StrEnum):
    ADD_EVIDENCE = "add_evidence"
    BUILD_CAPABILITY_AND_EVIDENCE = "build_capability_and_evidence"


@dataclass(frozen=True, slots=True)
class StudyChecklistItem:
    requirement_id: str
    requirement_text: str
    capability: str
    importance: RequirementImportance
    evidence_status: InterviewEvidenceStatus
    need: StudyChecklistNeed
    profile_skill_ids: tuple[str, ...]
    completion_criteria: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StudyChecklistFacts:
    job_id: str
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    extraction_id: str | None
    items: tuple[StudyChecklistItem, ...]
    blockers: tuple[str, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class BuildStudyChecklistUseCase:
    """Select explicit high-value evidence gaps without generating learning content."""

    _included_importance = {
        RequirementImportance.MUST_HAVE,
        RequirementImportance.PREFERRED,
    }

    def execute(self, *, interview_facts: InterviewQuestionFacts) -> StudyChecklistFacts:
        if not interview_facts.facts_usable:
            return self._blocked(interview_facts.job_id, "interview_question_facts_not_ready")

        items: list[StudyChecklistItem] = []
        for fact in interview_facts.items:
            if fact.requirement_type is not RequirementType.SKILL:
                continue
            if fact.importance not in self._included_importance:
                continue
            if fact.evidence_status not in {
                InterviewEvidenceStatus.UNEVIDENCED,
                InterviewEvidenceStatus.MISSING,
            }:
                continue
            if not fact.normalized_capability:
                return self._blocked(interview_facts.job_id, "interview_fact_provenance_invalid")

            if fact.evidence_status is InterviewEvidenceStatus.UNEVIDENCED:
                need = StudyChecklistNeed.ADD_EVIDENCE
                completion_criteria = ("confirmed_evidence_linked_to_skill_exists",)
            else:
                need = StudyChecklistNeed.BUILD_CAPABILITY_AND_EVIDENCE
                completion_criteria = (
                    "confirmed_profile_skill_exists",
                    "confirmed_evidence_linked_to_skill_exists",
                )

            items.append(
                StudyChecklistItem(
                    requirement_id=fact.requirement_id,
                    requirement_text=fact.requirement_text,
                    capability=fact.normalized_capability,
                    importance=fact.importance,
                    evidence_status=fact.evidence_status,
                    need=need,
                    profile_skill_ids=fact.profile_skill_ids,
                    completion_criteria=completion_criteria,
                )
            )

        return StudyChecklistFacts(
            job_id=interview_facts.job_id,
            facts_usable=True,
            profile_id=interview_facts.profile_id,
            profile_version=interview_facts.profile_version,
            extraction_id=interview_facts.extraction_id,
            items=tuple(items),
            blockers=(),
        )

    @staticmethod
    def _blocked(job_id: str, blocker: str) -> StudyChecklistFacts:
        return StudyChecklistFacts(
            job_id=job_id,
            facts_usable=False,
            profile_id=None,
            profile_version=None,
            extraction_id=None,
            items=(),
            blockers=(blocker,),
        )


__all__ = [
    "BuildStudyChecklistUseCase",
    "StudyChecklistFacts",
    "StudyChecklistItem",
    "StudyChecklistNeed",
]
