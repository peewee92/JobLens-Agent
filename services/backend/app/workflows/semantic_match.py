"""Semantic Match workflow: trusted facts → provider judgment → guarded result + Trace."""
from __future__ import annotations

import json
from collections.abc import Callable
from hashlib import sha256
from time import perf_counter
from uuid import uuid4

from app.application.eligibility import JobEligibilityResult, RequirementFitStatus
from app.application.evidence_retrieval import (
    EvidenceRelevanceTier,
    JobEvidenceRetrievalResult,
)
from app.application.ports.semantic_matcher import AbstractSemanticMatcher
from app.application.ports.trace_unit_of_work import AbstractTraceUnitOfWork
from app.application.semantic_match.errors import (
    InvalidSemanticMatcherOutputError,
    SemanticMatcherFailedError,
    SemanticMatcherUnavailableError,
    SemanticMatchInputsNotReadyError,
)
from app.application.semantic_match.models import (
    JobSemanticMatchResult,
    SemanticAssessmentSource,
    SemanticCandidateInput,
    SemanticMatchOutput,
    SemanticMatchVerdict,
    SemanticRequirementAssessment,
    SemanticRequirementInput,
)
from app.application.tracing import TraceWrite

TraceUnitOfWorkFactory = Callable[[], AbstractTraceUnitOfWork]

MATCHER_VERSION = "semantic-match-v1"
PROMPT_VERSION = "semantic-match-v2"


class SemanticMatchWorkflow:
    """Let a provider assess candidate Evidence without overriding Eligibility."""

    def __init__(
        self,
        *,
        matcher: AbstractSemanticMatcher,
        trace_uow_factory: TraceUnitOfWorkFactory,
    ) -> None:
        self._matcher = matcher
        self._trace_uow_factory = trace_uow_factory

    def execute(
        self,
        *,
        eligibility: JobEligibilityResult,
        evidence: JobEvidenceRetrievalResult,
    ) -> JobSemanticMatchResult:
        self._validate_input_identity(eligibility=eligibility, evidence=evidence)
        evidence_by_requirement = {
            item.requirement_id: item for item in evidence.requirements
        }
        deterministic: dict[str, SemanticRequirementAssessment] = {}
        provider_inputs: list[SemanticRequirementInput] = []

        for item in eligibility.requirements:
            candidate_set = evidence_by_requirement[item.requirement_id]
            if item.status is RequirementFitStatus.MATCHED:
                deterministic[item.requirement_id] = SemanticRequirementAssessment(
                    requirement_id=item.requirement_id,
                    requirement_index=item.requirement_index,
                    type=item.type,
                    importance=item.importance,
                    original_text=item.original_text,
                    normalized_capability=item.normalized_capability,
                    eligibility_status=item.status,
                    verdict=SemanticMatchVerdict.MATCHED,
                    evidence_ids=item.evidence_ids,
                    profile_fact_refs=item.profile_fact_refs,
                    reason=(
                        "确定性 Eligibility 已有直接证据或已确认 Profile 事实，"
                        "无需模型再次判断。"
                    ),
                    source=SemanticAssessmentSource.DETERMINISTIC,
                )
                continue

            if not candidate_set.candidates:
                deterministic[item.requirement_id] = SemanticRequirementAssessment(
                    requirement_id=item.requirement_id,
                    requirement_index=item.requirement_index,
                    type=item.type,
                    importance=item.importance,
                    original_text=item.original_text,
                    normalized_capability=item.normalized_capability,
                    eligibility_status=item.status,
                    verdict=SemanticMatchVerdict.NOT_MATCHED,
                    evidence_ids=(),
                    profile_fact_refs=item.profile_fact_refs,
                    reason="没有检索到可供语义判断的已确认职业证据。",
                    source=SemanticAssessmentSource.DETERMINISTIC,
                )
                continue

            provider_inputs.append(
                SemanticRequirementInput(
                    requirement_id=item.requirement_id,
                    requirement_index=item.requirement_index,
                    type=item.type,
                    importance=item.importance,
                    original_text=item.original_text,
                    normalized_capability=item.normalized_capability,
                    candidates=tuple(
                        SemanticCandidateInput(
                            evidence_id=candidate.evidence_id,
                            evidence_type=candidate.evidence_type,
                            summary=candidate.summary,
                            relevance_tier=candidate.relevance_tier,
                            retrieval_basis=candidate.retrieval_basis,
                        )
                        for candidate in candidate_set.candidates
                    ),
                )
            )

        if not provider_inputs:
            return self._build_result(
                eligibility=eligibility,
                assessments=deterministic,
                model=None,
                trace_run_id=None,
                provider_calls=0,
                trace_runs_created=0,
            )

        run_id = f"run_{uuid4().hex}"
        started = perf_counter()
        model = self._matcher.model_name
        output: SemanticMatchOutput | None = None
        input_tokens: int | None = None
        output_tokens: int | None = None

        try:
            result = self._matcher.match(tuple(provider_inputs))
            model = result.model
            input_tokens = result.input_tokens
            output_tokens = result.output_tokens
            output = result.output
            self._validate_provider_output(tuple(provider_inputs), output)
        except (
            SemanticMatcherUnavailableError,
            SemanticMatcherFailedError,
            InvalidSemanticMatcherOutputError,
        ) as error:
            error.run_id = run_id
            self._record_trace(
                run_id=run_id,
                eligibility=eligibility,
                provider_inputs=tuple(provider_inputs),
                model=model,
                output=output,
                latency_ms=self._elapsed_ms(started),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error=str(error),
            )
            raise
        except Exception as error:
            wrapped = SemanticMatcherFailedError(
                "Semantic matcher failed before producing usable output",
                run_id=run_id,
            )
            self._record_trace(
                run_id=run_id,
                eligibility=eligibility,
                provider_inputs=tuple(provider_inputs),
                model=model,
                output=output,
                latency_ms=self._elapsed_ms(started),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error=f"{type(error).__name__}: unexpected semantic matcher error",
            )
            raise wrapped from error

        assert output is not None
        provider_by_requirement = {item.requirement_id: item for item in output.assessments}
        eligibility_by_requirement = {
            item.requirement_id: item for item in eligibility.requirements
        }
        for requirement_input in provider_inputs:
            provider_item = provider_by_requirement[requirement_input.requirement_id]
            eligibility_item = eligibility_by_requirement[requirement_input.requirement_id]
            deterministic[requirement_input.requirement_id] = SemanticRequirementAssessment(
                requirement_id=eligibility_item.requirement_id,
                requirement_index=eligibility_item.requirement_index,
                type=eligibility_item.type,
                importance=eligibility_item.importance,
                original_text=eligibility_item.original_text,
                normalized_capability=eligibility_item.normalized_capability,
                eligibility_status=eligibility_item.status,
                verdict=provider_item.verdict,
                evidence_ids=provider_item.evidence_ids,
                profile_fact_refs=eligibility_item.profile_fact_refs,
                reason=provider_item.reason.strip(),
                source=SemanticAssessmentSource.PROVIDER,
            )

        self._record_trace(
            run_id=run_id,
            eligibility=eligibility,
            provider_inputs=tuple(provider_inputs),
            model=model,
            output=output,
            latency_ms=self._elapsed_ms(started),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=None,
        )
        return self._build_result(
            eligibility=eligibility,
            assessments=deterministic,
            model=model,
            trace_run_id=run_id,
            provider_calls=1,
            trace_runs_created=1,
        )

    @staticmethod
    def _validate_input_identity(
        *,
        eligibility: JobEligibilityResult,
        evidence: JobEvidenceRetrievalResult,
    ) -> None:
        if (
            eligibility.job_id != evidence.job_id
            or eligibility.profile_id != evidence.profile_id
            or eligibility.profile_version != evidence.profile_version
            or eligibility.extraction_id != evidence.extraction_id
        ):
            raise SemanticMatchInputsNotReadyError(
                "Semantic Match inputs do not share the same frozen Profile and Requirement identities."
            )
        eligibility_ids = [item.requirement_id for item in eligibility.requirements]
        evidence_ids = [item.requirement_id for item in evidence.requirements]
        if eligibility_ids != evidence_ids:
            raise SemanticMatchInputsNotReadyError(
                "Semantic Match Eligibility and Evidence Retrieval requirement sets differ."
            )

    @staticmethod
    def _validate_provider_output(
        requirements: tuple[SemanticRequirementInput, ...],
        output: SemanticMatchOutput,
    ) -> None:
        expected_ids = [item.requirement_id for item in requirements]
        actual_ids = [item.requirement_id for item in output.assessments]
        if len(actual_ids) != len(set(actual_ids)):
            raise InvalidSemanticMatcherOutputError(
                "Semantic Match output contains duplicate requirementId values."
            )
        if actual_ids != expected_ids:
            raise InvalidSemanticMatcherOutputError(
                "Semantic Match output must contain each requested requirement exactly once and in order."
            )

        inputs_by_id = {item.requirement_id: item for item in requirements}
        for assessment in output.assessments:
            if not assessment.reason.strip():
                raise InvalidSemanticMatcherOutputError(
                    f"Semantic Match {assessment.requirement_id} must include a reason."
                )
            if len(assessment.evidence_ids) != len(set(assessment.evidence_ids)):
                raise InvalidSemanticMatcherOutputError(
                    f"Semantic Match {assessment.requirement_id} contains duplicate evidenceIds."
                )
            requirement = inputs_by_id[assessment.requirement_id]
            candidates = {item.evidence_id: item for item in requirement.candidates}
            unknown = [item for item in assessment.evidence_ids if item not in candidates]
            if unknown:
                raise InvalidSemanticMatcherOutputError(
                    f"Semantic Match {assessment.requirement_id} cites Evidence outside retrieved candidates."
                )
            if assessment.verdict is SemanticMatchVerdict.NOT_MATCHED:
                if assessment.evidence_ids:
                    raise InvalidSemanticMatcherOutputError(
                        f"Semantic Match {assessment.requirement_id} not_matched must not cite supporting Evidence."
                    )
                continue
            if not assessment.evidence_ids:
                raise InvalidSemanticMatcherOutputError(
                    f"Semantic Match {assessment.requirement_id} {assessment.verdict.value} requires Evidence."
                )
            if assessment.verdict is SemanticMatchVerdict.MATCHED and not any(
                candidates[evidence_id].relevance_tier is EvidenceRelevanceTier.DIRECT
                for evidence_id in assessment.evidence_ids
            ):
                raise InvalidSemanticMatcherOutputError(
                    f"Semantic Match {assessment.requirement_id} related-only Evidence cannot be promoted to matched."
                )

    def _build_result(
        self,
        *,
        eligibility: JobEligibilityResult,
        assessments: dict[str, SemanticRequirementAssessment],
        model: str | None,
        trace_run_id: str | None,
        provider_calls: int,
        trace_runs_created: int,
    ) -> JobSemanticMatchResult:
        ordered = tuple(assessments[item.requirement_id] for item in eligibility.requirements)
        return JobSemanticMatchResult(
            job_id=eligibility.job_id,
            profile_id=eligibility.profile_id,
            profile_version=eligibility.profile_version,
            extraction_id=eligibility.extraction_id,
            eligibility=eligibility.eligibility,
            assessments=ordered,
            matched_count=sum(item.verdict is SemanticMatchVerdict.MATCHED for item in ordered),
            partial_count=sum(item.verdict is SemanticMatchVerdict.PARTIAL for item in ordered),
            not_matched_count=sum(
                item.verdict is SemanticMatchVerdict.NOT_MATCHED for item in ordered
            ),
            matcher_version=MATCHER_VERSION,
            prompt_version=PROMPT_VERSION,
            model=model,
            trace_run_id=trace_run_id,
            provider_calls=provider_calls,
            trace_runs_created=trace_runs_created,
        )

    def _record_trace(
        self,
        *,
        run_id: str,
        eligibility: JobEligibilityResult,
        provider_inputs: tuple[SemanticRequirementInput, ...],
        model: str,
        output: SemanticMatchOutput | None,
        latency_ms: int,
        input_tokens: int | None,
        output_tokens: int | None,
        error: str | None,
    ) -> None:
        serialized_input = _provider_input_dict(provider_inputs)
        with self._trace_uow_factory() as uow:
            uow.traces.add(
                TraceWrite(
                    run_id=run_id,
                    capability="semantic_match",
                    version=MATCHER_VERSION,
                    model=model,
                    prompt_version=PROMPT_VERSION,
                    input_refs={
                        "jobId": eligibility.job_id,
                        "profileId": eligibility.profile_id,
                        "profileVersion": eligibility.profile_version,
                        "extractionId": eligibility.extraction_id,
                        "requirementIds": [item.requirement_id for item in provider_inputs],
                        "candidateEvidenceIds": [
                            candidate.evidence_id
                            for item in provider_inputs
                            for candidate in item.candidates
                        ],
                        "inputSha256": sha256(
                            json.dumps(
                                serialized_input,
                                ensure_ascii=False,
                                sort_keys=True,
                            ).encode("utf-8")
                        ).hexdigest(),
                    },
                    output=_semantic_output_dict(output) if output is not None else None,
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


def _provider_input_dict(
    requirements: tuple[SemanticRequirementInput, ...],
) -> dict[str, object]:
    return {
        "requirements": [
            {
                "requirementId": item.requirement_id,
                "type": item.type.value,
                "importance": item.importance.value,
                "originalText": item.original_text,
                "normalizedCapability": item.normalized_capability,
                "candidates": [
                    {
                        "evidenceId": candidate.evidence_id,
                        "evidenceType": candidate.evidence_type.value,
                        "summary": candidate.summary,
                        "relevanceTier": candidate.relevance_tier.value,
                        "retrievalBasis": candidate.retrieval_basis.value,
                    }
                    for candidate in item.candidates
                ],
            }
            for item in requirements
        ]
    }


def _semantic_output_dict(output: SemanticMatchOutput) -> dict[str, object]:
    return {
        "assessments": [
            {
                "requirementId": item.requirement_id,
                "verdict": item.verdict.value,
                "evidenceIds": list(item.evidence_ids),
                "reason": item.reason,
            }
            for item in output.assessments
        ]
    }
