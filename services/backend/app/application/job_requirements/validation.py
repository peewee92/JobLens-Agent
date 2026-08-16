"""Deterministic grounding and business validation for Requirement output."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
import re

from app.application.job_requirements.errors import (
    InvalidRequirementExtractorOutputError,
)
from app.application.job_requirements.models import (
    JobRequirementExtractionOutput,
    ProposedJobRequirement,
)
from app.domain.job_requirements import RequirementImportance, RequirementType

MAX_REQUIREMENTS_PER_RUN = 50
GROUNDING_POLICY_VERSION = "grounding-v1"
SEMANTIC_POLICY_VERSION = "requirement-semantics-v4"


class GroundingRepairStrategy(StrEnum):
    VERBATIM_COUNTERPART = "verbatim_counterpart"
    WHITESPACE = "whitespace"
    PUNCTUATION_WIDTH = "punctuation_width"
    WHITESPACE_AND_PUNCTUATION_WIDTH = "whitespace_and_punctuation_width"


class SemanticRepairStrategy(StrEnum):
    WAIVER_SCOPE = "waiver_scope"
    DROP_REDUNDANT_WAIVER = "drop_redundant_waiver"
    SPLIT_TRAILING_PREFERRED = "split_trailing_preferred"
    SYNTHESIZE_ALTERNATIVE_GROUP = "synthesize_alternative_group"
    INLINE_ALTERNATIVE_GROUP = "inline_alternative_group"
    ALTERNATIVE_CHILD = "alternative_child"


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
class SemanticRepairEvent:
    requirement_index: int
    strategy: SemanticRepairStrategy


@dataclass(frozen=True, slots=True)
class JobRequirementSemanticRepairResult:
    output: JobRequirementExtractionOutput
    repairs: tuple[SemanticRepairEvent, ...]


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


_WAIVER_MARKERS = (
    "可放宽",
    "可豁免",
    "不限年限",
    "waived",
    "waiver",
    "exception",
    "can be relaxed",
    "may be relaxed",
)
_THRESHOLD_PATTERN = re.compile(
    r"(?:\d+\s*年|[一二三四五六七八九十两]+\s*年|以上|至少|不少于|不低于|本科|硕士|博士|years?|degree|minimum|at least)",
    re.IGNORECASE,
)
_WAIVER_BRIDGE_PATTERN = re.compile(
    r"^[\s,，:：()（）]*(?:(?:表现|特别)?优秀(?:候选人|者)?|exceptional\s+candidates?|strong\s+candidates?)?[\s,，:：()（）]*$",
    re.IGNORECASE,
)
_COMBINED_EXPERIENCE_WAIVER_PATTERN = re.compile(
    r"(?:不限年限|年限.{0,8}(?:可放宽|可豁免)|(?:可放宽|可豁免).{0,8}年限|(?:表现|特别)?优秀(?:候选人|者)?.{0,8}(?:可放宽|可豁免)|exceptional\s+candidates?.{0,16}(?:waived|relaxed|exception))",
    re.IGNORECASE,
)
_UNRELATED_WAIVER_TARGET_PATTERN = re.compile(
    r"(?:学历|学位|专业|年龄|证书|户籍|地点|地域|城市|语言|英语).{0,8}(?:可放宽|可豁免)",
    re.IGNORECASE,
)
_TRAILING_PREFERRED_EXPERIENCE_PATTERN = re.compile(
    r"(?P<suffix>有[^，,。；;\n]{1,80}经验者优先)\s*[。.]?$",
    re.IGNORECASE,
)
_TRAILING_PREFERRED_SKILL_PATTERN = re.compile(
    r"(?P<suffix>熟悉[^，,。；;\n]{1,80}者优先)\s*[。.]?$",
    re.IGNORECASE,
)
_SOFT_MARKER_PATTERN = re.compile(
    r"(?:优先|加分|可选|optional|preferred|bonus)",
    re.IGNORECASE,
)
_EXPLICIT_OR_PATTERN = re.compile(
    r"(?:或者|或|\bor\b)",
    re.IGNORECASE,
)
_ALTERNATIVE_GROUP_PATTERN = re.compile(
    r"(?:至少.{0,24}(?:一个|一项|一种|两项|2\s*项|2\s*个)|任意.{0,12}(?:一个|一项|一种)|任选|任一|at\s+least\s+\w+\s+(?:of|from)|one\s+of|any\s+(?:one|of))",
    re.IGNORECASE,
)
_EXPLICIT_CHILD_HARD_PATTERN = re.compile(
    r"(?:必须|必需|均需|全部需要|all\s+of|required|\bmust\b)",
    re.IGNORECASE,
)
_TOP_LEVEL_NUMBERED_ITEM_PATTERN = re.compile(r"(?m)^[ \t]*\d+\s*[.、．)]")
_STRONG_CLAUSE_BOUNDARIES = "\n。；;"


def _unique_exact_span(description: str, quote: str) -> tuple[int, int] | None:
    value = quote.strip()
    if not value:
        return None
    start = description.find(value)
    if start < 0:
        return None
    if description.find(value, start + 1) >= 0:
        return None
    return start, start + len(value)


def _same_clause_end(description: str, start: int) -> int:
    candidates = [
        index
        for marker in _STRONG_CLAUSE_BOUNDARIES
        if (index := description.find(marker, start)) >= 0
    ]
    return min(candidates) if candidates else len(description)


def _contains_waiver(value: str) -> bool:
    folded = value.casefold()
    return any(marker.casefold() in folded for marker in _WAIVER_MARKERS)


def _waiver_is_local_to_threshold(clause: str, threshold_text: str) -> bool:
    folded = clause.casefold()
    marker_positions = [
        position
        for marker in _WAIVER_MARKERS
        if (position := folded.find(marker.casefold())) >= 0
    ]
    if not marker_positions:
        return False
    marker_start = min(marker_positions)
    bridge = clause[len(threshold_text):marker_start]
    return bool(_WAIVER_BRIDGE_PATTERN.fullmatch(bridge))


def _combined_waiver_targets_experience_threshold(item: ProposedJobRequirement) -> bool:
    if item.type is not RequirementType.EXPERIENCE:
        return False
    text = item.original_text.strip()
    if not _contains_waiver(text) or not _THRESHOLD_PATTERN.search(text):
        return False
    if _UNRELATED_WAIVER_TARGET_PATTERN.search(text):
        return False
    return bool(_COMBINED_EXPERIENCE_WAIVER_PATTERN.search(text))


def _preferred_suffix_requirement(
    suffix: str,
    *,
    confidence: float,
) -> ProposedJobRequirement | None:
    value = suffix.strip()
    if value.startswith("有") and "经验者优先" in value:
        return ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=value,
            normalized_capability=None,
            importance=RequirementImportance.PREFERRED,
            evidence_span=value,
            confidence=confidence,
        )
    if value.startswith("熟悉") and value.endswith("者优先"):
        capability = value[len("熟悉") : -len("者优先")].strip(" ，,。.;；")
        if not capability:
            return None
        return ProposedJobRequirement(
            type=RequirementType.SKILL,
            original_text=value,
            normalized_capability=capability,
            importance=RequirementImportance.PREFERRED,
            evidence_span=value,
            confidence=confidence,
        )
    return None


def _split_trailing_preferred_clause(
    item: ProposedJobRequirement,
) -> tuple[ProposedJobRequirement, ProposedJobRequirement] | None:
    if item.importance is not RequirementImportance.PREFERRED:
        return None
    text = item.original_text.strip()
    match = _TRAILING_PREFERRED_EXPERIENCE_PATTERN.search(text)
    if match is None:
        match = _TRAILING_PREFERRED_SKILL_PATTERN.search(text)
    if match is None or match.start("suffix") <= 0:
        return None

    prefix_with_bridge = text[: match.start("suffix")]
    separator_index = max(
        prefix_with_bridge.rfind(","),
        prefix_with_bridge.rfind("，"),
        prefix_with_bridge.rfind(";"),
        prefix_with_bridge.rfind("；"),
    )
    if separator_index < 0:
        return None
    bridge = prefix_with_bridge[separator_index + 1 :].strip().casefold()
    if bridge in {"或", "或者", "or"}:
        return None

    hard_text = prefix_with_bridge[:separator_index].strip()
    if not hard_text or _SOFT_MARKER_PATTERN.search(hard_text):
        return None
    soft_item = _preferred_suffix_requirement(
        match.group("suffix"),
        confidence=item.confidence,
    )
    if soft_item is None:
        return None

    hard_item = replace(
        item,
        original_text=hard_text,
        evidence_span=hard_text,
        importance=RequirementImportance.MUST_HAVE,
        normalized_capability=(
            item.normalized_capability if item.type is RequirementType.SKILL else None
        ),
    )
    return hard_item, soft_item


def repair_job_requirement_semantics(
    description: str,
    output: JobRequirementExtractionOutput,
) -> JobRequirementSemanticRepairResult:
    """Apply narrow deterministic repairs for two high-risk matching semantics.

    The repair is intentionally conservative: it requires exact grounded spans plus
    explicit waiver/cardinality wording in the JD. It never invents text or infers a
    relationship from semantic similarity.
    """
    indexed_items = list(enumerate(output.requirements))
    repairs: list[SemanticRepairEvent] = []
    waiver_ranges: list[tuple[int, int, int]] = []
    repaired_items: list[tuple[int, ProposedJobRequirement]] = []

    for requirement_index, item in indexed_items:
        repaired_item = item
        span = _unique_exact_span(description, item.original_text)
        if (
            span is not None
            and item.importance is RequirementImportance.MUST_HAVE
            and _THRESHOLD_PATTERN.search(item.original_text)
        ):
            if _combined_waiver_targets_experience_threshold(item):
                repaired_item = replace(
                    item,
                    importance=RequirementImportance.PREFERRED,
                )
                waiver_ranges.append((requirement_index, span[0], span[1]))
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=SemanticRepairStrategy.WAIVER_SCOPE,
                    )
                )
            else:
                clause_end = _same_clause_end(description, span[1])
                affected_clause = description[span[0]:clause_end].rstrip()
                if (
                    _contains_waiver(affected_clause)
                    and not _contains_waiver(item.original_text)
                    and _waiver_is_local_to_threshold(affected_clause, item.original_text)
                ):
                    repaired_item = replace(
                        item,
                        original_text=affected_clause,
                        evidence_span=affected_clause,
                        importance=RequirementImportance.PREFERRED,
                    )
                    waiver_ranges.append((requirement_index, span[0], clause_end))
                    repairs.append(
                        SemanticRepairEvent(
                            requirement_index=requirement_index,
                            strategy=SemanticRepairStrategy.WAIVER_SCOPE,
                        )
                    )
        repaired_items.append((requirement_index, repaired_item))

    if waiver_ranges:
        kept_items: list[tuple[int, ProposedJobRequirement]] = []
        for requirement_index, item in repaired_items:
            drop_as_redundant = False
            if requirement_index not in {item[0] for item in waiver_ranges}:
                span = _unique_exact_span(description, item.original_text)
                if span is not None and _contains_waiver(item.original_text):
                    drop_as_redundant = any(
                        range_start <= span[0] and span[1] <= range_end
                        for _, range_start, range_end in waiver_ranges
                    )
            if drop_as_redundant:
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=SemanticRepairStrategy.DROP_REDUNDANT_WAIVER,
                    )
                )
                continue
            kept_items.append((requirement_index, item))
        repaired_items = kept_items

    existing_texts = {item.original_text.strip() for _, item in repaired_items}
    split_items: list[tuple[int, ProposedJobRequirement]] = []
    for requirement_index, item in repaired_items:
        split = _split_trailing_preferred_clause(item)
        if split is None:
            split_items.append((requirement_index, item))
            continue
        hard_item, soft_item = split
        split_items.append((requirement_index, hard_item))
        if soft_item.original_text not in existing_texts:
            split_items.append((requirement_index, soft_item))
            existing_texts.add(soft_item.original_text)
        repairs.append(
            SemanticRepairEvent(
                requirement_index=requirement_index,
                strategy=SemanticRepairStrategy.SPLIT_TRAILING_PREFERRED,
            )
        )
    repaired_items = split_items

    sibling_groups: dict[tuple[str, str], list[tuple[int, ProposedJobRequirement]]] = {}
    for requirement_index, item in repaired_items:
        text = item.original_text.strip()
        evidence = item.evidence_span.strip()
        if (
            item.type is RequirementType.SKILL
            and item.importance is RequirementImportance.MUST_HAVE
            and item.normalized_capability
            and _EXPLICIT_OR_PATTERN.search(text)
            and not _SOFT_MARKER_PATTERN.search(text)
            and _unique_exact_span(description, text) is not None
        ):
            sibling_groups.setdefault((text, evidence), []).append(
                (requirement_index, item)
            )

    explicit_or_groups = {
        key: members
        for key, members in sibling_groups.items()
        if len({
            member.normalized_capability.strip().casefold()
            for _, member in members
            if member.normalized_capability
        }) >= 2
    }
    existing_group_texts = {
        item.original_text.strip()
        for _, item in repaired_items
        if item.type is RequirementType.CONSTRAINT
        and item.importance is RequirementImportance.MUST_HAVE
        and _EXPLICIT_OR_PATTERN.search(item.original_text)
    }
    if explicit_or_groups:
        grouped_items: list[tuple[int, ProposedJobRequirement]] = []
        emitted_groups: set[tuple[str, str]] = set()
        for requirement_index, item in repaired_items:
            key = (item.original_text.strip(), item.evidence_span.strip())
            members = explicit_or_groups.get(key)
            if members is None or item.type is not RequirementType.SKILL:
                grouped_items.append((requirement_index, item))
                continue
            if key not in emitted_groups:
                emitted_groups.add(key)
                if key[0] not in existing_group_texts:
                    grouped_items.append(
                        (
                            requirement_index,
                            ProposedJobRequirement(
                                type=RequirementType.CONSTRAINT,
                                original_text=key[0],
                                normalized_capability=None,
                                importance=RequirementImportance.MUST_HAVE,
                                evidence_span=key[1],
                                confidence=min(member.confidence for _, member in members),
                            ),
                        )
                    )
                    repairs.append(
                        SemanticRepairEvent(
                            requirement_index=requirement_index,
                            strategy=SemanticRepairStrategy.SYNTHESIZE_ALTERNATIVE_GROUP,
                        )
                    )
            grouped_items.append(
                (requirement_index, replace(item, importance=RequirementImportance.PREFERRED))
            )
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.ALTERNATIVE_CHILD,
                )
            )
        repaired_items = grouped_items

    inline_group_items: list[tuple[int, ProposedJobRequirement]] = []
    for requirement_index, item in repaired_items:
        if (
            item.type is RequirementType.SKILL
            and item.importance is RequirementImportance.MUST_HAVE
            and item.normalized_capability
            and _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
            and not _SOFT_MARKER_PATTERN.search(item.original_text)
            and _unique_exact_span(description, item.original_text) is not None
        ):
            item = replace(
                item,
                type=RequirementType.CONSTRAINT,
                normalized_capability=None,
            )
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.INLINE_ALTERNATIVE_GROUP,
                )
            )
        inline_group_items.append((requirement_index, item))
    repaired_items = inline_group_items

    group_scopes: list[tuple[int, int]] = []
    for _, item in repaired_items:
        if not _ALTERNATIVE_GROUP_PATTERN.search(item.original_text):
            continue
        span = _unique_exact_span(description, item.original_text)
        if span is None:
            continue
        next_item = _TOP_LEVEL_NUMBERED_ITEM_PATTERN.search(description, span[1])
        scope_end = next_item.start() if next_item is not None else len(description)
        group_scopes.append((span[1], scope_end))

    final_items = []
    for requirement_index, item in repaired_items:
        span = _unique_exact_span(description, item.original_text)
        is_alternative_child = (
            span is not None
            and item.importance is RequirementImportance.MUST_HAVE
            and not _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
            and not _EXPLICIT_CHILD_HARD_PATTERN.search(item.original_text)
            and any(scope_start < span[0] < scope_end for scope_start, scope_end in group_scopes)
        )
        if is_alternative_child:
            item = replace(item, importance=RequirementImportance.PREFERRED)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.ALTERNATIVE_CHILD,
                )
            )
        final_items.append(item)

    return JobRequirementSemanticRepairResult(
        output=JobRequirementExtractionOutput(requirements=tuple(final_items)),
        repairs=tuple(repairs),
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

    seen: set[tuple[str, str, str, str]] = set()
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
            original_text.casefold(),
            evidence_span.casefold(),
        )
        if identity in seen:
            raise InvalidRequirementExtractorOutputError(
                f"Requirement {index} duplicates an earlier requirement"
            )
        seen.add(identity)
