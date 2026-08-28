"""Read-only summary of why current persisted MatchReports are blocked."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.match_ranking import BatchRankMatchReportsUseCase
from app.application.match_report import MatchRecommendation
from app.application.ports.job_requirement_repository import AbstractJobRequirementQueryRepository
from app.domain.job_requirements import RequirementType


@dataclass(frozen=True, slots=True)
class MatchBlockerRequirementSummary:
    requirement_id: str
    requirement_type: RequirementType
    original_text: str
    normalized_capability: str | None


@dataclass(frozen=True, slots=True)
class MatchBlockerJobSummary:
    job_id: str
    missing_requirement_count: int
    requirements: tuple[MatchBlockerRequirementSummary, ...]
    unresolved_missing_requirement_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchBlockerCategorySummary:
    requirement_type: RequirementType
    missing_requirement_count: int
    affected_job_count: int
    affected_job_ids: tuple[str, ...]
    examples: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchBlockerActionSummary:
    requirement_type: RequirementType
    normalized_capability: str | None
    missing_requirement_count: int
    affected_job_count: int
    affected_job_ids: tuple[str, ...]
    requirement_ids: tuple[str, ...]
    examples: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MatchBlockerSummary:
    analyzed_report_count: int
    blocked_report_count: int
    missing_requirement_count: int
    resolved_missing_requirement_count: int
    unresolved_missing_requirement_ids: tuple[str, ...]
    categories: tuple[MatchBlockerCategorySummary, ...]
    priority_actions: tuple[MatchBlockerActionSummary, ...]
    job_blockers: tuple[MatchBlockerJobSummary, ...]
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
        action_jobs: dict[tuple[RequirementType, str], list[str]] = {}
        action_examples: dict[tuple[RequirementType, str], list[str]] = {}
        action_requirement_ids: dict[tuple[RequirementType, str], list[str]] = {}
        action_capabilities: dict[tuple[RequirementType, str], str | None] = {}
        action_requirement_counts: dict[tuple[RequirementType, str], int] = {}
        unresolved: list[str] = []
        job_blockers: list[MatchBlockerJobSummary] = []
        resolved_count = 0
        missing_count = 0

        for stored in blocked:
            report = stored.report
            missing_count += len(report.missing_requirement_ids)
            job_requirements: list[MatchBlockerRequirementSummary] = []
            job_unresolved: list[str] = []
            extraction = self._requirements.get_latest(report.job_id)
            if extraction is None:
                job_unresolved.extend(report.missing_requirement_ids)
                unresolved.extend(report.missing_requirement_ids)
                job_blockers.append(
                    MatchBlockerJobSummary(
                        job_id=report.job_id,
                        missing_requirement_count=len(report.missing_requirement_ids),
                        requirements=(),
                        unresolved_missing_requirement_ids=tuple(job_unresolved),
                    )
                )
                continue
            by_id = {item.id: item for item in extraction.requirements}
            for requirement_id in report.missing_requirement_ids:
                requirement = by_id.get(requirement_id)
                if requirement is None:
                    job_unresolved.append(requirement_id)
                    unresolved.append(requirement_id)
                    continue
                resolved_count += 1
                job_requirements.append(
                    MatchBlockerRequirementSummary(
                        requirement_id=requirement.id,
                        requirement_type=requirement.type,
                        original_text=requirement.original_text,
                        normalized_capability=requirement.normalized_capability,
                    )
                )
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

                capability = requirement.normalized_capability.strip() if requirement.normalized_capability else None
                action_identity = capability.casefold() if capability else f"requirement:{requirement.id}"
                action_key = (requirement_type, action_identity)
                action_capabilities.setdefault(action_key, capability)
                action_requirement_counts[action_key] = action_requirement_counts.get(action_key, 0) + 1
                action_job_ids = action_jobs.setdefault(action_key, [])
                if report.job_id not in action_job_ids:
                    action_job_ids.append(report.job_id)
                action_ids = action_requirement_ids.setdefault(action_key, [])
                if requirement.id not in action_ids:
                    action_ids.append(requirement.id)
                action_texts = action_examples.setdefault(action_key, [])
                if requirement.original_text not in action_texts and len(action_texts) < 3:
                    action_texts.append(requirement.original_text)

            job_blockers.append(
                MatchBlockerJobSummary(
                    job_id=report.job_id,
                    missing_requirement_count=len(report.missing_requirement_ids),
                    requirements=tuple(job_requirements),
                    unresolved_missing_requirement_ids=tuple(job_unresolved),
                )
            )

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

        priority_actions = tuple(
            MatchBlockerActionSummary(
                requirement_type=action_key[0],
                normalized_capability=action_capabilities[action_key],
                missing_requirement_count=action_requirement_counts[action_key],
                affected_job_count=len(action_jobs[action_key]),
                affected_job_ids=tuple(action_jobs[action_key]),
                requirement_ids=tuple(action_requirement_ids[action_key]),
                examples=tuple(action_examples[action_key]),
            )
            for action_key in sorted(
                action_requirement_counts,
                key=lambda item: (
                    -len(action_jobs[item]),
                    -action_requirement_counts[item],
                    item[0].value,
                    action_capabilities[item] or action_examples[item][0],
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
            priority_actions=priority_actions,
            job_blockers=tuple(job_blockers),
        )
