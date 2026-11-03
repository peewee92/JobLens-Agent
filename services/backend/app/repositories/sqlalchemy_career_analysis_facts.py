"""Capture released facts in one SQLite read snapshot; validate in caller transaction."""
from contextlib import contextmanager

from app.application.saved_career_analysis import (
    AnalysisFactRequest, AnalysisJobBinding, PinnedAnalysisFacts,
    AnalysisFactsChangedError, AnalysisInputsBlockedError,
)
from app.application.match_report_history import report_stale_reasons
from app.repositories.sqlalchemy_career_context_repository import SqlAlchemyCareerContextQueryRepository
from app.repositories.sqlalchemy_job_query_repository import SqlAlchemyJobQueryRepository
from app.repositories.sqlalchemy_job_requirement_repository import SqlAlchemyJobRequirementQueryRepository
from app.repositories.sqlalchemy_match_report_repository import SqlAlchemyMatchReportQueryRepository


class SqlAlchemyCareerAnalysisFacts:
    def __init__(self, factory, *, readiness):
        self._factory, self._readiness = factory, readiness

    def capture(self, request: AnalysisFactRequest) -> PinnedAnalysisFacts:
        # Readiness has no external calls. Check identities again inside the snapshot.
        readiness = tuple(self._readiness.execute(job_id) for job_id in request.selected_job_ids)
        if any(not item.preparation_inputs_ready for item in readiness):
            raise AnalysisInputsBlockedError("analysis inputs are not released")
        with self._factory() as session:
            if session.get_bind().dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN")
            reasons, context, reports, requirements, jobs = self._read(request, session)
            if reasons:
                raise AnalysisFactsChangedError("analysis facts changed")
            by_job = {item.report.job_id: item for item in reports}
            if any(job_id not in by_job for job_id in request.selected_job_ids):
                raise AnalysisFactsChangedError("selected jobs are outside the saved reports")
            extractions = tuple(requirements.get_extraction(job_id=job_id,
                extraction_id=by_job[job_id].report.extraction_id) for job_id in request.selected_job_ids)
            if any(item is None for item in extractions):
                raise AnalysisFactsChangedError("required extraction is missing")
            for ready, extraction in zip(readiness, extractions, strict=True):
                if (ready.profile_id, ready.profile_version, ready.extraction_id) != (
                    context.profile.id, context.profile.version, extraction.extraction_id):
                    raise AnalysisFactsChangedError("release identities changed")
            return PinnedAnalysisFacts(profile=context.profile,
                bindings=tuple(AnalysisJobBinding(item.report.job_id, item.report.extraction_id,
                    item.id, item.report.policy_version,
                    jobs[item.report.job_id].title, jobs[item.report.job_id].company) for item in reports),
                extractions=extractions, readiness=readiness)

    def stale_reasons(self, request: AnalysisFactRequest, *, session=None) -> tuple[str, ...]:
        if session is None:
            with self._factory() as owned:
                if owned.get_bind().dialect.name == "sqlite":
                    owned.connection().exec_driver_sql("BEGIN")
                return self.stale_reasons(request, session=owned)
        reasons = self._read(request, session)[0]
        # Caller holds the final SQLite write lock: release decisions cannot change
        # between these read-only gate queries and committing the result.
        for job_id in request.selected_job_ids:
            ready = self._readiness.execute(job_id)
            if not ready.preparation_inputs_ready:
                reasons = (*reasons, f"{job_id}:inputs_not_released")
        return tuple(dict.fromkeys(reasons))

    def _read(self, request, session):
        @contextmanager
        def borrowed():
            yield session  # Never close or commit the caller's unit of work.
        context = SqlAlchemyCareerContextQueryRepository(borrowed).get_current_context()
        requirements = SqlAlchemyJobRequirementQueryRepository(borrowed)
        report_repo = SqlAlchemyMatchReportQueryRepository(borrowed)
        jobs = SqlAlchemyJobQueryRepository(borrowed)
        reasons = []
        profile, intent = context.profile, context.search_intent
        if profile is None or (profile.id, profile.version) != (request.profile_id, request.profile_version):
            reasons.append("profile_changed")
        if intent is None or (intent.id, intent.version) != (request.search_intent_id, request.search_intent_version):
            reasons.append("search_intent_changed")
        reports = []
        captured_jobs = {}
        for report_id in request.match_report_ids:
            stored = report_repo.get(report_id)
            if stored is None:
                reasons.append("match_report_missing")
                continue
            reports.append(stored)
            report = stored.report
            captured_jobs[report.job_id] = jobs.get_job(report.job_id)
            reasons.extend(f"{report.job_id}:{reason}" for reason in report_stale_reasons(report,
                profile=profile, intent=intent, extraction=requirements.get_latest(report.job_id),
                job=captured_jobs[report.job_id]))
            latest = report_repo.list_latest_for_jobs((report.job_id,))
            if not latest or latest[0].id != stored.id:
                reasons.append(f"{report.job_id}:match_report_changed")
        if not request.match_report_ids:
            reasons.append("match_reports_missing")
        return tuple(dict.fromkeys(reasons)), context, tuple(reports), requirements, captured_jobs
