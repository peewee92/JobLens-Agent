"""Fail-closed release policy for Job Requirement facts consumed by Match."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from app.application.job_queries.errors import JobNotFoundError
from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.application.ports.job_requirement_release_repository import (
    AbstractJobRequirementReleaseQueryRepository,
)
from app.application.ports.job_requirement_repository import (
    AbstractJobRequirementQueryRepository,
)
from app.application.ports.requirement_review_repository import (
    AbstractRequirementReviewQueryRepository,
)


class JobRequirementReleaseBlockerCode(StrEnum):
    ACCEPTED_BASELINE_MISSING = "accepted_baseline_missing"
    EXTRACTION_MISSING = "requirement_extraction_missing"
    EXTRACTION_INPUT_STALE = "extraction_input_stale"
    EXTRACTION_COHORT_MISMATCH = "extraction_cohort_mismatch"
    REQUIREMENTS_EMPTY = "requirements_empty"
    REQUIREMENT_COUNT_MISMATCH = "requirement_count_mismatch"
    TRACE_MISSING = "trace_missing"
    TRACE_FAILED = "trace_failed"
    TRACE_CAPABILITY_MISMATCH = "trace_capability_mismatch"
    TRACE_COHORT_MISMATCH = "trace_cohort_mismatch"
    TRACE_INPUT_MISMATCH = "trace_input_mismatch"
    TRACE_OUTPUT_MISMATCH = "trace_output_mismatch"


@dataclass(frozen=True, slots=True)
class JobRequirementReleaseBlocker:
    code: JobRequirementReleaseBlockerCode
    message: str


@dataclass(frozen=True, slots=True)
class JobRequirementReleaseReadiness:
    job_id: str
    release_eligible: bool
    current_description_sha256: str
    extraction_id: str | None
    extraction_input_hash: str | None
    provider: str | None
    model: str | None
    extractor_version: str | None
    prompt_version: str | None
    trace_run_id: str | None
    requirement_count: int
    accepted_baseline_batch_id: str | None
    accepted_baseline_decision_id: str | None
    accepted_baseline_evidence_fingerprint: str | None
    blockers: tuple[JobRequirementReleaseBlocker, ...]


MVP_FROZEN_EXTRACTOR_VERSION = "requirement-extractor-v42.95"


class GetJobRequirementReleaseReadinessUseCase:
    """Derive whether the latest Requirement facts may be consumed by Match."""

    def __init__(
        self,
        *,
        jobs: AbstractJobQueryRepository,
        requirements: AbstractJobRequirementQueryRepository,
        reviews: AbstractRequirementReviewQueryRepository,
        traces: AbstractJobRequirementReleaseQueryRepository,
        allow_frozen_mvp_without_baseline: bool = False,
    ) -> None:
        self._jobs = jobs
        self._requirements = requirements
        self._reviews = reviews
        self._traces = traces
        self._allow_frozen_mvp_without_baseline = allow_frozen_mvp_without_baseline

    def execute(self, job_id: str) -> JobRequirementReleaseReadiness:
        job = self._jobs.get_job(job_id)
        if job is None:
            raise JobNotFoundError(f"Job {job_id!r} was not found")

        normalized_description = (job.description or "").strip()
        description_sha256 = sha256(normalized_description.encode("utf-8")).hexdigest()
        baseline = self._reviews.get_accepted_baseline()
        extraction = self._requirements.get_latest(job_id)
        blockers: list[JobRequirementReleaseBlocker] = []

        def block(code: JobRequirementReleaseBlockerCode, message: str) -> None:
            blockers.append(JobRequirementReleaseBlocker(code=code, message=message))

        if extraction is None:
            if baseline is None:
                block(
                    JobRequirementReleaseBlockerCode.ACCEPTED_BASELINE_MISSING,
                    "No current human-accepted Requirement Review baseline exists.",
                )
            block(
                JobRequirementReleaseBlockerCode.EXTRACTION_MISSING,
                "The Job has no Requirement Extraction.",
            )
            return JobRequirementReleaseReadiness(
                job_id=job_id,
                release_eligible=False,
                current_description_sha256=description_sha256,
                extraction_id=None,
                extraction_input_hash=None,
                provider=None,
                model=None,
                extractor_version=None,
                prompt_version=None,
                trace_run_id=None,
                requirement_count=0,
                accepted_baseline_batch_id=(baseline.batch.id if baseline else None),
                accepted_baseline_decision_id=(baseline.decision.id if baseline else None),
                accepted_baseline_evidence_fingerprint=(
                    baseline.decision.evidence_fingerprint if baseline else None
                ),
                blockers=tuple(blockers),
            )

        if baseline is None and not (
            self._allow_frozen_mvp_without_baseline
            and extraction.extractor_version == MVP_FROZEN_EXTRACTOR_VERSION
        ):
            block(
                JobRequirementReleaseBlockerCode.ACCEPTED_BASELINE_MISSING,
                (
                    "No current human-accepted Requirement Review baseline exists, "
                    f"and the latest Extraction is not the frozen MVP cohort {MVP_FROZEN_EXTRACTOR_VERSION}."
                    if self._allow_frozen_mvp_without_baseline
                    else "No current human-accepted Requirement Review baseline exists."
                ),
            )

        if extraction.input_hash != description_sha256:
            block(
                JobRequirementReleaseBlockerCode.EXTRACTION_INPUT_STALE,
                "The latest Extraction no longer matches the current Job description.",
            )

        if baseline is not None:
            baseline_cohort = (
                baseline.batch.provider.casefold(),
                baseline.batch.model,
                baseline.batch.extractor_version,
                baseline.batch.prompt_version,
            )
            extraction_cohort = (
                extraction.provider.casefold(),
                extraction.model,
                extraction.extractor_version,
                extraction.prompt_version,
            )
            if extraction_cohort != baseline_cohort:
                block(
                    JobRequirementReleaseBlockerCode.EXTRACTION_COHORT_MISMATCH,
                    "The Extraction cohort does not match the accepted Requirement baseline.",
                )

        actual_requirement_count = len(extraction.requirements)
        if actual_requirement_count == 0:
            block(
                JobRequirementReleaseBlockerCode.REQUIREMENTS_EMPTY,
                "The Extraction contains no Requirement facts.",
            )
        if actual_requirement_count != extraction.requirement_count:
            block(
                JobRequirementReleaseBlockerCode.REQUIREMENT_COUNT_MISMATCH,
                "The persisted Requirement count does not match the loaded facts.",
            )

        trace = self._traces.get_trace(extraction.trace_run_id)
        if trace is None:
            block(
                JobRequirementReleaseBlockerCode.TRACE_MISSING,
                "The Extraction Trace cannot be found.",
            )
        else:
            if trace.error is not None:
                block(
                    JobRequirementReleaseBlockerCode.TRACE_FAILED,
                    "The Extraction Trace contains an execution error.",
                )
            if trace.capability != "requirement_extraction":
                block(
                    JobRequirementReleaseBlockerCode.TRACE_CAPABILITY_MISMATCH,
                    "The linked Trace is not a Requirement Extraction capability run.",
                )
            if (
                trace.version != extraction.extractor_version
                or trace.model != extraction.model
                or trace.prompt_version != extraction.prompt_version
            ):
                block(
                    JobRequirementReleaseBlockerCode.TRACE_COHORT_MISMATCH,
                    "The Trace model/version cohort does not match the Extraction.",
                )
            if (
                trace.input_refs.get("jobId") != job_id
                or trace.input_refs.get("descriptionSha256") != extraction.input_hash
            ):
                block(
                    JobRequirementReleaseBlockerCode.TRACE_INPUT_MISMATCH,
                    "The Trace input references do not match the Job and Extraction input.",
                )
            output_requirements = (
                trace.output.get("requirements")
                if isinstance(trace.output, dict)
                else None
            )
            expected_output = [
                {
                    "type": item.type.value,
                    "originalText": item.original_text,
                    "normalizedCapability": item.normalized_capability,
                    "importance": item.importance.value,
                    "evidenceSpan": item.evidence_span,
                    "confidence": item.confidence,
                }
                for item in extraction.requirements
            ]
            if output_requirements != expected_output:
                block(
                    JobRequirementReleaseBlockerCode.TRACE_OUTPUT_MISMATCH,
                    "The Trace output does not exactly match the persisted Requirement facts.",
                )

        return JobRequirementReleaseReadiness(
            job_id=job_id,
            release_eligible=not blockers,
            current_description_sha256=description_sha256,
            extraction_id=extraction.extraction_id,
            extraction_input_hash=extraction.input_hash,
            provider=extraction.provider,
            model=extraction.model,
            extractor_version=extraction.extractor_version,
            prompt_version=extraction.prompt_version,
            trace_run_id=extraction.trace_run_id,
            requirement_count=extraction.requirement_count,
            accepted_baseline_batch_id=(baseline.batch.id if baseline else None),
            accepted_baseline_decision_id=(baseline.decision.id if baseline else None),
            accepted_baseline_evidence_fingerprint=(
                baseline.decision.evidence_fingerprint if baseline else None
            ),
            blockers=tuple(blockers),
        )
