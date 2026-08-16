"""Resumable orchestration from a Collector review dataset to one frozen Batch."""
from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Mapping, Sequence
from uuid import uuid4

from app.application.job_imports import ImportJobsUseCase
from app.application.ports import (
    AbstractJobImportQueryRepository,
    AbstractJobQueryRepository,
    AbstractJobRequirementQueryRepository,
    AbstractRequirementAcceptanceRunQueryRepository,
    AbstractRequirementReviewQueryRepository,
)
from app.application.ports.requirement_acceptance_run_unit_of_work import (
    AbstractRequirementAcceptanceRunUnitOfWork,
)
from app.application.job_queries.errors import JobNotFoundError
from app.application.job_requirements.errors import (
    InvalidRequirementExtractorOutputError,
    JobDescriptionNotExtractableError,
    RequirementExtractorFailedError,
    RequirementExtractorUnavailableError,
)
from app.application.job_requirements.models import JobRequirementExtractionDetail
from app.application.job_requirements.use_cases import ExtractJobRequirementsUseCase
from app.application.requirement_acceptance.errors import (
    InvalidRequirementAcceptanceDatasetError,
    RequirementAcceptanceCanaryGateError,
    RequirementAcceptanceExecutionLeaseLostError,
    RequirementAcceptanceExecutionLeaseUnavailableError,
    RequirementAcceptanceImportError,
)
from app.application.requirement_acceptance.execution_lease import (
    DEFAULT_REQUIREMENT_ACCEPTANCE_EXECUTION_LEASE_TTL_SECONDS,
    requirement_acceptance_execution_lease_key,
)
from app.application.requirement_acceptance.models import (
    RequirementAcceptanceCaseResult,
    RequirementAcceptanceCaseStatus,
    RequirementAcceptancePreparationResult,
)
from app.application.requirement_acceptance.runs import (
    RequirementAcceptanceCanaryDecision,
    RequirementAcceptancePreflight,
    RequirementAcceptanceRunCaseStatus,
    RequirementAcceptanceRunCaseUpdate,
    RequirementAcceptanceRunCaseWrite,
    RequirementAcceptanceRunDetail,
    RequirementAcceptanceRunWrite,
)
from app.application.requirement_reviews.models import RequirementReviewBatchDetail
from app.application.requirement_reviews.use_cases import (
    CreateRequirementReviewBatchUseCase,
)
from app.domain.jobs import ImportOutcome

FORMAL_SAMPLE_SIZE = 20
_BATCH_PAGE_SIZE = 100
RequirementAcceptanceRunUnitOfWorkFactory = Callable[
    [], AbstractRequirementAcceptanceRunUnitOfWork
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PrepareRequirementAcceptanceBatchUseCase:
    """Import, resume Extraction work, then create/reuse an exact Review Batch.

    Import is atomic. Each Requirement Extraction keeps its own transaction and Trace,
    so successful cases remain reusable when a later provider call fails. Batch
    creation is deliberately deferred until all 20 cases have current same-cohort
    Extractions.
    """

    def __init__(
        self,
        *,
        import_jobs: ImportJobsUseCase,
        imports: AbstractJobImportQueryRepository,
        jobs: AbstractJobQueryRepository,
        requirements: AbstractJobRequirementQueryRepository,
        extract_requirements: ExtractJobRequirementsUseCase,
        acceptance_runs: AbstractRequirementAcceptanceRunQueryRepository,
        acceptance_run_uow_factory: RequirementAcceptanceRunUnitOfWorkFactory,
        reviews: AbstractRequirementReviewQueryRepository,
        create_batch: CreateRequirementReviewBatchUseCase,
        provider: str,
        model: str,
        extractor_version: str,
        prompt_version: str,
        execution_lease_ttl_seconds: int = (
            DEFAULT_REQUIREMENT_ACCEPTANCE_EXECUTION_LEASE_TTL_SECONDS
        ),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._import_jobs = import_jobs
        self._imports = imports
        self._jobs = jobs
        self._requirements = requirements
        self._extract_requirements = extract_requirements
        self._acceptance_runs = acceptance_runs
        self._acceptance_run_uow_factory = acceptance_run_uow_factory
        self._reviews = reviews
        self._create_batch = create_batch
        self._provider = provider.strip().casefold() or "disabled"
        self._model = model.strip()
        self._extractor_version = extractor_version.strip()
        self._prompt_version = prompt_version.strip()
        if execution_lease_ttl_seconds <= 0:
            raise ValueError("execution_lease_ttl_seconds must be positive")
        self._execution_lease_ttl = timedelta(seconds=execution_lease_ttl_seconds)
        self._clock = clock or _utc_now

    def execute(
        self,
        *,
        payload: Mapping[str, Any],
        title: str,
        reviewer: str,
        max_new_extractions: int | None = None,
    ) -> RequirementAcceptancePreparationResult:
        selected_jobs = _validate_formal_dataset(payload)
        preflight = _preflight_from_selected(payload, selected_jobs)
        normalized_title = title.strip()
        normalized_reviewer = reviewer.strip()
        if not normalized_title:
            raise InvalidRequirementAcceptanceDatasetError("title must not be blank")
        if not normalized_reviewer:
            raise InvalidRequirementAcceptanceDatasetError("reviewer must not be blank")
        if max_new_extractions is not None and not 1 <= max_new_extractions <= FORMAL_SAMPLE_SIZE:
            raise InvalidRequirementAcceptanceDatasetError(
                f"maxNewExtractions must be between 1 and {FORMAL_SAMPLE_SIZE}"
            )
        if self._provider == "openai" and max_new_extractions is None:
            raise InvalidRequirementAcceptanceDatasetError(
                "OpenAI Requirement acceptance requires an explicit maxNewExtractions limit"
            )

        identity_key = requirement_acceptance_execution_lease_key(
            dataset_fingerprint=preflight.dataset_fingerprint,
            title=normalized_title,
            reviewer=normalized_reviewer,
            provider=self._provider,
            model=self._model,
            extractor_version=self._extractor_version,
            prompt_version=self._prompt_version,
        )
        lease_token = f"reqacceptlease_{uuid4().hex}"
        acquired_at = self._clock()
        expires_at = acquired_at + self._execution_lease_ttl
        with self._acceptance_run_uow_factory() as uow:
            acquired = uow.runs.try_acquire_execution_lease(
                identity_key=identity_key,
                lease_token=lease_token,
                acquired_at=acquired_at,
                expires_at=expires_at,
            )
            uow.commit()
        if not acquired:
            raise RequirementAcceptanceExecutionLeaseUnavailableError(
                "Another Requirement acceptance execution already owns this dataset/title/reviewer/cohort identity"
            )

        body_error: BaseException | None = None
        try:
            return self._execute_without_execution_lease(
                payload=payload,
                title=normalized_title,
                reviewer=normalized_reviewer,
                max_new_extractions=max_new_extractions,
                execution_lease_identity_key=identity_key,
                execution_lease_token=lease_token,
            )
        except BaseException as error:
            body_error = error
            raise
        finally:
            try:
                with self._acceptance_run_uow_factory() as uow:
                    released = uow.runs.release_execution_lease(
                        identity_key=identity_key,
                        lease_token=lease_token,
                    )
                    uow.commit()
                if not released:
                    raise RequirementAcceptanceExecutionLeaseLostError(
                        "Requirement acceptance execution lease ownership was lost before release"
                    )
            except Exception as release_error:
                if body_error is not None:
                    body_error.add_note(
                        "Execution lease release also failed: "
                        f"{type(release_error).__name__}: {release_error}"
                    )
                else:
                    raise

    def _execute_without_execution_lease(
        self,
        *,
        payload: Mapping[str, Any],
        title: str,
        reviewer: str,
        max_new_extractions: int | None = None,
        execution_lease_identity_key: str,
        execution_lease_token: str,
    ) -> RequirementAcceptancePreparationResult:
        selected_jobs = _validate_formal_dataset(payload)
        preflight = _preflight_from_selected(payload, selected_jobs)
        normalized_title = title.strip()
        normalized_reviewer = reviewer.strip()
        if not normalized_title:
            raise InvalidRequirementAcceptanceDatasetError("title must not be blank")
        if not normalized_reviewer:
            raise InvalidRequirementAcceptanceDatasetError("reviewer must not be blank")
        if max_new_extractions is not None and not 1 <= max_new_extractions <= FORMAL_SAMPLE_SIZE:
            raise InvalidRequirementAcceptanceDatasetError(
                f"maxNewExtractions must be between 1 and {FORMAL_SAMPLE_SIZE}"
            )
        if self._provider == "openai" and max_new_extractions is None:
            raise InvalidRequirementAcceptanceDatasetError(
                "OpenAI Requirement acceptance requires an explicit maxNewExtractions limit"
            )

        existing_run = self._acceptance_runs.get_by_identity(
            dataset_fingerprint=preflight.dataset_fingerprint,
            title=normalized_title,
            reviewer=normalized_reviewer,
            provider=self._provider,
            model=self._model,
            extractor_version=self._extractor_version,
            prompt_version=self._prompt_version,
        )
        self._enforce_canary_gate(
            existing_run=existing_run,
            max_new_extractions=max_new_extractions,
        )

        imported = self._import_jobs.execute(payload)
        if imported.skipped or imported.errors:
            raise RequirementAcceptanceImportError(
                "Formal Requirement acceptance import must not skip any selected Job"
            )
        import_detail = self._imports.get_import(imported.import_id)
        if import_detail is None:  # pragma: no cover - defensive persistence invariant
            raise RequirementAcceptanceImportError(
                f"Persisted Job import {imported.import_id!r} could not be read"
            )
        persisted_job_ids = _resolve_persisted_job_ids(import_detail.items)
        if len(persisted_job_ids) != FORMAL_SAMPLE_SIZE:
            raise RequirementAcceptanceImportError(
                f"Expected {FORMAL_SAMPLE_SIZE} persisted Jobs, found {len(persisted_job_ids)}"
            )
        if len(set(persisted_job_ids)) != FORMAL_SAMPLE_SIZE:
            raise RequirementAcceptanceImportError(
                "Formal Requirement acceptance Jobs must map to unique persisted Job IDs"
            )

        job_pairs = tuple(zip(persisted_job_ids, selected_jobs, strict=True))
        run_id = self._get_or_create_run(
            preflight=preflight,
            title=normalized_title,
            reviewer=normalized_reviewer,
            import_id=imported.import_id,
            job_pairs=job_pairs,
        )

        cases: list[RequirementAcceptanceCaseResult] = []
        successful_extractions: list[JobRequirementExtractionDetail] = []
        new_call_count = 0
        provider_unavailable = False
        for input_index, (job_id, source_job) in enumerate(job_pairs):
            title_value = _text(source_job.get("title")) or f"Job {input_index + 1}"
            company_value = _text(source_job.get("company")) or "Unknown company"
            persisted_job = self._jobs.get_job(job_id)
            if persisted_job is None:
                case = _failed_case(
                    input_index=input_index,
                    job_id=job_id,
                    title=title_value,
                    company=company_value,
                    error_code="job_not_found_after_import",
                    error_message="Imported Job could not be read",
                )
                cases.append(case)
                self._record_run_case(run_id, case, attempt_increment=0)
                continue

            input_hash = sha256(
                (persisted_job.description or "").strip().encode("utf-8")
            ).hexdigest()
            latest = self._requirements.get_latest(job_id)
            if latest is not None and self._can_reuse(latest, input_hash=input_hash):
                successful_extractions.append(latest)
                case = RequirementAcceptanceCaseResult(
                    input_index=input_index,
                    job_id=job_id,
                    title=title_value,
                    company=company_value,
                    status=RequirementAcceptanceCaseStatus.REUSED,
                    extraction_id=latest.extraction_id,
                    trace_run_id=latest.trace_run_id,
                    error_code=None,
                    error_message=None,
                )
                cases.append(case)
                self._record_run_case(run_id, case, attempt_increment=0)
                continue

            if provider_unavailable:
                case = _deferred_case(
                    input_index=input_index,
                    job_id=job_id,
                    title=title_value,
                    company=company_value,
                    error_code="provider_unavailable_not_attempted",
                    error_message=(
                        "Extraction was not attempted after the provider reported "
                        "an unavailable configuration or service"
                    ),
                )
                cases.append(case)
                self._record_run_case(run_id, case, attempt_increment=0)
                continue

            if (
                max_new_extractions is not None
                and new_call_count >= max_new_extractions
            ):
                case = _deferred_case(
                    input_index=input_index,
                    job_id=job_id,
                    title=title_value,
                    company=company_value,
                    error_code="new_extraction_limit_reached",
                    error_message=(
                        f"This invocation reached maxNewExtractions={max_new_extractions}; "
                        "rerun the same dataset/title/reviewer to resume"
                    ),
                )
                cases.append(case)
                self._record_run_case(run_id, case, attempt_increment=0)
                continue

            extraction = None
            gateway_timeout_retry_used = False
            while True:
                self._renew_execution_lease(
                    identity_key=execution_lease_identity_key,
                    lease_token=execution_lease_token,
                )
                new_call_count += 1
                try:
                    extraction = self._extract_requirements.execute(job_id)
                except RequirementExtractorUnavailableError as error:
                    failed_case = _failed_case(
                        input_index=input_index,
                        job_id=job_id,
                        title=title_value,
                        company=company_value,
                        error_code=type(error).__name__,
                        error_message=str(error),
                        trace_run_id=error.run_id,
                    )
                    self._record_run_case(run_id, failed_case, attempt_increment=1)
                    retry_budget_available = (
                        max_new_extractions is None
                        or new_call_count < max_new_extractions
                    )
                    if (
                        error.status_code == 504
                        and not gateway_timeout_retry_used
                        and retry_budget_available
                    ):
                        gateway_timeout_retry_used = True
                        continue
                    provider_unavailable = True
                    cases.append(failed_case)
                    break
                except (
                    JobNotFoundError,
                    JobDescriptionNotExtractableError,
                    RequirementExtractorFailedError,
                    InvalidRequirementExtractorOutputError,
                ) as error:  # one expected case failure must not erase prior cases
                    case = _failed_case(
                        input_index=input_index,
                        job_id=job_id,
                        title=title_value,
                        company=company_value,
                        error_code=type(error).__name__,
                        error_message=str(error),
                        trace_run_id=getattr(error, "run_id", None),
                    )
                    cases.append(case)
                    self._record_run_case(run_id, case, attempt_increment=1)
                    break
                break

            if extraction is None:
                continue

            if not self._matches_target_cohort(extraction):
                case = _failed_case(
                    input_index=input_index,
                    job_id=job_id,
                    title=title_value,
                    company=company_value,
                    error_code="extraction_cohort_mismatch",
                    error_message=(
                        "Persisted Extraction does not match the configured "
                        "provider/model/extractor/prompt cohort"
                    ),
                    extraction_id=extraction.extraction_id,
                    trace_run_id=extraction.trace_run_id,
                )
                cases.append(case)
                self._record_run_case(run_id, case, attempt_increment=1)
                continue

            successful_extractions.append(extraction)
            case = RequirementAcceptanceCaseResult(
                input_index=input_index,
                job_id=job_id,
                title=title_value,
                company=company_value,
                status=RequirementAcceptanceCaseStatus.EXTRACTED,
                extraction_id=extraction.extraction_id,
                trace_run_id=extraction.trace_run_id,
                error_code=None,
                error_message=None,
            )
            cases.append(case)
            self._record_run_case(run_id, case, attempt_increment=1)

        failed_count = sum(
            case.status is RequirementAcceptanceCaseStatus.FAILED for case in cases
        )
        deferred_count = sum(
            case.status is RequirementAcceptanceCaseStatus.DEFERRED for case in cases
        )
        batch: RequirementReviewBatchDetail | None = None
        batch_reused = False
        if (
            failed_count == 0
            and deferred_count == 0
            and len(successful_extractions) == FORMAL_SAMPLE_SIZE
        ):
            extraction_ids = tuple(
                extraction.extraction_id for extraction in successful_extractions
            )
            batch = self._find_exact_batch(
                title=normalized_title,
                reviewer=normalized_reviewer,
                extraction_ids=extraction_ids,
            )
            if batch is not None:
                batch_reused = True
            else:
                batch = self._create_batch.execute(
                    title=normalized_title,
                    reviewer=normalized_reviewer,
                    extraction_ids=extraction_ids,
                )
            with self._acceptance_run_uow_factory() as uow:
                uow.runs.attach_batch(run_id=run_id, batch_id=batch.summary.id)
                uow.commit()

        return RequirementAcceptancePreparationResult(
            run_id=run_id,
            dataset_fingerprint=preflight.dataset_fingerprint,
            import_id=imported.import_id,
            source_version=imported.source_version,
            received=imported.received,
            created_jobs=imported.created,
            updated_jobs=imported.updated,
            reused_extractions=sum(
                case.status is RequirementAcceptanceCaseStatus.REUSED for case in cases
            ),
            created_extractions=sum(
                case.status is RequirementAcceptanceCaseStatus.EXTRACTED for case in cases
            ),
            failed_extractions=failed_count,
            deferred_extractions=deferred_count,
            max_new_extractions=max_new_extractions,
            provider=self._provider,
            model=self._model,
            extractor_version=self._extractor_version,
            prompt_version=self._prompt_version,
            batch_id=batch.summary.id if batch is not None else None,
            batch_reused=batch_reused,
            cases=tuple(cases),
        )

    def _enforce_canary_gate(
        self,
        *,
        existing_run: RequirementAcceptanceRunDetail | None,
        max_new_extractions: int | None,
    ) -> None:
        if self._provider != "openai":
            return
        assert max_new_extractions is not None
        if existing_run is None:
            if max_new_extractions > 3:
                raise RequirementAcceptanceCanaryGateError(
                    "The first live invocation may attempt at most 3 Canary Extractions"
                )
            return
        if existing_run.batch_id is not None:
            return
        review = existing_run.canary_review
        if (
            review is not None
            and review.decision is RequirementAcceptanceCanaryDecision.STOP
        ):
            raise RequirementAcceptanceCanaryGateError(
                "This Requirement acceptance Run was stopped by its immutable Canary review"
            )
        if review is not None:
            return
        remaining_canary_calls = max(0, 3 - existing_run.attempted_calls)
        if max_new_extractions > remaining_canary_calls:
            raise RequirementAcceptanceCanaryGateError(
                "Canary human approval is required before the Run may exceed 3 cumulative live calls; "
                f"remainingCanaryCalls={remaining_canary_calls}"
            )

    def _get_or_create_run(
        self,
        *,
        preflight: RequirementAcceptancePreflight,
        title: str,
        reviewer: str,
        import_id: str,
        job_pairs: tuple[tuple[str, Mapping[str, Any]], ...],
    ) -> str:
        existing = self._acceptance_runs.get_by_identity(
            dataset_fingerprint=preflight.dataset_fingerprint,
            title=title,
            reviewer=reviewer,
            provider=self._provider,
            model=self._model,
            extractor_version=self._extractor_version,
            prompt_version=self._prompt_version,
        )
        if existing is not None:
            self._validate_existing_run(existing, job_pairs=job_pairs)
            with self._acceptance_run_uow_factory() as uow:
                uow.runs.update_last_import(
                    run_id=existing.id,
                    import_id=import_id,
                    dataset_generated_at=preflight.generated_at,
                )
                uow.commit()
            return existing.id

        run_id = f"reqacceptrun_{uuid4().hex}"
        case_writes: list[RequirementAcceptanceRunCaseWrite] = []
        for index, (job_id, source_job) in enumerate(job_pairs):
            persisted_job = self._jobs.get_job(job_id)
            if persisted_job is None:
                raise RequirementAcceptanceImportError(
                    f"Persisted Job {job_id!r} could not be read while freezing Run evidence"
                )
            persisted_description = (persisted_job.description or "").strip()
            case_writes.append(
                RequirementAcceptanceRunCaseWrite(
                    case_id=f"reqacceptcase_{uuid4().hex}",
                    case_index=index,
                    source_url=_text(source_job.get("url")) or "",
                    title=(
                        _text(source_job.get("title")) or f"Job {index + 1}"
                    ),
                    company=(
                        _text(source_job.get("company")) or "Unknown company"
                    ),
                    description_hash=sha256(
                        persisted_description.encode("utf-8")
                    ).hexdigest(),
                    description_snapshot=persisted_description,
                    job_id=job_id,
                )
            )
        write = RequirementAcceptanceRunWrite(
            run_id=run_id,
            dataset_fingerprint=preflight.dataset_fingerprint,
            source_version=preflight.source_version,
            dataset_generated_at=preflight.generated_at,
            title=title,
            reviewer=reviewer,
            provider=self._provider,
            model=self._model,
            extractor_version=self._extractor_version,
            prompt_version=self._prompt_version,
            first_import_id=import_id,
            last_import_id=import_id,
            cases=tuple(case_writes),
        )
        with self._acceptance_run_uow_factory() as uow:
            uow.runs.add_run(write)
            uow.commit()
        persisted = self._acceptance_runs.get_run(run_id)
        if persisted is None:  # pragma: no cover - defensive persistence invariant
            raise RuntimeError(
                f"Persisted Requirement acceptance run {run_id!r} could not be read"
            )
        return persisted.id

    def _validate_existing_run(
        self,
        run: RequirementAcceptanceRunDetail,
        *,
        job_pairs: tuple[tuple[str, Mapping[str, Any]], ...],
    ) -> None:
        if len(run.cases) != FORMAL_SAMPLE_SIZE:
            raise RequirementAcceptanceImportError(
                "Existing Requirement acceptance run does not contain 20 cases"
            )
        for index, (job_id, source_job) in enumerate(job_pairs):
            case = run.cases[index]
            expected_url = _text(source_job.get("url")) or ""
            persisted_job = self._jobs.get_job(job_id)
            if persisted_job is None:
                raise RequirementAcceptanceImportError(
                    f"Persisted Job {job_id!r} could not be read while validating Run evidence"
                )
            expected_description = (persisted_job.description or "").strip()
            expected_hash = sha256(expected_description.encode("utf-8")).hexdigest()
            if (
                case.case_index != index
                or case.source_url != expected_url
                or case.description_hash != expected_hash
                or (
                    case.description_snapshot is not None
                    and case.description_snapshot != expected_description
                )
                or case.job_id != job_id
            ):
                raise RequirementAcceptanceImportError(
                    "Existing Requirement acceptance run does not match the imported "
                    f"dataset at case {index + 1}"
                )

    def _renew_execution_lease(
        self,
        *,
        identity_key: str,
        lease_token: str,
    ) -> None:
        renewed_at = self._clock()
        with self._acceptance_run_uow_factory() as uow:
            renewed = uow.runs.renew_execution_lease(
                identity_key=identity_key,
                lease_token=lease_token,
                renewed_at=renewed_at,
                expires_at=renewed_at + self._execution_lease_ttl,
            )
            uow.commit()
        if not renewed:
            raise RequirementAcceptanceExecutionLeaseLostError(
                "Requirement acceptance execution lease expired or changed owner "
                "before Provider call"
            )

    def _record_run_case(
        self,
        run_id: str,
        case: RequirementAcceptanceCaseResult,
        *,
        attempt_increment: int,
    ) -> None:
        with self._acceptance_run_uow_factory() as uow:
            uow.runs.update_case(
                RequirementAcceptanceRunCaseUpdate(
                    run_id=run_id,
                    case_index=case.input_index,
                    status=RequirementAcceptanceRunCaseStatus(case.status.value),
                    job_id=case.job_id,
                    attempt_increment=attempt_increment,
                    extraction_id=case.extraction_id,
                    trace_run_id=case.trace_run_id,
                    error_code=case.error_code,
                    error_message=case.error_message,
                )
            )
            uow.commit()

    def _can_reuse(
        self,
        extraction: JobRequirementExtractionDetail,
        *,
        input_hash: str,
    ) -> bool:
        return extraction.input_hash == input_hash and self._matches_target_cohort(extraction)

    def _matches_target_cohort(
        self,
        extraction: JobRequirementExtractionDetail,
    ) -> bool:
        return (
            extraction.provider.strip().casefold() == self._provider
            and extraction.model == self._model
            and extraction.extractor_version == self._extractor_version
            and extraction.prompt_version == self._prompt_version
        )

    def _find_exact_batch(
        self,
        *,
        title: str,
        reviewer: str,
        extraction_ids: tuple[str, ...],
    ) -> RequirementReviewBatchDetail | None:
        offset = 0
        while True:
            page = self._reviews.list_batches(limit=_BATCH_PAGE_SIZE, offset=offset)
            for summary in page.items:
                if (
                    summary.title != title
                    or summary.reviewer != reviewer
                    or summary.provider.strip().casefold() != self._provider
                    or summary.model != self._model
                    or summary.extractor_version != self._extractor_version
                    or summary.prompt_version != self._prompt_version
                    or summary.sample_size != len(extraction_ids)
                ):
                    continue
                detail = self._reviews.get_batch(summary.id)
                if detail is not None and tuple(
                    case.extraction_id for case in detail.cases
                ) == extraction_ids:
                    return detail
            offset += len(page.items)
            if offset >= page.total or not page.items:
                return None


def preflight_requirement_acceptance_dataset(
    payload: Mapping[str, Any],
) -> RequirementAcceptancePreflight:
    """Validate one formal dataset without writing to DB or calling a provider."""

    selected_jobs = _validate_formal_dataset(payload)
    return _preflight_from_selected(payload, selected_jobs)


def _preflight_from_selected(
    payload: Mapping[str, Any],
    selected_jobs: tuple[Mapping[str, Any], ...],
) -> RequirementAcceptancePreflight:
    source_version = _text(payload.get("version")) or ""
    generated_at = _text(payload.get("generatedAt"))
    fingerprint_input = {
        "version": source_version,
        "jobs": [
            {
                "url": _text(job.get("url")) or "",
                "sourceJobId": _text(job.get("sourceJobId")),
                "title": _text(job.get("title")) or "",
                "company": _text(job.get("company")) or "",
                "sourceVersion": _text(job.get("sourceVersion")) or "",
                "descriptionHash": _text(job.get("descriptionHash")) or "",
            }
            for job in selected_jobs
        ],
    }
    dataset_fingerprint = sha256(
        json.dumps(
            fingerprint_input,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    description_lengths = [
        len((_text(job.get("description")) or "").strip()) for job in selected_jobs
    ]
    total = sum(description_lengths)
    return RequirementAcceptancePreflight(
        dataset_fingerprint=dataset_fingerprint,
        source_version=source_version,
        generated_at=generated_at,
        selected_count=len(selected_jobs),
        total_description_characters=total,
        minimum_description_characters=min(description_lengths),
        maximum_description_characters=max(description_lengths),
        average_description_characters=round(total / len(description_lengths), 2),
    )


def _validate_formal_dataset(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    version = _text(payload.get("version"))
    if not version:
        raise InvalidRequirementAcceptanceDatasetError("dataset version is required")
    if payload.get("purpose") != "requirement_manual_quality_review":
        raise InvalidRequirementAcceptanceDatasetError(
            "dataset purpose must be requirement_manual_quality_review"
        )

    quality_gate = payload.get("qualityGate")
    if not isinstance(quality_gate, Mapping):
        raise InvalidRequirementAcceptanceDatasetError("qualityGate is required")
    if quality_gate.get("status") != "ready":
        raise InvalidRequirementAcceptanceDatasetError(
            "qualityGate.status must be ready"
        )
    if quality_gate.get("requiredSampleSize") != FORMAL_SAMPLE_SIZE:
        raise InvalidRequirementAcceptanceDatasetError(
            f"qualityGate.requiredSampleSize must be {FORMAL_SAMPLE_SIZE}"
        )
    if quality_gate.get("selectedCount") != FORMAL_SAMPLE_SIZE:
        raise InvalidRequirementAcceptanceDatasetError(
            f"qualityGate.selectedCount must be {FORMAL_SAMPLE_SIZE}"
        )
    eligible_count = _non_negative_integer(
        quality_gate.get("eligibleCount"),
        field="qualityGate.eligibleCount",
    )
    distinct_count = _non_negative_integer(
        quality_gate.get("distinctEligibleCount"),
        field="qualityGate.distinctEligibleCount",
    )
    near_duplicate_count = _non_negative_integer(
        quality_gate.get("nearDuplicateCount"),
        field="qualityGate.nearDuplicateCount",
    )
    if distinct_count < FORMAL_SAMPLE_SIZE:
        raise InvalidRequirementAcceptanceDatasetError(
            f"qualityGate.distinctEligibleCount must be at least {FORMAL_SAMPLE_SIZE}"
        )
    if eligible_count - near_duplicate_count != distinct_count:
        raise InvalidRequirementAcceptanceDatasetError(
            "qualityGate eligible/distinct/nearDuplicate counts are inconsistent"
        )
    blockers = quality_gate.get("blockers")
    if not isinstance(blockers, list) or blockers:
        raise InvalidRequirementAcceptanceDatasetError(
            "qualityGate.blockers must be an empty array"
        )

    excluded_duplicates = payload.get("excludedNearDuplicates")
    if not isinstance(excluded_duplicates, list):
        raise InvalidRequirementAcceptanceDatasetError(
            "excludedNearDuplicates must be an array"
        )
    if len(excluded_duplicates) != near_duplicate_count:
        raise InvalidRequirementAcceptanceDatasetError(
            "excludedNearDuplicates length must match qualityGate.nearDuplicateCount"
        )

    selection_policy = payload.get("selectionPolicy")
    if not isinstance(selection_policy, Mapping):
        raise InvalidRequirementAcceptanceDatasetError("selectionPolicy is required")
    if selection_policy.get("descriptionSimilarity") != "nfkc_alphanumeric_5gram_jaccard":
        raise InvalidRequirementAcceptanceDatasetError(
            "selectionPolicy.descriptionSimilarity is unsupported"
        )
    threshold = selection_policy.get("nearDuplicateThreshold")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise InvalidRequirementAcceptanceDatasetError(
            "selectionPolicy.nearDuplicateThreshold must be numeric"
        )
    if not 0 < float(threshold) <= 1:
        raise InvalidRequirementAcceptanceDatasetError(
            "selectionPolicy.nearDuplicateThreshold must be in (0, 1]"
        )

    raw_jobs = payload.get("jobs")
    if not isinstance(raw_jobs, list) or len(raw_jobs) != FORMAL_SAMPLE_SIZE:
        raise InvalidRequirementAcceptanceDatasetError(
            f"dataset jobs must contain exactly {FORMAL_SAMPLE_SIZE} items"
        )
    jobs: list[Mapping[str, Any]] = []
    urls: set[str] = set()
    for index, raw_job in enumerate(raw_jobs):
        if not isinstance(raw_job, Mapping):
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}] must be an object"
            )
        url = _text(raw_job.get("url"))
        if not url:
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}].url is required"
            )
        if url in urls:
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}].url duplicates another selected Job"
            )
        urls.add(url)
        if raw_job.get("sourceVersion") != version:
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}].sourceVersion must match dataset version"
            )
        if raw_job.get("detailSucceeded") is not True:
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}].detailSucceeded must be true"
            )
        if raw_job.get("descriptionQuality") != "full_jd":
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}].descriptionQuality must be full_jd"
            )
        if raw_job.get("descriptionHasRoleEvidenceSignal") is not True:
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}] must contain role evidence"
            )
        if raw_job.get("descriptionNoiseCount") != 0:
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}].descriptionNoiseCount must be 0"
            )
        if raw_job.get("requirementReviewEligible") is not True:
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}].requirementReviewEligible must be true"
            )
        reasons = raw_job.get("requirementReviewIneligibilityReasons")
        if not isinstance(reasons, list) or reasons:
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}].requirementReviewIneligibilityReasons must be empty"
            )
        description = _text(raw_job.get("description"))
        if not description:
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}].description is required"
            )
        if raw_job.get("descriptionLength") != _utf16_length(description):
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}].descriptionLength does not match description"
            )
        if raw_job.get("descriptionHash") != _stable_text_hash(description):
            raise InvalidRequirementAcceptanceDatasetError(
                f"jobs[{index}].descriptionHash does not match description"
            )
        jobs.append(raw_job)

    for left_index, left_job in enumerate(jobs):
        left_description = _text(left_job.get("description")) or ""
        for right_index in range(left_index + 1, len(jobs)):
            right_description = _text(jobs[right_index].get("description")) or ""
            similarity = _description_similarity(left_description, right_description)
            if similarity >= float(threshold):
                raise InvalidRequirementAcceptanceDatasetError(
                    "selected Jobs contain a near-duplicate description: "
                    f"jobs[{left_index}] vs jobs[{right_index}] similarity={similarity:.4f}"
                )
    return tuple(jobs)


def _resolve_persisted_job_ids(items: Sequence[Any]) -> tuple[str, ...]:
    ordered = sorted(items, key=lambda item: item.input_index)
    resolved: list[str] = []
    for expected_index, item in enumerate(ordered):
        if item.input_index != expected_index:
            raise RequirementAcceptanceImportError(
                "Job import items do not preserve the selected dataset order"
            )
        if item.outcome not in (ImportOutcome.CREATED, ImportOutcome.UPDATED):
            raise RequirementAcceptanceImportError(
                f"Job import item {item.input_index} did not persist successfully"
            )
        if not item.job_id:
            raise RequirementAcceptanceImportError(
                f"Job import item {item.input_index} is missing jobId"
            )
        resolved.append(item.job_id)
    return tuple(resolved)


def _deferred_case(
    *,
    input_index: int,
    job_id: str,
    title: str,
    company: str,
    error_code: str,
    error_message: str,
) -> RequirementAcceptanceCaseResult:
    return RequirementAcceptanceCaseResult(
        input_index=input_index,
        job_id=job_id,
        title=title,
        company=company,
        status=RequirementAcceptanceCaseStatus.DEFERRED,
        extraction_id=None,
        trace_run_id=None,
        error_code=error_code,
        error_message=error_message[:1000],
    )


def _failed_case(
    *,
    input_index: int,
    job_id: str,
    title: str,
    company: str,
    error_code: str,
    error_message: str,
    extraction_id: str | None = None,
    trace_run_id: str | None = None,
) -> RequirementAcceptanceCaseResult:
    return RequirementAcceptanceCaseResult(
        input_index=input_index,
        job_id=job_id,
        title=title,
        company=company,
        status=RequirementAcceptanceCaseStatus.FAILED,
        extraction_id=extraction_id,
        trace_run_id=trace_run_id,
        error_code=error_code,
        error_message=error_message[:1000],
    )


def _non_negative_integer(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidRequirementAcceptanceDatasetError(
            f"{field} must be a non-negative integer"
        )
    return value


def _description_similarity(left: str, right: str) -> float:
    left_grams = _character_grams(_similarity_text(left))
    right_grams = _character_grams(_similarity_text(right))
    if not left_grams and not right_grams:
        return 1.0
    union = left_grams | right_grams
    if not union:
        return 0.0
    return len(left_grams & right_grams) / len(union)


def _similarity_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _character_grams(value: str, size: int = 5) -> set[str]:
    if len(value) < size:
        return {value} if value else set()
    return {value[index : index + size] for index in range(len(value) - size + 1)}


def _utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _stable_text_hash(value: str) -> str:
    hash_value = 0x811C9DC5
    encoded = value.encode("utf-16-le")
    for offset in range(0, len(encoded), 2):
        code_unit = encoded[offset] | (encoded[offset + 1] << 8)
        hash_value ^= code_unit
        hash_value = (hash_value * 0x01000193) & 0xFFFFFFFF
    return f"fnv1a32:{hash_value:08x}"


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
