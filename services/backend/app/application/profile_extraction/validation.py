"""Deterministic gates for Profile Extraction proposals."""
from __future__ import annotations

from app.application.profile_extraction.errors import (
    InvalidProfileExtractorOutputError,
)
from app.application.profile_extraction.models import ProfileExtractionOutput


def validate_profile_extraction_output(
    resume_text: str,
    output: ProfileExtractionOutput,
) -> ProfileExtractionOutput:
    """Reject structurally valid but unsupported or internally inconsistent facts."""

    if not output.headline.strip():
        raise InvalidProfileExtractorOutputError("headline must not be empty")
    if output.years_of_experience is not None and output.years_of_experience < 0:
        raise InvalidProfileExtractorOutputError(
            "yearsOfExperience must be non-negative"
        )
    if not output.evidence:
        raise InvalidProfileExtractorOutputError(
            "at least one Evidence item is required"
        )
    if not output.skills:
        raise InvalidProfileExtractorOutputError("at least one Skill is required")

    evidence_keys: set[str] = set()
    for evidence in output.evidence:
        key = evidence.key.strip()
        if not key:
            raise InvalidProfileExtractorOutputError("Evidence key must not be empty")
        if key in evidence_keys:
            raise InvalidProfileExtractorOutputError(
                f"duplicate Evidence key: {key}"
            )
        evidence_keys.add(key)
        if not evidence.summary.strip():
            raise InvalidProfileExtractorOutputError(
                f"Evidence {key} summary must not be empty"
            )
        if not evidence.source.strip():
            raise InvalidProfileExtractorOutputError(
                f"Evidence {key} source must not be empty"
            )
        span = evidence.evidence_span
        if not span.strip():
            raise InvalidProfileExtractorOutputError(
                f"Evidence {key} evidenceSpan must not be empty"
            )
        if span not in resume_text:
            raise InvalidProfileExtractorOutputError(
                f"Evidence {key} evidenceSpan does not occur in resume text"
            )

    skill_names: set[str] = set()
    for skill in output.skills:
        normalized_name = skill.name.strip().casefold()
        if not normalized_name:
            raise InvalidProfileExtractorOutputError("Skill name must not be empty")
        if normalized_name in skill_names:
            raise InvalidProfileExtractorOutputError(
                f"duplicate Skill name: {skill.name.strip()}"
            )
        skill_names.add(normalized_name)
        if not skill.evidence_keys:
            raise InvalidProfileExtractorOutputError(
                f"Skill {skill.name.strip()} must reference Evidence"
            )
        unknown = [key for key in skill.evidence_keys if key not in evidence_keys]
        if unknown:
            raise InvalidProfileExtractorOutputError(
                f"Skill {skill.name.strip()} references unknown Evidence: {unknown[0]}"
            )

    return output
