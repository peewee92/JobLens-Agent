"""Short SQLite transactions around, never during, the external request."""
from datetime import UTC, datetime
from hashlib import sha256
from sqlalchemy import select
from app.db.models import JobORM, JobRequirementExtractionORM, RequirementCallORM
from app.repositories.sqlalchemy_job_requirement_unit_of_work import SqlAlchemyJobRequirementUnitOfWork


from app.application.job_requirements.call_models import RequirementCallConflict, digest


def public_record(row, artifact_field="extraction_id", artifact_key="extractionId"):
    age = datetime.now(UTC) - row.created_at.replace(tzinfo=UTC)
    status = "uncertain" if row.status == "running" and age.total_seconds() > 120 else row.status
    return dict(actionId=row.action_id, jobId=row.job_id, status=status,
        attempts=row.attempts, responseStatus=row.response_status,
        inputTokens=row.input_tokens, outputTokens=row.output_tokens,
        **{artifact_key: getattr(row, artifact_field)}, errorCode=row.error_code,
        model=row.snapshot["model"], maxOutputTokens=row.snapshot["maxOutputTokens"],
        timeoutSeconds=row.snapshot["timeoutSeconds"])


def assert_snapshot(session, job_id, snapshot):
    job = session.get(JobORM, job_id)
    if job is None or job.user_marked_inactive:
        raise RequirementCallConflict("job_unavailable")
    latest = session.scalar(select(JobRequirementExtractionORM.id)
        .where(JobRequirementExtractionORM.job_id == job_id)
        .order_by(JobRequirementExtractionORM.created_at.desc(), JobRequirementExtractionORM.id.asc()).limit(1))
    if (sha256((job.description or "").strip().encode()).hexdigest() != snapshot["inputHash"]
        or job.availability_revision != snapshot["availabilityRevision"]
        or latest != snapshot["previousExtractionId"]):
        raise RequirementCallConflict("extraction_plan_stale")


class SqlAlchemyRequirementCalls:
    def __init__(self, session_factory, *, record_type=RequirementCallORM,
                 snapshot_validator=assert_snapshot, serializer=public_record):
        self.sessions = session_factory
        self.record_type = record_type
        self.assert_snapshot = snapshot_validator
        self.public_record = serializer

    def get(self, job_id, action_id=None):
        with self.sessions() as session:
            query = select(self.record_type).where(self.record_type.job_id == job_id)
            query = query.where(self.record_type.action_id == action_id) if action_id else query.order_by(self.record_type.created_at.desc(), self.record_type.action_id.desc())
            row = session.scalars(query).first()
            return self.public_record(row) if row else None

    def reserve(self, *, job_id, action_id, command, snapshot, acknowledged):
        command_digest = digest(command)
        with self.sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            old = session.get(self.record_type, action_id)
            if old:
                if old.job_id != job_id or old.command_digest != command_digest:
                    raise RequirementCallConflict("command_content_conflict")
                return self.public_record(old), False
            self.assert_snapshot(session, job_id, snapshot)
            prior = session.scalars(select(self.record_type).where(self.record_type.job_id == job_id)
                .order_by(self.record_type.created_at.desc(), self.record_type.action_id.desc())).first()
            if prior:
                state = self.public_record(prior)["status"]
                if state == "running":
                    raise RequirementCallConflict("extraction_already_running")
                if state == "uncertain":
                    if acknowledged != prior.action_id:
                        raise RequirementCallConflict("prior_call_outcome_uncertain")
                    prior.status = "uncertain"  # fences a late previous executor
            row = self.record_type(action_id=action_id, job_id=job_id,
                command_digest=command_digest, snapshot=snapshot, status="running",
                created_at=datetime.now(UTC), attempts=0)
            session.add(row)
            session.commit()
            return self.public_record(row), True

    def begin_attempt(self, action_id):
        with self.sessions() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            row = session.get(self.record_type, action_id)
            if row is None or row.status != "running" or row.attempts != 0:
                raise RequirementCallConflict("call_budget_or_execution_conflict")
            self.assert_snapshot(session, row.job_id, row.snapshot)
            row.attempts = 1  # may have been sent; a crash never permits automatic replay
            session.commit()

    def received(self, action_id, status, usage):
        def token(name, fallback):
            value = usage.get(name, usage.get(fallback))
            return value if type(value) is int and value >= 0 else None
        with self.sessions.begin() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            row = session.get(self.record_type, action_id)
            if row.status == "running":
                row.response_status = status
                row.input_tokens = token("input_tokens", "prompt_tokens")
                row.output_tokens = token("output_tokens", "completion_tokens")

    def fail(self, action_id, code):
        with self.sessions.begin() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            row = session.get(self.record_type, action_id)
            if row and row.status == "running":
                row.status = "uncertain" if row.attempts and row.response_status is None else "failed"
                row.error_code = code


class _TrackedRequirements:
    def __init__(self, repository):
        self.repository = repository
        self.extraction_id = None

    def add(self, write):
        self.extraction_id = write.extraction_id
        self.repository.add(write)


class AuthorizedRequirementUnitOfWork(SqlAlchemyJobRequirementUnitOfWork):
    def __init__(self, session_factory, action_id):
        super().__init__(session_factory)
        self.action_id = action_id

    def __enter__(self):
        super().__enter__()
        self.requirements = _TrackedRequirements(self.requirements)
        return self

    def ensure_latest_extraction(self, job_id, expected_id):
        super().ensure_latest_extraction(job_id, expected_id)
        row = self._session.get(RequirementCallORM, self.action_id)
        if row is None or row.status != "running":
            raise RequirementCallConflict("execution_superseded")
        assert_snapshot(self._session, row.job_id, row.snapshot)

    def commit(self):
        session = self._session
        row = session.get(RequirementCallORM, self.action_id)
        if row is None or row.status != "running":
            raise RequirementCallConflict("execution_superseded")
        row.status = "completed"
        row.extraction_id = self.requirements.extraction_id
        super().commit()  # artifact and completion either both commit or both roll back
