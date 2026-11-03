"""Read original snapshots; derive currentness without changing career facts."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from hashlib import sha256

from app.application.career_context.models import ProfileDetail, SearchIntentDetail
from app.application.job_queries.models import JobDetail, JobListItem
from app.application.job_requirements.models import JobRequirementExtractionDetail
from app.application.job_requirements.release import GetJobRequirementReleaseReadinessUseCase
from app.application.ports.career_context_repository import AbstractCareerContextQueryRepository
from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.application.ports.job_requirement_repository import AbstractJobRequirementQueryRepository
from app.application.ports.match_report_repository import AbstractMatchReportQueryRepository

from app.application.job_queries import JobNotFoundError
from app.application.evidence_retrieval.strategy import RETRIEVAL_VERSION
from app.application.match_policy_version import CURRENT_MATCH_POLICY_VERSION
from app.application.match_report import MatchReport, MatchReportPersistenceNotReadyError, StoredMatchReport
from app.application.search_preferences import preference_input_fingerprint


def report_stale_reasons(
    report: MatchReport, *, profile: ProfileDetail | None,
    intent: SearchIntentDetail | None, extraction: JobRequirementExtractionDetail | None,
    job: JobDetail | JobListItem | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if report.retrieval_version != RETRIEVAL_VERSION:
        reasons.append("retrieval_changed")
    if report.policy_version != CURRENT_MATCH_POLICY_VERSION:
        reasons.append("policy_changed")
    if profile is None:
        reasons.append("profile_missing")
    elif (report.profile_id, report.profile_version) != (profile.id, profile.version):
        reasons.append("profile_changed")
    if intent is None:
        reasons.append("search_intent_missing")
    elif (report.search_intent_id, report.search_intent_version) != (intent.id, intent.version):
        reasons.append("search_intent_changed")
    if extraction is None:
        reasons.append("requirements_missing")
    elif report.extraction_id != extraction.extraction_id:
        reasons.append("requirements_changed")
    if extraction is not None and job is not None:
        input_hash = getattr(extraction, "input_hash", None)
        if not isinstance(job, JobDetail) or not isinstance(input_hash, str) or not input_hash:
            # A list projection or an incomplete historical extraction cannot prove currentness.
            reasons.append("job_description_unavailable")
        else:
            current_hash = sha256((job.description or "").strip().encode("utf-8")).hexdigest()
            if input_hash != current_hash:
                reasons.append("job_description_changed")
    if job is None:
        reasons.append("job_missing")
    else:
        if isinstance(job, JobDetail) and job.user_marked_inactive:
            reasons.append("job_user_marked_inactive")
        if intent is not None and report.preference_fingerprint != preference_input_fingerprint(intent, job):
            reasons.append("preference_inputs_changed")
    return tuple(reasons)


@dataclass(frozen=True, slots=True)
class MatchReportHistoryEntry:
    stored: StoredMatchReport
    stale_reasons: tuple[str, ...]


class GetMatchReportHistoryUseCase:
    def __init__(
        self, *, reports: AbstractMatchReportQueryRepository,
        context: AbstractCareerContextQueryRepository, jobs: AbstractJobQueryRepository,
        requirements: AbstractJobRequirementQueryRepository, persistence_ready: Callable[[], bool],
        requirement_release: GetJobRequirementReleaseReadinessUseCase,
    ) -> None:
        self._reports = reports
        self._context = context
        self._jobs = jobs
        self._requirements = requirements
        self._requirement_release = requirement_release
        self._persistence_ready = persistence_ready

    def execute(self, job_id: str) -> tuple[MatchReportHistoryEntry, ...]:
        job = self._jobs.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"Job not found: {job_id}")
        if not self._persistence_ready():
            raise MatchReportPersistenceNotReadyError("MatchReport persistence schema is not ready")
        profile = self._context.get_current_profile()
        intent = self._context.get_current_search_intent()
        extraction = self._requirements.get_latest(job_id)
        entries = tuple(
            MatchReportHistoryEntry(item, report_stale_reasons(
                item.report, profile=profile, intent=intent, extraction=extraction, job=job,
            )) for item in self._reports.list_for_job(job_id)
        )
        if any(not entry.stale_reasons for entry in entries) and not self._requirement_release.execute(job_id).release_eligible:
            return tuple(MatchReportHistoryEntry(entry.stored, entry.stale_reasons or ("requirements_not_released",)) for entry in entries)
        return entries
