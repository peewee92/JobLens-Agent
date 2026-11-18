"""Profile Extraction workflow: provider output → deterministic gates → Trace."""
from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from time import perf_counter
from uuid import uuid4

from app.application.ports.profile_extractor import AbstractProfileExtractor
from app.application.ports.trace_unit_of_work import AbstractTraceUnitOfWork
from app.application.profile_extraction import (
    InvalidProfileExtractorOutputError,
    InvalidResumeTextError,
    ProfileExtractionOutput,
    ProfileExtractionProposal,
    ProfileExtractorFailedError,
    ProfileExtractorUnavailableError,
)
from app.application.profile_extraction.validation import (
    recover_partial_profile_output,
    validate_profile_extraction_output,
)
from app.application.tracing import TraceWrite

TraceUnitOfWorkFactory = Callable[[], AbstractTraceUnitOfWork]

EXTRACTOR_VERSION = "profile-extractor-v2"
LOCAL_PARTIAL_EXTRACTOR_VERSION = "profile-extractor-v3-local-partial"
PROMPT_VERSION = "profile-proposal-v1"
MIN_RESUME_CHARS = 50
MAX_RESUME_CHARS = 30_000


class ProposeProfileFromResumeWorkflow:
    """Create a reviewable proposal without mutating confirmed Profile data."""

    def __init__(
        self,
        extractor: AbstractProfileExtractor,
        trace_uow_factory: TraceUnitOfWorkFactory,
        *,
        allow_partial: bool = False,
    ) -> None:
        self._extractor = extractor
        self._trace_uow_factory = trace_uow_factory
        self._allow_partial = allow_partial
        self._extractor_version = LOCAL_PARTIAL_EXTRACTOR_VERSION if allow_partial else EXTRACTOR_VERSION

    def execute(self, resume_text: str) -> ProfileExtractionProposal:
        normalized_text = resume_text.strip()
        if len(normalized_text) < MIN_RESUME_CHARS:
            raise InvalidResumeTextError(
                f"resumeText must contain at least {MIN_RESUME_CHARS} characters"
            )
        if len(normalized_text) > MAX_RESUME_CHARS:
            raise InvalidResumeTextError(
                f"resumeText must contain at most {MAX_RESUME_CHARS} characters"
            )

        run_id = f"run_{uuid4().hex}"
        started = perf_counter()
        model = self._extractor.model_name
        output: ProfileExtractionOutput | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None
        omitted_evidence_count = omitted_skill_count = 0

        try:
            result = self._extractor.extract(normalized_text)
            model = result.model
            input_tokens = result.input_tokens
            output_tokens = result.output_tokens
            output = result.output
            if self._allow_partial:
                output, omitted_evidence_count, omitted_skill_count = recover_partial_profile_output(normalized_text, output)
            else:
                output = validate_profile_extraction_output(normalized_text, output)
        except (
            ProfileExtractorUnavailableError,
            ProfileExtractorFailedError,
            InvalidProfileExtractorOutputError,
        ) as error:
            error.run_id = run_id
            self._record_trace(
                run_id=run_id,
                resume_text=normalized_text,
                model=model,
                output=output,
                latency_ms=self._elapsed_ms(started),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error=str(error),
            )
            raise
        except Exception as error:
            wrapped = ProfileExtractorFailedError(
                "Profile extractor failed before producing a usable proposal",
                run_id=run_id,
            )
            self._record_trace(
                run_id=run_id,
                resume_text=normalized_text,
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
            resume_text=normalized_text,
            model=model,
            output=output,
            latency_ms=self._elapsed_ms(started),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=None,
            omitted_evidence_count=omitted_evidence_count,
            omitted_skill_count=omitted_skill_count,
        )
        return ProfileExtractionProposal(
            run_id=run_id,
            extractor_version=self._extractor_version,
            model=model,
            prompt_version=PROMPT_VERSION,
            headline=output.headline,
            years_of_experience=output.years_of_experience,
            evidence=output.evidence,
            skills=output.skills,
            warnings=output.warnings,
            omitted_evidence_count=omitted_evidence_count,
            omitted_skill_count=omitted_skill_count,
        )

    def _record_trace(
        self,
        *,
        run_id: str,
        resume_text: str,
        model: str,
        output: ProfileExtractionOutput | None,
        latency_ms: int,
        input_tokens: int | None,
        output_tokens: int | None,
        error: str | None,
        omitted_evidence_count: int = 0,
        omitted_skill_count: int = 0,
    ) -> None:
        with self._trace_uow_factory() as uow:
            uow.traces.add(
                TraceWrite(
                    run_id=run_id,
                    capability="profile_extraction",
                    version=self._extractor_version,
                    model=model,
                    prompt_version=PROMPT_VERSION,
                    input_refs={
                        "resumeSha256": sha256(
                            resume_text.encode("utf-8")
                        ).hexdigest(),
                        "characterCount": len(resume_text),
                    },
                    output=(
                        _profile_output_dict(output, omitted_evidence_count, omitted_skill_count) if output is not None else None
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


def _profile_output_dict(output: ProfileExtractionOutput, omitted_evidence_count: int = 0, omitted_skill_count: int = 0) -> dict:
    return {
        "headline": output.headline,
        "yearsOfExperience": output.years_of_experience,
        "evidence": [
            {
                "key": item.key,
                "type": item.type.value,
                "summary": item.summary,
                "source": item.source,
                "evidenceSpan": item.evidence_span,
            }
            for item in output.evidence
        ],
        "skills": [
            {
                "name": item.name,
                "level": item.level.value,
                "evidenceKeys": list(item.evidence_keys),
            }
            for item in output.skills
        ],
        "warnings": list(output.warnings),
        **({"sourceRecovery": {"omittedEvidenceCount": omitted_evidence_count, "omittedSkillCount": omitted_skill_count}}
           if omitted_evidence_count else {}),
    }
