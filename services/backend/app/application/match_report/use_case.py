"""Application orchestration for one persisted MatchReport snapshot."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

from app.application.eligibility import (
    EligibilityDecision,
    JobEligibilityResult,
    RequirementFitStatus,
)
from app.application.match_report.builder import build_match_report
from app.application.match_report.models import MatchReport
from app.application.ports.match_report_unit_of_work import AbstractMatchReportUnitOfWork
from app.application.semantic_match import (
    JobSemanticMatchResult,
    SemanticAssessmentSource,
    SemanticMatchVerdict,
    SemanticRequirementAssessment,
)


class SemanticMatchRunner(Protocol):
    def execute(self, job_id: str) -> JobSemanticMatchResult: ...


class EligibilityRunner(Protocol):
    def execute(self, job_id: str) -> JobEligibilityResult: ...


class MatchReportPersistenceNotReadyError(RuntimeError):
    """Raised before Provider work when the immutable report schema is unavailable."""


MatchReportUnitOfWorkFactory = Callable[[], AbstractMatchReportUnitOfWork]
PersistenceReadyCheck = Callable[[], bool]


class BuildJobMatchReportUseCase:
    """Run guarded Semantic Match once, then persist one immutable report snapshot."""

    def __init__(
        self,
        semantic_match: SemanticMatchRunner,
        *,
        eligibility: EligibilityRunner | None = None,
        persistence_ready: PersistenceReadyCheck | None = None,
        uow_factory: MatchReportUnitOfWorkFactory | None = None,
    ) -> None:
        self._semantic_match = semantic_match
        self._eligibility = eligibility
        self._persistence_ready = persistence_ready
        self._uow_factory = uow_factory

    def execute(self, job_id: str) -> MatchReport:
        if self._persistence_ready is not None and not self._persistence_ready():
            raise MatchReportPersistenceNotReadyError(
                "MatchReport persistence schema is not ready; apply the approved database migration before generating reports."
            )

        eligibility = self._eligibility.execute(job_id) if self._eligibility is not None else None
        if eligibility is not None and eligibility.eligibility is EligibilityDecision.BLOCKED:
            report = build_match_report(_blocked_semantic_result(eligibility))
        else:
            report = build_match_report(self._semantic_match.execute(job_id))
        if self._uow_factory is None:
            return report

        persisted_report = replace(report, db_writes=1)
        with self._uow_factory() as uow:
            uow.reports.add(persisted_report)
            uow.commit()
        return persisted_report


def _blocked_semantic_result(eligibility: JobEligibilityResult) -> JobSemanticMatchResult:
    assessments = tuple(
        SemanticRequirementAssessment(
            requirement_id=item.requirement_id,
            requirement_index=item.requirement_index,
            type=item.type,
            importance=item.importance,
            original_text=item.original_text,
            normalized_capability=item.normalized_capability,
            eligibility_status=item.status,
            verdict=(
                SemanticMatchVerdict.MATCHED
                if item.status is RequirementFitStatus.MATCHED
                else SemanticMatchVerdict.NOT_MATCHED
            ),
            evidence_ids=item.evidence_ids if item.status is RequirementFitStatus.MATCHED else (),
            profile_fact_refs=item.profile_fact_refs,
            reason=(
                item.reason
                if item.status is not RequirementFitStatus.CONDITIONAL
                else (
                    "整体 Eligibility 已因明确 must-have 缺口 blocked；"
                    "本次 MatchReport 不再执行语义匹配，这条要求仅保留为未确认。"
                )
            ),
            source=SemanticAssessmentSource.DETERMINISTIC,
        )
        for item in eligibility.requirements
    )
    return JobSemanticMatchResult(
        job_id=eligibility.job_id,
        profile_id=eligibility.profile_id,
        profile_version=eligibility.profile_version,
        extraction_id=eligibility.extraction_id,
        eligibility=eligibility.eligibility,
        assessments=assessments,
        matched_count=sum(item.verdict is SemanticMatchVerdict.MATCHED for item in assessments),
        partial_count=0,
        not_matched_count=sum(
            item.verdict is SemanticMatchVerdict.NOT_MATCHED for item in assessments
        ),
        matcher_version="eligibility-only-v1",
        prompt_version="not-applicable",
        model=None,
        trace_run_id=None,
        provider_calls=0,
        trace_runs_created=0,
    )
