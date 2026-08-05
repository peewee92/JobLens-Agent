"""Job Requirement workflow: provider output → deterministic gates → Trace."""
from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from time import perf_counter
from uuid import uuid4

from app.application.job_requirements import (
    InvalidRequirementExtractorOutputError,
    JobDescriptionNotExtractableError,
    JobRequirementExtractionOutput,
    JobRequirementExtractionProposal,
    RequirementExtractorFailedError,
    RequirementExtractorUnavailableError,
)
from app.application.job_requirements.validation import validate_job_requirement_output
from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
from app.application.ports.trace_unit_of_work import AbstractTraceUnitOfWork
from app.application.tracing import TraceWrite

TraceUnitOfWorkFactory = Callable[[], AbstractTraceUnitOfWork]

EXTRACTOR_VERSION = "requirement-extractor-v3"
PROMPT_VERSION = "requirement-extraction-v1"
MIN_DESCRIPTION_CHARS = 40
MAX_DESCRIPTION_CHARS = 50_000


class ExtractJobRequirementsWorkflow:
    """Produce grounded Requirement facts without reading or writing ORM models."""

    def __init__(
        self,
        extractor: AbstractJobRequirementExtractor,
        trace_uow_factory: TraceUnitOfWorkFactory,
    ) -> None:
        self._extractor = extractor
        self._trace_uow_factory = trace_uow_factory

    def execute(self, *, job_id: str, description: str) -> JobRequirementExtractionProposal:
        normalized = description.strip()
        if len(normalized) < MIN_DESCRIPTION_CHARS:
            raise JobDescriptionNotExtractableError(
                f"Job description must contain at least {MIN_DESCRIPTION_CHARS} characters"
            )
        if len(normalized) > MAX_DESCRIPTION_CHARS:
            raise JobDescriptionNotExtractableError(
                f"Job description must contain at most {MAX_DESCRIPTION_CHARS} characters"
            )

        run_id = f"run_{uuid4().hex}"
        started = perf_counter()
        model = self._extractor.model_name
        output: JobRequirementExtractionOutput | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None

        try:
            result = self._extractor.extract(normalized)
            model = result.model
            input_tokens = result.input_tokens
            output_tokens = result.output_tokens
            output = result.output
            validate_job_requirement_output(normalized, output)
        except (
            RequirementExtractorUnavailableError,
            RequirementExtractorFailedError,
            InvalidRequirementExtractorOutputError,
        ) as error:
            error.run_id = run_id
            self._record_trace(
                run_id=run_id,
                job_id=job_id,
                description=normalized,
                model=model,
                output=output,
                latency_ms=self._elapsed_ms(started),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error=str(error),
            )
            raise
        except Exception as error:
            wrapped = RequirementExtractorFailedError(
                "Requirement extractor failed before producing usable output",
                run_id=run_id,
            )
            self._record_trace(
                run_id=run_id,
                job_id=job_id,
                description=normalized,
                model=model,
                output=output,
                latency_ms=self._elapsed_ms(started),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error=f"{type(error).__name__}: unexpected extractor error",
            )
            raise wrapped from error

        assert output is not None
        self._record_trace(
            run_id=run_id,
            job_id=job_id,
            description=normalized,
            model=model,
            output=output,
            latency_ms=self._elapsed_ms(started),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=None,
        )
        return JobRequirementExtractionProposal(
            trace_run_id=run_id,
            extractor_version=EXTRACTOR_VERSION,
            model=model,
            prompt_version=PROMPT_VERSION,
            requirements=output.requirements,
        )

    def _record_trace(
        self,
        *,
        run_id: str,
        job_id: str,
        description: str,
        model: str,
        output: JobRequirementExtractionOutput | None,
        latency_ms: int,
        input_tokens: int | None,
        output_tokens: int | None,
        error: str | None,
    ) -> None:
        with self._trace_uow_factory() as uow:
            uow.traces.add(
                TraceWrite(
                    run_id=run_id,
                    capability="requirement_extraction",
                    version=EXTRACTOR_VERSION,
                    model=model,
                    prompt_version=PROMPT_VERSION,
                    input_refs={
                        "jobId": job_id,
                        "descriptionSha256": sha256(
                            description.encode("utf-8")
                        ).hexdigest(),
                        "characterCount": len(description),
                    },
                    output=(
                        _requirement_output_dict(output)
                        if output is not None
                        else None
                    ),
                    latency_ms=latency_ms,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    error=error,
                )
            )
            uow.commit()

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((perf_counter() - started) * 1000))


def _requirement_output_dict(output: JobRequirementExtractionOutput) -> dict:
    return {
        "requirements": [
            {
                "type": item.type.value,
                "originalText": item.original_text,
                "normalizedCapability": item.normalized_capability,
                "importance": item.importance.value,
                "evidenceSpan": item.evidence_span,
                "confidence": item.confidence,
            }
            for item in output.requirements
        ]
    }
