"""Deterministic grounding and business validation for Requirement output."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from app.application.job_requirements.errors import (
    InvalidRequirementExtractorOutputError,
)
from app.application.job_requirements.models import JobRequirementExtractionOutput
from app.domain.job_requirements import RequirementType

MAX_REQUIREMENTS_PER_RUN = 50
GROUNDING_POLICY_VERSION = "grounding-v1"


class GroundingRepairStrategy(StrEnum):
    VERBATIM_COUNTERPART = "verbatim_counterpart"
    WHITESPACE = "whitespace"
    PUNCTUATION_WIDTH = "punctuation_width"
    WHITESPACE_AND_PUNCTUATION_WIDTH = "whitespace_and_punctuation_width"


@dataclass(frozen=True, slots=True)
class GroundingRepairEvent:
    requirement_index: int
    field: str
    strategy: GroundingRepairStrategy


@dataclass(frozen=True, slots=True)
class JobRequirementGroundingRepairResult:
    output: JobRequirementExtractionOutput
    repairs: tuple[GroundingRepairEvent, ...]


@dataclass(frozen=True, slots=True)
class _RecoveredRawSlice:
    value: str
    strategy: GroundingRepairStrategy


def _normalize_width_punctuation(char: str) -> str:
    codepoint = ord(char)
    if 0xFF01 <= codepoint <= 0xFF5E:
        ascii_char = chr(codepoint - 0xFEE0)
        if ascii_char in "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~":
            return ascii_char
    return char


def _remove_whitespace(value: str) -> str:
    return "".join(char for char in value if not char.isspace())


def _normalize_punctuation_width(value: str) -> str:
    return "".join(_normalize_width_punctuation(char) for char in value)


def _normalize_grounding_text(value: str) -> str:
    return _normalize_punctuation_width(_remove_whitespace(value))


def _classify_format_repair(raw_slice: str, quote: str) -> GroundingRepairStrategy:
    if _remove_whitespace(raw_slice) == _remove_whitespace(quote):
        return GroundingRepairStrategy.WHITESPACE
    if _normalize_punctuation_width(raw_slice) == _normalize_punctuation_width(quote):
        return GroundingRepairStrategy.PUNCTUATION_WIDTH
    return GroundingRepairStrategy.WHITESPACE_AND_PUNCTUATION_WIDTH


def _recover_unique_format_normalized_slice(
    description: str,
    quote: str,
) -> _RecoveredRawSlice | None:
    """Recover a unique raw JD slice under the narrow grounding format policy."""
    compact_quote = _normalize_grounding_text(quote)
    if not compact_quote:
        return None

    compact_description_chars: list[str] = []
    raw_indexes: list[int] = []
    for index, char in enumerate(description):
        if char.isspace():
            continue
        compact_description_chars.append(_normalize_width_punctuation(char))
        raw_indexes.append(index)
    compact_description = "".join(compact_description_chars)

    matches: list[int] = []
    start = compact_description.find(compact_quote)
    while start != -1:
        matches.append(start)
        if len(matches) > 1:
            return None
        start = compact_description.find(compact_quote, start + 1)
    if len(matches) != 1:
        return None

    compact_start = matches[0]
    compact_end = compact_start + len(compact_quote) - 1
    raw_start = raw_indexes[compact_start]
    raw_end = raw_indexes[compact_end] + 1
    raw_slice = description[raw_start:raw_end]
    return _RecoveredRawSlice(
        value=raw_slice,
        strategy=_classify_format_repair(raw_slice, quote),
    )


def repair_job_requirement_grounding(
    description: str,
    output: JobRequirementExtractionOutput,
) -> JobRequirementGroundingRepairResult:
    """Repair quotes only from deterministic verbatim JD evidence.

    Exact grounding remains preferred. When a provider changes whitespace or only the
    width of ASCII punctuation, a quote may be recovered iff the normalized quote has
    exactly one occurrence in the JD; the persisted value is always the original raw JD
    slice. No fuzzy or semantic matching is allowed.
    """
    repaired = []
    repair_events: list[GroundingRepairEvent] = []
    for requirement_index, item in enumerate(output.requirements):
        original_text = item.original_text.strip()
        evidence_span = item.evidence_span.strip()
        original_grounded = bool(original_text) and original_text in description
        evidence_grounded = bool(evidence_span) and evidence_span in description
        if not original_grounded and evidence_grounded:
            repaired.append(replace(item, original_text=evidence_span))
            repair_events.append(
                GroundingRepairEvent(
                    requirement_index=requirement_index,
                    field="originalText",
                    strategy=GroundingRepairStrategy.VERBATIM_COUNTERPART,
                )
            )
            continue
        if original_grounded and not evidence_grounded:
            repaired.append(replace(item, evidence_span=original_text))
            repair_events.append(
                GroundingRepairEvent(
                    requirement_index=requirement_index,
                    field="evidenceSpan",
                    strategy=GroundingRepairStrategy.VERBATIM_COUNTERPART,
                )
            )
            continue

        recovered_original = (
            _recover_unique_format_normalized_slice(description, original_text)
            if not original_grounded
            else None
        )
        recovered_evidence = (
            _recover_unique_format_normalized_slice(description, evidence_span)
            if not evidence_grounded
            else None
        )
        if recovered_original is not None:
            repair_events.append(
                GroundingRepairEvent(
                    requirement_index=requirement_index,
                    field="originalText",
                    strategy=recovered_original.strategy,
                )
            )
        if recovered_evidence is not None:
            repair_events.append(
                GroundingRepairEvent(
                    requirement_index=requirement_index,
                    field="evidenceSpan",
                    strategy=recovered_evidence.strategy,
                )
            )
        if recovered_original is not None or recovered_evidence is not None:
            repaired.append(
                replace(
                    item,
                    original_text=(
                        recovered_original.value
                        if recovered_original is not None
                        else original_text
                    ),
                    evidence_span=(
                        recovered_evidence.value
                        if recovered_evidence is not None
                        else evidence_span
                    ),
                )
            )
            continue
        repaired.append(item)
    return JobRequirementGroundingRepairResult(
        output=JobRequirementExtractionOutput(requirements=tuple(repaired)),
        repairs=tuple(repair_events),
    )


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
