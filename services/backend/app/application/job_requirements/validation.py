"""Deterministic grounding and business validation for Requirement output."""
from __future__ import annotations

from dataclasses import replace

from app.application.job_requirements.errors import (
    InvalidRequirementExtractorOutputError,
)
from app.application.job_requirements.models import JobRequirementExtractionOutput
from app.domain.job_requirements import RequirementType

MAX_REQUIREMENTS_PER_RUN = 50


def repair_job_requirement_grounding(
    description: str,
    output: JobRequirementExtractionOutput,
) -> JobRequirementExtractionOutput:
    """Repair one invalid quote only from the other already-grounded verbatim quote."""
    repaired = []
    for item in output.requirements:
        original_text = item.original_text.strip()
        evidence_span = item.evidence_span.strip()
        original_grounded = bool(original_text) and original_text in description
        evidence_grounded = bool(evidence_span) and evidence_span in description
        if not original_grounded and evidence_grounded:
            repaired.append(replace(item, original_text=evidence_span))
            continue
        if original_grounded and not evidence_grounded:
            repaired.append(replace(item, evidence_span=original_text))
            continue
        repaired.append(item)
    return JobRequirementExtractionOutput(requirements=tuple(repaired))


def validate_job_requirement_output(
    description: str,
    output: JobRequirementExtractionOutput,
) -> None:
    if not output.requirements:
        raise InvalidRequirementExtractorOutputError(
            "Requirement extractor must return at least one requirement"
        )
    if len(output.requirements) > MAX_REQUIREMENTS_PER_RUN:
        raise InvalidRequirementExtractorOutputError(
            f"Requirement extractor returned more than {MAX_REQUIREMENTS_PER_RUN} requirements"
        )

    seen: set[tuple[str, str, str]] = set()
    for index, item in enumerate(output.requirements):
        original_text = item.original_text.strip()
        evidence_span = item.evidence_span.strip()
        capability = (
            item.normalized_capability.strip()
            if item.normalized_capability is not None
            else None
        )
        if not original_text:
            raise InvalidRequirementExtractorOutputError(
                f"Requirement {index} originalText must not be blank"
            )
        if not evidence_span:
            raise InvalidRequirementExtractorOutputError(
                f"Requirement {index} evidenceSpan must not be blank"
            )
        if original_text not in description:
            raise InvalidRequirementExtractorOutputError(
                f"Requirement {index} originalText does not occur in Job description"
            )
        if evidence_span not in description:
            raise InvalidRequirementExtractorOutputError(
                f"Requirement {index} evidenceSpan does not occur in Job description"
            )
        if not 0 <= item.confidence <= 1:
            raise InvalidRequirementExtractorOutputError(
                f"Requirement {index} confidence must be between 0 and 1"
            )
        if item.type is RequirementType.SKILL and not capability:
            raise InvalidRequirementExtractorOutputError(
                f"Skill Requirement {index} must include normalizedCapability"
            )
        identity = (
            item.type.value,
            (capability or "").casefold(),
            evidence_span.casefold(),
        )
        if identity in seen:
            raise InvalidRequirementExtractorOutputError(
                f"Requirement {index} duplicates an earlier requirement"
            )
        seen.add(identity)
