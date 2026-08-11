"""HTTP response contract for the read-only Phase 7 Job Preparation bundle."""
from __future__ import annotations

from app.api.v1.schemas.common import CamelCaseModel
from app.application.job_preparation.bundle import JobPreparationBundle


class ResumeDeltaHighlightResponse(CamelCaseModel):
    requirement_id: str
    capability: str
    profile_skill_ids: list[str]
    evidence_ids: list[str]


class ResumeDeltaGapResponse(CamelCaseModel):
    requirement_id: str
    capability: str
    status: str
    profile_skill_ids: list[str]


class ResumeDeltaResponse(CamelCaseModel):
    highlights: list[ResumeDeltaHighlightResponse]
    evidence_gaps: list[ResumeDeltaGapResponse]


class ExperiencePriorityItemResponse(CamelCaseModel):
    evidence_id: str
    evidence_type: str
    supporting_requirement_ids: list[str]
    matched_capabilities: list[str]
    must_have_count: int
    requirement_count: int


class ExperiencePriorityResponse(CamelCaseModel):
    items: list[ExperiencePriorityItemResponse]


class StoryFactItemResponse(CamelCaseModel):
    evidence_id: str
    evidence_type: str
    evidence_summary: str
    supporting_requirement_ids: list[str]
    supporting_requirement_texts: list[str]
    matched_capabilities: list[str]
    must_have_count: int
    requirement_count: int


class StoryFactsResponse(CamelCaseModel):
    items: list[StoryFactItemResponse]


class InterviewFactItemResponse(CamelCaseModel):
    requirement_id: str
    requirement_type: str
    requirement_text: str
    importance: str
    normalized_capability: str | None
    preparation_priority: str
    evidence_status: str
    profile_skill_ids: list[str]
    evidence_ids: list[str]
    evidence_summaries: list[str]


class InterviewFactsResponse(CamelCaseModel):
    items: list[InterviewFactItemResponse]


class StudyChecklistItemResponse(CamelCaseModel):
    requirement_id: str
    requirement_text: str
    capability: str
    importance: str
    evidence_status: str
    need: str
    profile_skill_ids: list[str]
    completion_criteria: list[str]


class StudyChecklistResponse(CamelCaseModel):
    items: list[StudyChecklistItemResponse]


class JobPreparationResponse(CamelCaseModel):
    job_id: str
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    extraction_id: str | None
    resume_delta: ResumeDeltaResponse | None
    experience_priority: ExperiencePriorityResponse | None
    story_facts: StoryFactsResponse | None
    interview_facts: InterviewFactsResponse | None
    study_checklist: StudyChecklistResponse | None
    blockers: list[str]
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_result(cls, result: JobPreparationBundle) -> "JobPreparationResponse":
        resume_delta = None
        if result.resume_delta is not None:
            resume_delta = ResumeDeltaResponse(
                highlights=[
                    ResumeDeltaHighlightResponse(
                        requirement_id=item.requirement_id,
                        capability=item.capability,
                        profile_skill_ids=list(item.profile_skill_ids),
                        evidence_ids=list(item.evidence_ids),
                    )
                    for item in result.resume_delta.highlights
                ],
                evidence_gaps=[
                    ResumeDeltaGapResponse(
                        requirement_id=item.requirement_id,
                        capability=item.capability,
                        status=item.status.value,
                        profile_skill_ids=list(item.profile_skill_ids),
                    )
                    for item in result.resume_delta.evidence_gaps
                ],
            )

        experience_priority = None
        if result.experience_priority is not None:
            experience_priority = ExperiencePriorityResponse(
                items=[
                    ExperiencePriorityItemResponse(
                        evidence_id=item.evidence_id,
                        evidence_type=item.evidence_type.value,
                        supporting_requirement_ids=list(item.supporting_requirement_ids),
                        matched_capabilities=list(item.matched_capabilities),
                        must_have_count=item.must_have_count,
                        requirement_count=item.requirement_count,
                    )
                    for item in result.experience_priority.items
                ]
            )

        story_facts = None
        if result.story_facts is not None:
            story_facts = StoryFactsResponse(
                items=[
                    StoryFactItemResponse(
                        evidence_id=item.evidence_id,
                        evidence_type=item.evidence_type.value,
                        evidence_summary=item.evidence_summary,
                        supporting_requirement_ids=list(item.supporting_requirement_ids),
                        supporting_requirement_texts=list(item.supporting_requirement_texts),
                        matched_capabilities=list(item.matched_capabilities),
                        must_have_count=item.must_have_count,
                        requirement_count=item.requirement_count,
                    )
                    for item in result.story_facts.items
                ]
            )

        interview_facts = None
        if result.interview_facts is not None:
            interview_facts = InterviewFactsResponse(
                items=[
                    InterviewFactItemResponse(
                        requirement_id=item.requirement_id,
                        requirement_type=item.requirement_type.value,
                        requirement_text=item.requirement_text,
                        importance=item.importance.value,
                        normalized_capability=item.normalized_capability,
                        preparation_priority=item.preparation_priority.value,
                        evidence_status=item.evidence_status.value,
                        profile_skill_ids=list(item.profile_skill_ids),
                        evidence_ids=list(item.evidence_ids),
                        evidence_summaries=list(item.evidence_summaries),
                    )
                    for item in result.interview_facts.items
                ]
            )

        study_checklist = None
        if result.study_checklist is not None:
            study_checklist = StudyChecklistResponse(
                items=[
                    StudyChecklistItemResponse(
                        requirement_id=item.requirement_id,
                        requirement_text=item.requirement_text,
                        capability=item.capability,
                        importance=item.importance.value,
                        evidence_status=item.evidence_status.value,
                        need=item.need.value,
                        profile_skill_ids=list(item.profile_skill_ids),
                        completion_criteria=list(item.completion_criteria),
                    )
                    for item in result.study_checklist.items
                ]
            )

        return cls(
            job_id=result.job_id,
            facts_usable=result.facts_usable,
            profile_id=result.profile_id,
            profile_version=result.profile_version,
            extraction_id=result.extraction_id,
            resume_delta=resume_delta,
            experience_priority=experience_priority,
            story_facts=story_facts,
            interview_facts=interview_facts,
            study_checklist=study_checklist,
            blockers=list(result.blockers),
            db_writes=result.db_writes,
            provider_calls=result.provider_calls,
            trace_runs_created=result.trace_runs_created,
        )
