"""Atomic correction of a manual job plus an immutable text observation."""

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_imports.manual import ManualJobInput, normalize_manual_job
from app.application.job_queries.manual_description import (
    ManualDescriptionBlocker,
    ManualDescriptionSaved,
    description_digest,
)
from app.application.ports.job_repository import JobImportItemWrite, JobImportWrite
from app.db.models import JobORM, JobSourceORM
from app.domain.jobs import ImportOutcome
from app.repositories.sqlalchemy_job_repository import SqlAlchemyJobRepository


class SqlAlchemyManualJobDescription:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._sessions = session_factory

    def save(self, job_id: str, *, description: str, expected_sha256: str) -> ManualDescriptionSaved | ManualDescriptionBlocker:
        try:
            with self._sessions.begin() as session:
                return self._save(session, job_id, description, expected_sha256)
        except IntegrityError:
            return "identity_conflict"

    @staticmethod
    def _save(session: Session, job_id: str, description: str, expected_sha256: str) -> ManualDescriptionSaved | ManualDescriptionBlocker:
        job = session.scalar(select(JobORM).where(JobORM.id == job_id).with_for_update())
        if job is None:
            return "not_found"
        sources = tuple(session.scalars(select(JobSourceORM).where(JobSourceORM.job_id == job_id)
            .order_by(JobSourceORM.last_seen_at.desc(), JobSourceORM.id.asc())))
        if not sources or any(source.source != "manual" for source in sources):
            return "source_read_only"
        source = sources[0]
        next_digest = description_digest(description)
        current_digest = description_digest(job.description)
        if job.description == description:
            return ManualDescriptionSaved(job_id, next_digest, False)
        if current_digest != expected_sha256:
            return "changed"

        report = normalize_manual_job(ManualJobInput(
            title=job.title, company=job.company, description=description, sourceUrl=source.source_url or None,
        ))
        observation = report.jobs[0]
        repo = SqlAlchemyJobRepository(session)
        target_source_id = source.id
        known_source = None
        if observation.source_job_id:
            known_source = repo.find_source_by_external_id("manual", observation.source_job_id)
            canonical_id = repo.find_job_id_by_canonical_key(observation.canonical_key)
            if (known_source and known_source.job_id != job_id) or (canonical_id and canonical_id != job_id):
                return "identity_conflict"
            if known_source:
                target_source_id = known_source.id

        result = session.execute(update(JobORM).where(
            JobORM.id == job_id, JobORM.description == job.description,
        ).values(description=description))
        if not result.rowcount:
            return "changed"

        if observation.source_job_id and not known_source:
            # The corrected no-URL text becomes another recognized paste identity.
            # Keep all previous identities and never reassign the JobLens ID.
            target_source_id = repo.add_source(job_id, observation)
        import_id = repo.add_import(JobImportWrite(
            source_version="manual-description-revision-v1", received=1, updated=1,
            source_snapshot={"provenanceKind": "user_paste_revision"}, collected_at=report.generated_at,
        ))
        repo.add_import_item(JobImportItemWrite(
            import_id=import_id, input_index=0, outcome=ImportOutcome.UPDATED, job_id=job_id,
            job_source_id=target_source_id, source_raw_snapshot={
                **observation.source_raw, "provenanceKind": "user_paste_revision",
                "previousDescriptionSha256": current_digest,
            },
        ))
        return ManualDescriptionSaved(job_id, next_digest, True)
