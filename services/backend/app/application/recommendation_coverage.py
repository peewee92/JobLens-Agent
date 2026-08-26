"""Read-only coverage planning for the main JobLens recommendation loop."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.application.career_context.models import SearchIntentDetail
from app.application.job_queries.models import JobListItem, JobListQuery
from app.application.job_queries.use_cases import ListJobsUseCase
from app.application.match_inputs.readiness import GetMatchInputReadinessUseCase
from app.application.match_ranking import BatchRankMatchReportsUseCase
from app.application.ports.career_context_repository import AbstractCareerContextQueryRepository


class RecommendationCoverageStatus(StrEnum):
    CURRENT_REPORT = "current_report"
    MATCH_READY = "match_ready"
    REQUIREMENT_ANALYSIS_NEEDED = "requirement_analysis_needed"
    PROFILE_BLOCKED = "profile_blocked"
    OTHER_BLOCKED = "other_blocked"


@dataclass(frozen=True, slots=True)
class RecommendationCoverageCandidate:
    job_id: str
    title: str
    company: str
    area: str | None
    salary_min_k: float | None
    salary_max_k: float | None
    status: RecommendationCoverageStatus
    blocker_codes: tuple[str, ...]
    intent_signals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecommendationCoverage:
    total_job_count: int
    considered_job_count: int
    current_report_count: int
    match_ready_without_report_count: int
    requirement_analysis_needed_count: int
    profile_blocked_count: int
    other_blocked_count: int
    next_analysis_candidates: tuple[RecommendationCoverageCandidate, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


_GENERIC_ROLE_SUFFIXES = (
    "开发工程师",
    "研发工程师",
    "工程师",
    "产品经理",
    "开发",
    "研发",
    "经理",
)


def _compact(value: str) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value.casefold())


def _meaningful_role_stem(stem: str) -> bool:
    if len(stem) < 2:
        return False
    if stem.isascii():
        return len(stem) >= 3
    return sum("\u4e00" <= char <= "\u9fff" for char in stem) >= 2


def _role_keys(role: str) -> tuple[str, ...]:
    compact = _compact(role)
    keys = [compact] if compact else []
    for suffix in _GENERIC_ROLE_SUFFIXES:
        compact_suffix = _compact(suffix)
        if compact.endswith(compact_suffix):
            stem = compact[: -len(compact_suffix)]
            if _meaningful_role_stem(stem):
                keys.append(stem)
    return tuple(dict.fromkeys(keys))


def _target_role_matches(title: str, target_roles: tuple[str, ...]) -> tuple[str, ...]:
    compact_title = _compact(title)
    matches: list[str] = []
    for role in target_roles:
        if any(key and key in compact_title for key in _role_keys(role)):
            matches.append(role)
    return tuple(matches)


def _city_matches(area: str | None, cities: tuple[str, ...]) -> tuple[str, ...]:
    compact_area = _compact(area or "")
    return tuple(city for city in cities if _compact(city) in compact_area)


def _salary_signal(job: JobListItem, intent: SearchIntentDetail) -> str | None:
    minimum = intent.minimum_salary_k
    if minimum is None:
        return None
    if job.salary_min_k is not None and job.salary_min_k >= minimum:
        return f"薪资下限达到 {minimum:g}K"
    if job.salary_max_k is not None and job.salary_max_k < minimum:
        return None
    if job.salary_max_k is not None and job.salary_max_k >= minimum:
        return f"薪资区间覆盖 {minimum:g}K"
    return None


def _intent_signals(job: JobListItem, intent: SearchIntentDetail | None) -> tuple[str, ...]:
    if intent is None:
        return ()
    signals: list[str] = []
    role_matches = _target_role_matches(job.title, intent.target_roles)
    if role_matches:
        signals.append(f"目标方向：{role_matches[0]}")
    city_matches = _city_matches(job.area, intent.cities)
    if city_matches:
        signals.append(f"目标城市：{city_matches[0]}")
    salary = _salary_signal(job, intent)
    if salary:
        signals.append(salary)
    if intent.remote_accepted and job.remote_status.value == "confirmed":
        signals.append("支持远程")
    return tuple(signals)


def _candidate_sort_key(candidate: RecommendationCoverageCandidate, source_index: int) -> tuple[int, int, int]:
    role_signal = any(value.startswith("目标方向：") for value in candidate.intent_signals)
    city_signal = any(value.startswith("目标城市：") for value in candidate.intent_signals)
    salary_signal = any(value.startswith("薪资") for value in candidate.intent_signals)
    return (
        -(3 * int(role_signal) + 2 * int(city_signal) + int(salary_signal)),
        -len(candidate.intent_signals),
        source_index,
    )


class BuildRecommendationCoverageUseCase:
    """Explain recommendation coverage and prioritize the next jobs to analyze."""

    MAX_JOBS = 50
    NEXT_CANDIDATE_LIMIT = 5

    def __init__(
        self,
        *,
        jobs: ListJobsUseCase,
        match_inputs: GetMatchInputReadinessUseCase,
        ranking: BatchRankMatchReportsUseCase,
        career_context: AbstractCareerContextQueryRepository,
    ) -> None:
        self._jobs = jobs
        self._match_inputs = match_inputs
        self._ranking = ranking
        self._career_context = career_context

    def execute(self) -> RecommendationCoverage:
        page = self._jobs.execute(JobListQuery(limit=self.MAX_JOBS, offset=0))
        job_ids = tuple(item.id for item in page.items)
        reports = self._ranking.execute(job_ids, include_blocked=True)
        current_report_job_ids = {item.report.job_id for item in reports}
        intent = self._career_context.get_current_search_intent()

        current_report_count = 0
        match_ready_without_report_count = 0
        requirement_analysis_needed_count = 0
        profile_blocked_count = 0
        other_blocked_count = 0
        refresh_candidates: list[tuple[int, RecommendationCoverageCandidate]] = []

        for index, job in enumerate(page.items):
            if job.id in current_report_job_ids:
                current_report_count += 1
                continue

            readiness = self._match_inputs.execute(job.id)
            blocker_codes = tuple(item.code for item in readiness.blockers)
            if readiness.inputs_release_eligible:
                match_ready_without_report_count += 1
                continue

            if not readiness.career_context.release_eligible:
                profile_blocked_count += 1
                continue

            if not readiness.job_requirements.release_eligible:
                requirement_analysis_needed_count += 1
                candidate = RecommendationCoverageCandidate(
                    job_id=job.id,
                    title=job.title,
                    company=job.company,
                    area=job.area,
                    salary_min_k=job.salary_min_k,
                    salary_max_k=job.salary_max_k,
                    status=RecommendationCoverageStatus.REQUIREMENT_ANALYSIS_NEEDED,
                    blocker_codes=blocker_codes,
                    intent_signals=_intent_signals(job, intent),
                )
                refresh_candidates.append((index, candidate))
                continue

            other_blocked_count += 1

        refresh_candidates.sort(key=lambda pair: _candidate_sort_key(pair[1], pair[0]))
        return RecommendationCoverage(
            total_job_count=page.total,
            considered_job_count=len(page.items),
            current_report_count=current_report_count,
            match_ready_without_report_count=match_ready_without_report_count,
            requirement_analysis_needed_count=requirement_analysis_needed_count,
            profile_blocked_count=profile_blocked_count,
            other_blocked_count=other_blocked_count,
            next_analysis_candidates=tuple(
                candidate
                for _, candidate in refresh_candidates[: self.NEXT_CANDIDATE_LIMIT]
            ),
        )
