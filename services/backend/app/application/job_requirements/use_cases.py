"""Application use cases for extracting and reading Job Requirements."""
from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from uuid import uuid4

from app.application.job_queries.errors import JobNotFoundError
from app.application.job_requirements import (
    JobDescriptionNotExtractableError,
    JobRequirementExtractionDetail,
    JobRequirementExtractionNotFoundError,
    JobRequirementExtractionWrite,
    JobRequirementWrite,
)
from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.application.ports.job_requirement_repository import (
    AbstractJobRequirementQueryRepository,
)
from app.application.ports.job_requirement_unit_of_work import (
    AbstractJobRequirementUnitOfWork,
)
from app.workflows.job_requirement_extraction import ExtractJobRequirementsWorkflow

JobRequirementUnitOfWorkFactory = Callable[[], AbstractJobRequirementUnitOfWork]


class ExtractJobRequirementsUseCase:
    def __init__(
        self,
        *,
        jobs: AbstractJobQueryRepository,
        workflow: ExtractJobRequirementsWorkflow,
        uow_factory: JobRequirementUnitOfWorkFactory,
        query_repository: AbstractJobRequirementQueryRepository,
        provider: str,
    ) -> None:
        self._jobs = jobs
        self._workflow = workflow
        self._uow_factory = uow_factory
        self._query_repository = query_repository
        self._provider = provider.strip().casefold() or "disabled"

    def execute(self, job_id: str) -> JobRequirementExtractionDetail:
        job = self._jobs.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id!r} was not found")
        if (
            job.source_version == "1.4.0"
            and job.requirement_review_eligible is not True
        ):
            reasons = ", ".join(job.requirement_review_ineligibility_reasons) or (
                "missing_requirement_review_eligibility"
            )
            raise JobDescriptionNotExtractableError(
                "Collector v1.4.0 job is not eligible for Requirement Extraction: "
                f"descriptionQuality={job.description_quality or 'unknown'}; "
                f"reasons={reasons}"
            )
        description = job.description or ""
        proposal = self._workflow.execute(job_id=job_id, description=description)
        normalized_description = description.strip()
        extraction_id = f"reqrun_{uuid4().hex}"
        write = JobRequirementExtractionWrite(
            extraction_id=extraction_id,
            job_id=job_id,
            input_hash=sha256(normalized_description.encode("utf-8")).hexdigest(),
            description_characters=len(normalized_description),
            extractor_version=proposal.extractor_version,
            provider=self._provider,
            model=proposal.model,
            prompt_version=proposal.prompt_version,
            trace_run_id=proposal.trace_run_id,
            requirements=tuple(
                JobRequirementWrite(
                    requirement_id=f"req_{uuid4().hex}",
                    job_id=job_id,
                    requirement_index=index,
                    type=item.type,
                    original_text=item.original_text.strip(),
                    normalized_capability=(
                        item.normalized_capability.strip()
                        if item.normalized_capability is not None
                        else None
                    ),
                    importance=item.importance,
                    evidence_span=item.evidence_span.strip(),
                    confidence=item.confidence,
                    extractor_version=proposal.extractor_version,
                )
                for index, item in enumerate(proposal.requirements)
            ),
        )
        with self._uow_factory() as uow:
            uow.requirements.add(write)
            uow.commit()
        result = self._query_repository.get_extraction(
            job_id=job_id,
            extraction_id=extraction_id,
        )
        if result is None:
            raise RuntimeError("Persisted Job Requirement Extraction could not be read")
        return result


class GetLatestJobRequirementsUseCase:
    def __init__(
        self,
        *,
        jobs: AbstractJobQueryRepository,
        repository: AbstractJobRequirementQueryRepository,
    ) -> None:
        self._jobs = jobs
        self._repository = repository

    def execute(self, job_id: str) -> JobRequirementExtractionDetail:
        if self._jobs.get_job(job_id) is None:
            raise JobNotFoundError(f"Job {job_id!r} was not found")
        result = self._repository.get_latest(job_id)
        if result is None:
            raise JobRequirementExtractionNotFoundError(
                f"Job {job_id!r} has no Requirement Extraction"
            )
        return result


class GetJobRequirementExtractionUseCase:
    def __init__(
        self,
        *,
        jobs: AbstractJobQueryRepository,
        repository: AbstractJobRequirementQueryRepository,
    ) -> None:
        self._jobs = jobs
        self._repository = repository

    def execute(
        self,
        *,
        job_id: str,
        extraction_id: str,
    ) -> JobRequirementExtractionDetail:
        if self._jobs.get_job(job_id) is None:
            raise JobNotFoundError(f"Job {job_id!r} was not found")
        result = self._repository.get_extraction(
            job_id=job_id,
            extraction_id=extraction_id,
        )
        if result is None:
            raise JobRequirementExtractionNotFoundError(
                f"Requirement Extraction {extraction_id!r} was not found for Job {job_id!r}"
            )
        return result
