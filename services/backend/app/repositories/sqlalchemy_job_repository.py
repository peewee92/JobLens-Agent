"""SQLAlchemy implementation of the job persistence application port."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.job_imports.models import NormalizedJobInput
from app.application.ports.job_repository import (
    AbstractJobRepository,
    JobImportCandidateWrite,
    JobImportItemWrite,
    JobImportWrite,
    JobSourceRef,
    RepositoryRecordNotFound,
)
from app.db.models import (
    JobImportCandidateORM,
    JobImportItemORM,
    JobImportORM,
    JobORM,
    JobSourceORM,
)


class SqlAlchemyJobRepository(AbstractJobRepository):
    """Persist job-import state using one caller-owned SQLAlchemy Session.

    The repository never creates a Session and never commits or rolls back.
    It may flush so generated IDs and database constraint errors are visible
    before the surrounding Unit of Work decides whether to commit.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_job_id_by_canonical_key(self, canonical_key: str) -> str | None:
        statement = select(JobORM.id).where(JobORM.canonical_key == canonical_key)
        return self._session.scalar(statement)

    def find_source_by_external_id(
        self, source: str, source_job_id: str
    ) -> JobSourceRef | None:
        statement = select(JobSourceORM.id, JobSourceORM.job_id).where(
            JobSourceORM.source == source,
            JobSourceORM.source_job_id == source_job_id,
        )
        row = self._session.execute(statement).one_or_none()
        return None if row is None else JobSourceRef(id=row.id, job_id=row.job_id)

    def find_source_by_normalized_url(
        self, source: str, normalized_source_url: str
    ) -> JobSourceRef | None:
        statement = select(JobSourceORM.id, JobSourceORM.job_id).where(
            JobSourceORM.source == source,
            JobSourceORM.normalized_source_url == normalized_source_url,
        )
        row = self._session.execute(statement).one_or_none()
        return None if row is None else JobSourceRef(id=row.id, job_id=row.job_id)

    def add_job(self, data: NormalizedJobInput) -> str:
        model = JobORM(
            canonical_key=data.canonical_key,
            canonical_key_version=data.canonical_key_version,
            title=data.title,
            company=data.company,
            area=data.area,
            salary_min_k=data.salary_min_k,
            salary_max_k=data.salary_max_k,
            experience=data.experience,
            education=data.education,
            description=data.description,
            skills=list(data.skills),
            remote_status=data.remote_status,
            remote_confidence=data.remote_confidence,
        )
        self._session.add(model)
        self._session.flush()
        return model.id

    def update_job(self, job_id: str, data: NormalizedJobInput) -> None:
        model = self._session.get(JobORM, job_id)
        if model is None:
            raise RepositoryRecordNotFound(f"Job not found: {job_id}")

        model.title = data.title
        model.company = data.company
        model.area = data.area
        model.salary_min_k = data.salary_min_k
        model.salary_max_k = data.salary_max_k
        model.experience = data.experience
        model.education = data.education
        model.description = data.description
        model.skills = list(data.skills)
        model.remote_status = data.remote_status
        model.remote_confidence = data.remote_confidence
        self._session.flush()

    def add_source(self, job_id: str, data: NormalizedJobInput) -> str:
        model = JobSourceORM(
            job_id=job_id,
            source=data.source,
            source_job_id=data.source_job_id,
            source_url=data.source_url,
            normalized_source_url=data.normalized_source_url,
            source_version=data.source_version,
            source_raw=dict(data.source_raw),
            first_seen_at=data.first_seen_at,
            last_seen_at=data.last_seen_at,
            collected_at=data.collected_at,
        )
        self._session.add(model)
        self._session.flush()
        return model.id

    def update_source(self, source_id: str, data: NormalizedJobInput) -> None:
        model = self._session.get(JobSourceORM, source_id)
        if model is None:
            raise RepositoryRecordNotFound(f"JobSource not found: {source_id}")

        model.source_job_id = data.source_job_id
        model.source_url = data.source_url
        model.normalized_source_url = data.normalized_source_url
        model.source_version = data.source_version
        model.source_raw = dict(data.source_raw)
        model.last_seen_at = data.last_seen_at
        model.collected_at = data.collected_at
        self._session.flush()

    def add_import(self, data: JobImportWrite) -> str:
        model = JobImportORM(
            source_version=data.source_version,
            collector_version=data.collector_version,
            received=data.received,
            created=data.created,
            updated=data.updated,
            skipped=data.skipped,
            errors=[dict(error) for error in data.errors],
            search_intent_snapshot=dict(data.search_intent_snapshot),
            source_snapshot=dict(data.source_snapshot),
            collected_at=data.collected_at,
        )
        self._session.add(model)
        self._session.flush()
        return model.id

    def update_import_summary(
        self,
        import_id: str,
        *,
        created: int,
        updated: int,
        skipped: int,
        errors: tuple[dict[str, Any], ...],
    ) -> None:
        model = self._session.get(JobImportORM, import_id)
        if model is None:
            raise RepositoryRecordNotFound(f"JobImport not found: {import_id}")

        model.created = created
        model.updated = updated
        model.skipped = skipped
        model.errors = [dict(error) for error in errors]
        self._session.flush()

    def add_import_candidates(
        self, candidates: tuple[JobImportCandidateWrite, ...]
    ) -> None:
        models = [
            JobImportCandidateORM(
                import_id=data.import_id,
                candidate_index=data.candidate_index,
                keep=data.keep,
                decision=data.decision,
                pending_detail=data.pending_detail,
                source_job_id=data.source_job_id,
                source_url=data.source_url,
                title=data.title,
                company=data.company,
                candidate_raw=deepcopy(data.candidate_raw),
            )
            for data in candidates
        ]
        if not models:
            return
        self._session.add_all(models)
        self._session.flush()

    def add_import_item(self, data: JobImportItemWrite) -> str:
        model = JobImportItemORM(
            import_id=data.import_id,
            input_index=data.input_index,
            job_id=data.job_id,
            job_source_id=data.job_source_id,
            outcome=data.outcome,
            error_code=data.error_code,
            error_message=data.error_message,
        )
        self._session.add(model)
        self._session.flush()
        return model.id
