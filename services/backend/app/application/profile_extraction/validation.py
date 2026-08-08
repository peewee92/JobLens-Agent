"""Deterministic gates for Profile Extraction proposals."""
from __future__ import annotations

from app.application.profile_extraction.errors import (
    InvalidProfileExtractorOutputError,
)
from app.application.profile_extraction.models import (
    ProfileExtractionOutput,
    ProposedEvidence,
)

_INLINE_MARKDOWN_FORMATTING = frozenset({"*", "`"})
_MIN_FORMAT_ALIGNMENT_CHARS = 8


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
    aligned_evidence: list[ProposedEvidence] = []
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
        aligned_span = _align_exact_source_span(resume_text, span)
        if aligned_span is None:
            raise InvalidProfileExtractorOutputError(
                f"Evidence {key} evidenceSpan does not occur in resume text"
            )
        aligned_evidence.append(
            ProposedEvidence(
                key=evidence.key,
                type=evidence.type,
                summary=evidence.summary,
                source=evidence.source,
                evidence_span=aligned_span,
            )
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

    if all(
        aligned.evidence_span == original.evidence_span
        for aligned, original in zip(aligned_evidence, output.evidence, strict=True)
    ):
        return output
    return ProfileExtractionOutput(
        headline=output.headline,
        years_of_experience=output.years_of_experience,
        evidence=tuple(aligned_evidence),
        skills=output.skills,
        warnings=output.warnings,
    )


def _align_exact_source_span(resume_text: str, model_span: str) -> str | None:
    """Recover an exact source substring only for unique presentation-only differences.

    The model is still not allowed to paraphrase evidence. This helper ignores only
    whitespace and inline Markdown emphasis/code markers, then requires exactly one
    matching location in the source before returning the original contiguous slice.
    """

    if model_span in resume_text:
        return model_span

    target, _ = _format_projection(model_span)
    if len(target) < _MIN_FORMAT_ALIGNMENT_CHARS:
        return None
    source, source_indexes = _format_projection(resume_text)
    if not target or len(target) > len(source):
        return None

    positions: list[int] = []
    start = 0
    while True:
        position = source.find(target, start)
        if position < 0:
            break
        positions.append(position)
        if len(positions) > 1:
            return None
        start = position + 1
    if len(positions) != 1:
        return None

    position = positions[0]
    source_start = source_indexes[position]
    source_end = source_indexes[position + len(target) - 1] + 1
    while (
        source_start > 0
        and resume_text[source_start - 1] in _INLINE_MARKDOWN_FORMATTING
    ):
        source_start -= 1
    while (
        source_end < len(resume_text)
        and resume_text[source_end] in _INLINE_MARKDOWN_FORMATTING
    ):
        source_end += 1

    candidate = resume_text[source_start:source_end]
    candidate_projection, _ = _format_projection(candidate)
    return candidate if candidate_projection == target else None


def _format_projection(value: str) -> tuple[str, tuple[int, ...]]:
    projected: list[str] = []
    indexes: list[int] = []
    for index, character in enumerate(value):
        if character.isspace() or character in _INLINE_MARKDOWN_FORMATTING:
            continue
        projected.append(character)
        indexes.append(index)
    return "".join(projected), tuple(indexes)
