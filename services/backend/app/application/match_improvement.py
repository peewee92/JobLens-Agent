"""Read-only comparison between the current MatchReport and its prior comparable snapshot."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.ports.match_report_repository import AbstractMatchReportQueryRepository
from app.application.match_report import MatchRecommendation


@dataclass(frozen=True, slots=True)
class MatchImprovement:
    job_id: str
    current_report_id: str
    previous_report_id: str | None
    previous_recommendation: MatchRecommendation | None
    current_recommendation: MatchRecommendation
    previous_missing_requirement_count: int | None
    current_missing_requirement_count: int
    resolved_requirement_ids: tuple[str, ...]
    newly_missing_requirement_ids: tuple[str, ...]
    comparable: bool
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class GetMatchImprovementUseCase:
    """Compare one immutable current report with the newest comparable predecessor.

    Comparable means same Job, Profile identity, and Requirement Extraction. Profile version may
    differ, which is exactly the Evidence -> Re-match loop this read model explains.
    """

    def __init__(self, reports: AbstractMatchReportQueryRepository) -> None:
        self._reports = reports

    def execute(self, *, job_id: str, current_report_id: str) -> MatchImprovement:
        current = self._reports.get(current_report_id)
        if current is None or current.report.job_id != job_id:
            raise ValueError("current_match_report_not_found")

        current_report = current.report
        previous = next(
            (
                candidate
                for candidate in self._reports.list_for_job(job_id)
                if candidate.id != current.id
                and candidate.report.profile_id == current_report.profile_id
                and candidate.report.extraction_id == current_report.extraction_id
            ),
            None,
        )
        current_missing = tuple(current_report.missing_requirement_ids)
        if previous is None:
            return MatchImprovement(
                job_id=job_id,
                current_report_id=current.id,
                previous_report_id=None,
                previous_recommendation=None,
                current_recommendation=current_report.recommendation,
                previous_missing_requirement_count=None,
                current_missing_requirement_count=len(current_missing),
                resolved_requirement_ids=(),
                newly_missing_requirement_ids=(),
                comparable=False,
            )

        previous_missing = tuple(previous.report.missing_requirement_ids)
        current_missing_set = set(current_missing)
        previous_missing_set = set(previous_missing)
        return MatchImprovement(
            job_id=job_id,
            current_report_id=current.id,
            previous_report_id=previous.id,
            previous_recommendation=previous.report.recommendation,
            current_recommendation=current_report.recommendation,
            previous_missing_requirement_count=len(previous_missing),
            current_missing_requirement_count=len(current_missing),
            resolved_requirement_ids=tuple(
                requirement_id
                for requirement_id in previous_missing
                if requirement_id not in current_missing_set
            ),
            newly_missing_requirement_ids=tuple(
                requirement_id
                for requirement_id in current_missing
                if requirement_id not in previous_missing_set
            ),
            comparable=True,
        )
