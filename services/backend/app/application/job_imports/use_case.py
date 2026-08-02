"""Application use case for idempotent Collector job imports."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from app.application.job_imports.adapter import adapt_collector_report
from app.application.job_imports.errors import ImportIdentityConflictError
from app.application.job_imports.models import ImportIssue, NormalizedJobInput
from app.application.job_imports.normalizer import normalize_adapted_report
from app.application.ports import (
    AbstractUnitOfWork,
    JobImportCandidateWrite,
    JobImportItemWrite,
    JobImportWrite,
    JobSourceRef,
)
from app.domain.jobs import ImportOutcome

UnitOfWorkFactory = Callable[[], AbstractUnitOfWork]


@dataclass(frozen=True, slots=True)
class ImportErrorDetail:
    """One non-fatal item-level issue returned by the use case."""

    index: int
    stage: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ImportJobsResult:
    """Stable application result for a completed import transaction."""

    import_id: str
    source_version: str
    received: int
    created: int
    updated: int
    skipped: int
    errors: tuple[ImportErrorDetail, ...]


class ImportJobsUseCase:
    """Adapt, normalize and persist one Collector report atomically."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, payload: Mapping[str, Any]) -> ImportJobsResult:
        """Import one report using one Unit of Work and exactly one commit.

        Envelope/version errors are raised before a transaction is opened.
        Item-level adapter/normalizer errors are audited and counted as skipped.
        Persistent identity conflicts are fatal and roll back the whole batch.
        """

        normalized_report = normalize_adapted_report(adapt_collector_report(payload))
        error_details = tuple(self._error_detail(issue) for issue in normalized_report.issues)
        error_records = tuple(self._error_record(issue) for issue in normalized_report.issues)

        created = 0
        updated = 0
        skipped = len(normalized_report.issues)

        with self._uow_factory() as uow:
            import_id = uow.jobs.add_import(
                JobImportWrite(
                    source_version=normalized_report.source_version,
                    collector_version=normalized_report.source_version,
                    received=normalized_report.received,
                    errors=error_records,
                    search_intent_snapshot=deepcopy(normalized_report.config),
                    source_snapshot={
                        "statistics": deepcopy(normalized_report.statistics),
                        "candidateCount": normalized_report.candidate_count,
                    },
                    collected_at=normalized_report.generated_at,
                )
            )
            uow.jobs.add_import_candidates(
                tuple(
                    self._candidate_write(import_id, index, candidate)
                    for index, candidate in enumerate(normalized_report.candidates_raw)
                )
            )

            for issue in normalized_report.issues:
                if issue.index is None:
                    raise RuntimeError("item-level import issue is missing input index")
                uow.jobs.add_import_item(
                    JobImportItemWrite(
                        import_id=import_id,
                        input_index=issue.index,
                        outcome=ImportOutcome.ERROR,
                        error_code=issue.code,
                        error_message=issue.message,
                    )
                )

            for job in sorted(
                normalized_report.jobs,
                key=lambda item: item.input_index,
            ):
                outcome, job_id, source_id = self._persist_job(uow, job)
                if outcome is ImportOutcome.CREATED:
                    created += 1
                else:
                    updated += 1

                uow.jobs.add_import_item(
                    JobImportItemWrite(
                        import_id=import_id,
                        input_index=job.input_index,
                        outcome=outcome,
                        job_id=job_id,
                        job_source_id=source_id,
                    )
                )

            if normalized_report.received != created + updated + skipped:
                raise RuntimeError("import counters do not match received item count")

            uow.jobs.update_import_summary(
                import_id,
                created=created,
                updated=updated,
                skipped=skipped,
                errors=error_records,
            )
            uow.commit()

        return ImportJobsResult(
            import_id=import_id,
            source_version=normalized_report.source_version,
            received=normalized_report.received,
            created=created,
            updated=updated,
            skipped=skipped,
            errors=error_details,
        )

    def _persist_job(
        self,
        uow: AbstractUnitOfWork,
        job: NormalizedJobInput,
    ) -> tuple[ImportOutcome, str, str]:
        existing_job_id = uow.jobs.find_job_id_by_canonical_key(job.canonical_key)
        existing_source = self._find_existing_source(uow, job)

        if existing_job_id is None and existing_source is not None:
            raise ImportIdentityConflictError(
                "source identity already exists but canonical job identity does not"
            )

        if existing_job_id is None:
            job_id = uow.jobs.add_job(job)
            source_id = uow.jobs.add_source(job_id, job)
            return ImportOutcome.CREATED, job_id, source_id

        if existing_source is not None and existing_source.job_id != existing_job_id:
            raise ImportIdentityConflictError(
                "canonical job and source identity point to different jobs"
            )

        uow.jobs.update_job(existing_job_id, job)
        if existing_source is None:
            source_id = uow.jobs.add_source(existing_job_id, job)
        else:
            uow.jobs.update_source(existing_source.id, job)
            source_id = existing_source.id

        return ImportOutcome.UPDATED, existing_job_id, source_id

    def _find_existing_source(
        self,
        uow: AbstractUnitOfWork,
        job: NormalizedJobInput,
    ) -> JobSourceRef | None:
        source_by_external_id = None
        if job.source_job_id is not None:
            source_by_external_id = uow.jobs.find_source_by_external_id(
                job.source,
                job.source_job_id,
            )

        source_by_url = uow.jobs.find_source_by_normalized_url(
            job.source,
            job.normalized_source_url,
        )

        if (
            source_by_external_id is not None
            and source_by_url is not None
            and source_by_external_id != source_by_url
        ):
            raise ImportIdentityConflictError(
                "external source ID and normalized URL resolve to different source rows"
            )

        return source_by_external_id or source_by_url

    @classmethod
    def _candidate_write(
        cls,
        import_id: str,
        candidate_index: int,
        candidate: Any,
    ) -> JobImportCandidateWrite:
        record = candidate if isinstance(candidate, Mapping) else {}
        return JobImportCandidateWrite(
            import_id=import_id,
            candidate_index=candidate_index,
            candidate_raw=deepcopy(candidate),
            keep=record.get("keep") if isinstance(record.get("keep"), bool) else None,
            decision=cls._candidate_text(record, "decision", 512),
            pending_detail=(
                record.get("pendingDetail")
                if isinstance(record.get("pendingDetail"), bool)
                else None
            ),
            source_job_id=cls._candidate_text(record, "sourceJobId", 255),
            source_url=cls._candidate_text(record, "url", 2048),
            title=cls._candidate_text(record, "title", 255),
            company=cls._candidate_text(record, "company", 255),
        )

    @staticmethod
    def _candidate_text(
        record: Mapping[str, Any],
        key: str,
        max_length: int,
    ) -> str | None:
        value = record.get(key)
        if not isinstance(value, str):
            return None
        return value[:max_length]

    @staticmethod
    def _error_detail(issue: ImportIssue) -> ImportErrorDetail:
        if issue.index is None:
            raise RuntimeError("item-level import issue is missing input index")
        return ImportErrorDetail(
            index=issue.index,
            stage=issue.stage,
            code=issue.code,
            message=issue.message,
        )

    @staticmethod
    def _error_record(issue: ImportIssue) -> dict[str, Any]:
        if issue.index is None:
            raise RuntimeError("item-level import issue is missing input index")
        record: dict[str, Any] = {
            "index": issue.index,
            "stage": issue.stage,
            "code": issue.code,
            "message": issue.message,
        }
        if issue.raw is not None:
            record["raw"] = deepcopy(issue.raw)
        return record
