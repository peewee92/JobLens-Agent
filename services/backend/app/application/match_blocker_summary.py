"""Read-only summary of why current persisted MatchReports are blocked."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.match_ranking import BatchRankMatchReportsUseCase
from app.application.match_report import MatchRecommendation
from app.application.ports.job_requirement_repository import AbstractJobRequirementQueryRepository
from app.domain.job_requirements import RequirementType


@dataclass(frozen=True, slots=True)
class MatchBlockerCategorySummary:
    requirement_type: RequirementType
    missing_requirement_count: int
    affected_job_count: int
    affected_job_ids: tuple[str, ...]
    examples: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchBlockerSummary:
    analyzed_report_count: int
    blocked_report_count: int
    missing_requirement_count: int
    resolved_missing_requirement_count: int
    unresolved_missing_requirement_ids: tuple[str, ...]
    categories: tuple[MatchBlockerCategorySummary, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class BuildMatchBlockerSummaryUseCase:
    """Aggregate only current blocked MatchReports without inventing missing facts."""

    def __init__(
        self,
        *,
        ranking: BatchRankMatchReportsUseCase,
        requirements: AbstractJobRequirementQueryRepository,
    ) -> None:
        self._ranking = ranking
        self._requirements = requirements

    def execute(self, job_ids: tuple[str, ...]) -> MatchBlockerSummary:
        reports = self._ranking.execute(job_ids, include_blocked=True)
        blocked = tuple(
            item
            for item in reports
            if item.report.recommendation is MatchRecommendation.BLOCKED
        )

        category_jobs: dict[RequirementType, list[str]] = {}
        category_examples: dict[RequirementType, list[str]] = {}
        category_requirement_counts: dict[RequirementType, int] = {}
        unresolved: list[str] = []
        resolved_count = 0
        missing_count = 0

        for stored in blocked:
            report = stored.report
            missing_count += len(report.missing_requirement_ids)
            extraction = self._requirements.get_latest(report.job_id)
            if extraction is None:
                unresolved.extend(report.missing_requirement_ids)
                continue
            by_id = {item.id: item for item in extraction.requirements}
            for requirement_id in report.missing_requirement_ids:
                requirement = by_id.get(requirement_id)
                if requirement is None:
                    unresolved.append(requirement_id)
                    continue
                resolved_count += 1
                requirement_type = requirement.type
                category_requirement_counts[requirement_type] = (
                    category_requirement_counts.get(requirement_type, 0) + 1
                )
                jobs = category_jobs.setdefault(requirement_type, [])
                if report.job_id not in jobs:
                    jobs.append(report.job_id)
                examples = category_examples.setdefault(requirement_type, [])
                if requirement.original_text not in examples and len(examples) < 3:
                    examples.append(requirement.original_text)

        categories = tuple(
            MatchBlockerCategorySummary(
                requirement_type=requirement_type,
                missing_requirement_count=category_requirement_counts[requirement_type],
                affected_job_count=len(category_jobs[requirement_type]),
                affected_job_ids=tuple(category_jobs[requirement_type]),
                examples=tuple(category_examples[requirement_type]),
            )
            for requirement_type in sorted(
                category_requirement_counts,
                key=lambda item: (
                    -len(category_jobs[item]),
                    -category_requirement_counts[item],
                    item.value,
                ),
            )
        )

        return MatchBlockerSummary(
            analyzed_report_count=len(reports),
            blocked_report_count=len(blocked),
            missing_requirement_count=missing_count,
            resolved_missing_requirement_count=resolved_count,
            unresolved_missing_requirement_ids=tuple(unresolved),
            categories=categories,
        )
