"""Read-only aggregate query for the Phase 7 Job Preparation fact layers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.job_preparation.experience_priority import (
    BuildExperiencePriorityUseCase,
    ExperiencePriorityFacts,
)
from app.application.job_preparation.interview_question_facts import (
    BuildInterviewQuestionFactsUseCase,
    InterviewQuestionFacts,
)
from app.application.job_preparation.readiness import JobPreparationReadiness
from app.application.job_preparation.resume_delta import (
    BuildResumeDeltaFactsUseCase,
    ResumeDeltaFacts,
)
from app.application.job_preparation.story_facts import (
    BuildStoryFactSelectionUseCase,
    StoryFactSelection,
)
from app.application.job_preparation.study_checklist import (
    BuildStudyChecklistUseCase,
    StudyChecklistFacts,
)
from app.application.ports.career_context_repository import (
    AbstractCareerContextQueryRepository,
)
from app.application.ports.job_requirement_repository import (
    AbstractJobRequirementQueryRepository,
)


class JobPreparationReadinessGate(Protocol):
    def execute(self, job_id: str) -> JobPreparationReadiness: ...


@dataclass(frozen=True, slots=True)
class JobPreparationBundle:
    job_id: str
    facts_usable: bool
    profile_id: str | None
    profile_version: int | None
    extraction_id: str | None
    resume_delta: ResumeDeltaFacts | None
    experience_priority: ExperiencePriorityFacts | None
    story_facts: StoryFactSelection | None
    interview_facts: InterviewQuestionFacts | None
    study_checklist: StudyChecklistFacts | None
    blockers: tuple[str, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class BuildJobPreparationBundleUseCase:
    """Compose existing grounded preparation facts behind one read-only query.

    Readiness is evaluated first. When it is blocked, no Profile or Requirement facts
    are read. When ready, the exact frozen Requirement Extraction is loaded and all
    five deterministic Phase 7 fact layers run in dependency order. This use case
    does not generate resume prose, interview answers, learning content, Provider
    calls, Trace runs, or database writes.
    """

    def __init__(
        self,
        *,
        readiness: JobPreparationReadinessGate,
        profiles: AbstractCareerContextQueryRepository,
        requirements: AbstractJobRequirementQueryRepository,
    ) -> None:
        self._readiness = readiness
        self._profiles = profiles
        self._requirements = requirements
        self._resume_delta = BuildResumeDeltaFactsUseCase()
        self._experience_priority = BuildExperiencePriorityUseCase()
        self._story_facts = BuildStoryFactSelectionUseCase()
        self._interview_facts = BuildInterviewQuestionFactsUseCase()
        self._study_checklist = BuildStudyChecklistUseCase()

    def execute(self, job_id: str) -> JobPreparationBundle:
        readiness = self._readiness.execute(job_id)
        if not readiness.preparation_inputs_ready:
            return self._blocked(job_id, ("preparation_inputs_not_ready",))
        if readiness.extraction_id is None:
            return self._blocked(job_id, ("requirement_identity_missing",))

        profile = self._profiles.get_current_profile()
        if profile is None:
            return self._blocked(job_id, ("profile_not_found",))

        extraction = self._requirements.get_extraction(
            job_id=job_id,
            extraction_id=readiness.extraction_id,
        )
        if extraction is None:
            return self._blocked(job_id, ("requirement_extraction_not_found",))

        resume_delta = self._resume_delta.execute(
            readiness=readiness,
            profile=profile,
            extraction=extraction,
        )
        experience_priority = self._experience_priority.execute(
            readiness=readiness,
            profile=profile,
            extraction=extraction,
        )
        story_facts = self._story_facts.execute(
            readiness=readiness,
            profile=profile,
            extraction=extraction,
            priority=experience_priority,
        )
        interview_facts = self._interview_facts.execute(
            readiness=readiness,
            profile=profile,
            extraction=extraction,
            resume_delta=resume_delta,
        )
        study_checklist = self._study_checklist.execute(
            interview_facts=interview_facts,
        )

        layers = (
            resume_delta,
            experience_priority,
            story_facts,
            interview_facts,
            study_checklist,
        )
        blockers = tuple(
            dict.fromkeys(
                blocker
                for layer in layers
                for blocker in layer.blockers
            )
        )
        facts_usable = all(layer.facts_usable for layer in layers)
        return JobPreparationBundle(
            job_id=job_id,
            facts_usable=facts_usable,
            profile_id=profile.id if facts_usable else None,
            profile_version=profile.version if facts_usable else None,
            extraction_id=extraction.extraction_id if facts_usable else None,
            resume_delta=resume_delta,
            experience_priority=experience_priority,
            story_facts=story_facts,
            interview_facts=interview_facts,
            study_checklist=study_checklist,
            blockers=blockers,
        )

    @staticmethod
    def _blocked(job_id: str, blockers: tuple[str, ...]) -> JobPreparationBundle:
        return JobPreparationBundle(
            job_id=job_id,
            facts_usable=False,
            profile_id=None,
            profile_version=None,
            extraction_id=None,
            resume_delta=None,
            experience_priority=None,
            story_facts=None,
            interview_facts=None,
            study_checklist=None,
            blockers=blockers,
        )


__all__ = ["BuildJobPreparationBundleUseCase", "JobPreparationBundle"]
