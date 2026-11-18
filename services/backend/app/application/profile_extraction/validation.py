"""Deterministic gates for Profile Extraction proposals."""
from __future__ import annotations
from dataclasses import replace

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
    """Reject unsupported or internally inconsistent facts."""
    validated, _, _ = _validate_profile_output(resume_text, output, allow_partial=False)
    return validated


def recover_partial_profile_output(
    resume_text: str, output: ProfileExtractionOutput,
) -> tuple[ProfileExtractionOutput, int, int]:
    """For local interactive review only: retain grounded items after span mismatch."""
    return _validate_profile_output(resume_text, output, allow_partial=True)


def _validate_profile_output(
    resume_text: str, output: ProfileExtractionOutput, *, allow_partial: bool,
) -> tuple[ProfileExtractionOutput, int, int]:
    if not output.headline.strip():
        raise InvalidProfileExtractorOutputError("headline must not be empty")
    if output.years_of_experience is not None and output.years_of_experience < 0:
        raise InvalidProfileExtractorOutputError("yearsOfExperience must be non-negative")
    if not output.evidence:
        raise InvalidProfileExtractorOutputError("at least one Evidence item is required")
    if not output.skills:
        raise InvalidProfileExtractorOutputError("at least one Skill is required")

    evidence_keys: set[str] = set()
    dropped: set[str] = set()
    aligned_evidence: list[ProposedEvidence] = []
    for evidence in output.evidence:
        key = evidence.key.strip()
        if not key:
            raise InvalidProfileExtractorOutputError("Evidence key must not be empty")
        if key in evidence_keys:
            raise InvalidProfileExtractorOutputError(f"duplicate Evidence key: {key}")
        evidence_keys.add(key)
        if not evidence.summary.strip():
            raise InvalidProfileExtractorOutputError(f"Evidence {key} summary must not be empty")
        if not evidence.source.strip():
            raise InvalidProfileExtractorOutputError(f"Evidence {key} source must not be empty")
        span = evidence.evidence_span
        if not span.strip():
            raise InvalidProfileExtractorOutputError(f"Evidence {key} evidenceSpan must not be empty")
        aligned_span = _align_exact_source_span(resume_text, span)
        if aligned_span is None:
            if allow_partial:
                dropped.add(key)
                continue
            raise InvalidProfileExtractorOutputError(f"Evidence {key} evidenceSpan does not occur in resume text")
        aligned_evidence.append(replace(evidence, evidence_span=aligned_span))

    skill_names: set[str] = set()
    kept_skills = []
    for skill in output.skills:
        normalized_name = skill.name.strip().casefold()
        if not normalized_name:
            raise InvalidProfileExtractorOutputError("Skill name must not be empty")
        if normalized_name in skill_names:
            raise InvalidProfileExtractorOutputError(f"duplicate Skill name: {skill.name.strip()}")
        skill_names.add(normalized_name)
        if not skill.evidence_keys:
            raise InvalidProfileExtractorOutputError(f"Skill {skill.name.strip()} must reference Evidence")
        unknown = [key for key in skill.evidence_keys if key not in evidence_keys]
        if unknown:
            raise InvalidProfileExtractorOutputError(
                f"Skill {skill.name.strip()} references unknown Evidence: {unknown[0]}"
            )
        if dropped.isdisjoint(skill.evidence_keys):
            kept_skills.append(skill)

    if not aligned_evidence:
        raise InvalidProfileExtractorOutputError("no evidenceSpan was grounded in resume text")
    if dropped:
        # In a partial draft show exact excerpts, not summaries that may blend facts
        # from discarded claims. The user still confirms the profile separately.
        aligned_evidence = [replace(item, summary=item.evidence_span) for item in aligned_evidence]
    return (
        replace(output, evidence=tuple(aligned_evidence), skills=tuple(kept_skills)),
        len(dropped), len(output.skills) - len(kept_skills),
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
