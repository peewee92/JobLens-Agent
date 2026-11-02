"""Reuse the single-attempt lifecycle; guard immutable match inputs and report commit."""
from sqlalchemy import select
from app.db.models import SemanticCallORM, UserProfileORM, SearchIntentORM
from app.repositories.sqlalchemy_requirement_call import (
    SqlAlchemyRequirementCalls, public_record, assert_snapshot as assert_job_snapshot,
)
from app.repositories.sqlalchemy_match_report_unit_of_work import SqlAlchemyMatchReportUnitOfWork
from app.application.job_requirements.call_models import RequirementCallConflict


def assert_snapshot(session, job_id, snapshot):
    assert_job_snapshot(session, job_id, snapshot)
    profile = session.scalar(select(UserProfileORM.id).where(UserProfileORM.profile_key == "default")
        .order_by(UserProfileORM.version.desc()).limit(1))
    intent = session.scalar(select(SearchIntentORM.id).where(SearchIntentORM.intent_key == "default")
        .order_by(SearchIntentORM.version.desc()).limit(1))
    if profile != snapshot["profileId"] or intent != snapshot["searchIntentId"]:
        raise RequirementCallConflict("match_facts_changed")


def semantic_record(row):
    return public_record(row, "report_id", "reportId")


class SqlAlchemySemanticCalls(SqlAlchemyRequirementCalls):
    def __init__(self, session_factory):
        super().__init__(session_factory, record_type=SemanticCallORM,
            snapshot_validator=assert_snapshot, serializer=semantic_record)


class _TrackedReports:
    def __init__(self, repository):
        self.repository, self.report_id = repository, None

    def add(self, report):
        stored = self.repository.add(report)
        self.report_id = stored.id
        return stored


class AuthorizedSemanticUnitOfWork(SqlAlchemyMatchReportUnitOfWork):
    def __init__(self, session_factory, action_id):
        super().__init__(session_factory)
        self.action_id = action_id

    def __enter__(self):
        super().__enter__()
        self.reports = _TrackedReports(self.reports)
        return self

    def ensure_job_availability(self, job_id, revision):
        super().ensure_job_availability(job_id, revision)  # BEGIN IMMEDIATE, after model work
        row = self._active_session().get(SemanticCallORM, self.action_id)
        if row is None or row.status != "running":
            raise RequirementCallConflict("execution_superseded")
        assert_snapshot(self._active_session(), job_id, row.snapshot)

    def commit(self):
        row = self._active_session().get(SemanticCallORM, self.action_id)
        if row is None or row.status != "running":
            raise RequirementCallConflict("execution_superseded")
        row.status, row.report_id = "completed", self.reports.report_id
        super().commit()
