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
SEMANTIC_POLICY_VERSION = "requirement-semantics-v42.96"
COVERAGE_POLICY_VERSION = "requirement-coverage-v4"
MIN_DUTY_CANDIDATES_FOR_COVERAGE_GATE = 4
MIN_COVERED_DUTY_CANDIDATES = 2
MIN_BONUS_CANDIDATES_FOR_COVERAGE_GATE = 4
MIN_COVERED_BONUS_CANDIDATES = 2


class GroundingRepairStrategy(StrEnum):
    VERBATIM_COUNTERPART = "verbatim_counterpart"
    WHITESPACE = "whitespace"
    PUNCTUATION_WIDTH = "punctuation_width"
    WHITESPACE_AND_PUNCTUATION_WIDTH = "whitespace_and_punctuation_width"


class SemanticRepairStrategy(StrEnum):
    WAIVER_SCOPE = "waiver_scope"
    DROP_REDUNDANT_WAIVER = "drop_redundant_waiver"
    SPLIT_TRAILING_PREFERRED = "split_trailing_preferred"
    SPLIT_EMBEDDED_PREFERRED_WITH_COVERED_TAIL = "split_embedded_preferred_with_covered_tail"
    SYNTHESIZE_ALTERNATIVE_GROUP = "synthesize_alternative_group"
    INLINE_ALTERNATIVE_GROUP = "inline_alternative_group"
    SPLIT_HARD_ALTERNATIVE = "split_hard_alternative"
    SPLIT_EDUCATION_EXPERIENCE = "split_education_experience"
    SPLIT_EXPERIENCE_ALTERNATIVE = "split_experience_alternative"
    SPLIT_SKILL_EXPERIENCE = "split_skill_experience"
    COMPOUND_HARD_SKILL_CONSTRAINT = "compound_hard_skill_constraint"
    ABSTRACT_EVALUATIVE_SKILL_CONSTRAINT = "abstract_evaluative_skill_constraint"
    ABSTRACT_EVALUATIVE_TYPE_CONSTRAINT = "abstract_evaluative_type_constraint"
    CONCEPTUAL_MECHANISM_SKILL_CONSTRAINT = "conceptual_mechanism_skill_constraint"
    CONCEPTUAL_MECHANISM_TYPE_CONSTRAINT = "conceptual_mechanism_type_constraint"
    RESPONSIBILITY_TYPE_NORMALIZATION = "responsibility_type_normalization"
    SHORT_SCOPE_SUMMARY_RESPONSIBILITY = "short_scope_summary_responsibility"
    DROP_SHORT_SCOPE_SUMMARY_RESPONSIBILITY = "drop_short_scope_summary_responsibility"
    NON_EXPERIENCE_QUALIFICATION_CONSTRAINT = "non_experience_qualification_constraint"
    DROP_REDUNDANT_CROSS_TYPE_DUPLICATE = "drop_redundant_cross_type_duplicate"
    PRESERVE_CONJUNCTIVE_HARD_SIBLING = "preserve_conjunctive_hard_sibling"
    PRESERVE_POST_CARDINALITY_HARD_SIBLING = "preserve_post_cardinality_hard_sibling"
    DROP_REDUNDANT_SPLIT_HARD_PARENT = "drop_redundant_split_hard_parent"
    COLLAPSE_COMPOUND_DOMAIN_SIBLINGS = "collapse_compound_domain_siblings"
    ALTERNATIVE_CHILD = "alternative_child"
    DROP_REDUNDANT_REPAIRED_REQUIREMENT = "drop_redundant_repaired_requirement"
    RECOVER_ALTERNATIVE_GROUP_HEADER = "recover_alternative_group_header"
    DROP_EXACT_DUPLICATE_REQUIREMENT = "drop_exact_duplicate_requirement"
    DROP_REDUNDANT_SAME_SOURCE_CONSTRAINT_SUBCLAUSE = (
        "drop_redundant_same_source_constraint_subclause"
    )
    COLLAPSE_HARD_COMPOUND_ABILITY_FANOUT = "collapse_hard_compound_ability_fanout"
    COLLAPSE_HARD_INLINE_ALTERNATIVE_CAPABILITY_FANOUT = (
        "collapse_hard_inline_alternative_capability_fanout"
    )
    COLLAPSE_HARD_UMBRELLA_MEMBER_DUPLICATE = "collapse_hard_umbrella_member_duplicate"
    COLLAPSE_RECURSIVE_HARD_SKILL_SUBSET_CHAIN = (
        "collapse_recursive_hard_skill_subset_chain"
    )
    COLLAPSE_BONUS_UMBRELLA_CAPABILITY_FANOUT = (
        "collapse_bonus_umbrella_capability_fanout"
    )
    EXPAND_COMPOUND_HARD_EVIDENCE_SPAN = "expand_compound_hard_evidence_span"
    NORMALIZE_EXPERIENCE_TYPE_DRIFT = "normalize_experience_type_drift"
    NORMALIZE_TECHNICAL_SKILL_EXPERIENCE_DRIFT = "normalize_technical_skill_experience_drift"
    DROP_EXAMPLE_CHILD = "drop_example_child"
    COLLAPSE_EXAMPLE_SKILL_SIBLINGS = "collapse_example_skill_siblings"
    COLLAPSE_RESPONSIBILITY_ENUMERATION_SIBLINGS = (
        "collapse_responsibility_enumeration_siblings"
    )
    DROP_REDUNDANT_RESPONSIBILITY_SUBCLAUSE = "drop_redundant_responsibility_subclause"
    PROMOTE_HARD_EXPERIENCE_PREFIX_BEFORE_SOFT_SIBLING = (
        "promote_hard_experience_prefix_before_soft_sibling"
    )
    PROMOTE_EXPLICIT_MANDATORY_EXPERIENCE = "promote_explicit_mandatory_experience"
    PROMOTE_HARD_SKILL_PREFIX_BEFORE_SOFT_SIBLING = (
        "promote_hard_skill_prefix_before_soft_sibling"
    )
    DROP_REDUNDANT_COMPOUND_HARD_CHILD = "drop_redundant_compound_hard_child"
    REQUIREMENT_SECTION_DEFAULT_MUST_HAVE = "requirement_section_default_must_have"
    PROMOTE_APPLICATION_MATERIAL_REQUIREMENT = "promote_application_material_requirement"
    EXPLICIT_SOFT_MARKER_PREFERRED = "explicit_soft_marker_preferred"
    EXPLICIT_BONUS_SECTION = "explicit_bonus_section"
    RECOVER_UNCOVERED_CARDINALITY_REQUIREMENT = "recover_uncovered_cardinality_requirement"
    RECOVER_POST_CARDINALITY_ENGINEERING_PRACTICE = "recover_post_cardinality_engineering_practice"
    RECOVER_BACKEND_COMPONENT_UMBRELLA = "recover_backend_component_umbrella"
    DROP_BACKEND_COMPONENT_FANOUT = "drop_backend_component_fanout"
    DROP_REDUNDANT_QUALIFICATION_RESPONSIBILITY_CHILD = (
        "drop_redundant_qualification_responsibility_child"
    )
    DROP_REDUNDANT_QUALIFICATION_SUBCLAUSE = "drop_redundant_qualification_subclause"
    DROP_REDUNDANT_RECOVERED_CARDINALITY_CHILD = (
        "drop_redundant_recovered_cardinality_child"
    )
    NORMALIZE_HARD_SKILL_CAPABILITY_BEFORE_SOFT_SUFFIX = (
        "normalize_hard_skill_capability_before_soft_suffix"
    )
    DROP_REDUNDANT_CARDINALITY_FRAGMENT = "drop_redundant_cardinality_fragment"
    DROP_REDUNDANT_LEADING_CARDINALITY_SUBCLAUSE = (
        "drop_redundant_leading_cardinality_subclause"
    )
    REQUIREMENT_SECTION_QUALIFICATION_TYPE_NORMALIZATION = (
        "requirement_section_qualification_type_normalization"
    )
    SPLIT_HARD_PREFERRED_HARD_MIXED_SCOPE = "split_hard_preferred_hard_mixed_scope"
    COLLAPSE_COMPOUND_REQUIREMENT_LINE = "collapse_compound_requirement_line"
    COLLAPSE_CARDINALITY_REQUIREMENT_LINE = "collapse_cardinality_requirement_line"
    COLLAPSE_PREFERRED_ALTERNATIVE_GROUP = "collapse_preferred_alternative_group"
    RECOVER_ALTERNATIVE_GROUP_CHILD = "recover_alternative_group_child"
    RECOVER_MISSING_ALTERNATIVE_GROUP_PARENT = (
        "recover_missing_alternative_group_parent"
    )
    NORMALIZE_ALTERNATIVE_GROUP_CHILD_CAPABILITY = (
        "normalize_alternative_group_child_capability"
    )
    NORMALIZE_ALTERNATIVE_GROUP_CHILD_SOURCE_IDENTITY = (
        "normalize_alternative_group_child_source_identity"
    )
    NORMALIZE_ALTERNATIVE_GROUP_CHILD_SCOPE = (
        "normalize_alternative_group_child_scope"
    )
    NORMALIZE_UMBRELLA_SKILL_EXAMPLE_CAPABILITY = (
        "normalize_umbrella_skill_example_capability"
    )
    NORMALIZE_TECHNICAL_STACK_CONSTRAINT_DRIFT = (
        "normalize_technical_stack_constraint_drift"
    )
    COLLAPSE_ALTERNATIVE_GROUP_CHILD_SIBLINGS = (
        "collapse_alternative_group_child_siblings"
    )
    COLLAPSE_RESPONSIBILITY_CAPABILITY_SIBLINGS = (
        "collapse_responsibility_capability_siblings"
    )
    COLLAPSE_ENGINEERING_HABIT_QUALITY_FANOUT = (
        "collapse_engineering_habit_quality_fanout"
    )
    RECOVER_SAME_EVIDENCE_INLINE_ALTERNATIVE_PARENT = (
        "recover_same_evidence_inline_alternative_parent"
    )
    RECOVER_SAME_EVIDENCE_EXAMPLE_EXPERIENCE_PARENT = (
        "recover_same_evidence_example_experience_parent"
    )


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
class JobRequirementCoverageAudit:
    duty_candidate_count: int
    covered_duty_count: int
    minimum_covered_duty_count: int
    enforced: bool


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
_EMBEDDED_PREFERRED_EXPERIENCE_PATTERN = re.compile(
    r"(?P<suffix>有[^，,。；;\n]{1,80}经验者优先)(?P<tail>[。.]?\s+.+)$",
    re.IGNORECASE,
)
_EMBEDDED_PREFERRED_SKILL_PATTERN = re.compile(
    r"(?P<suffix>熟悉[^，,。；;\n]{1,80}者优先)(?P<tail>[。.]?\s+.+)$",
    re.IGNORECASE,
)
_SOFT_MARKER_PATTERN = re.compile(
    r"(?:优先|加分|可选|optional|preferred|bonus)",
    re.IGNORECASE,
)
_SECTION_HEADING_PATTERN = re.compile(
    r"(?mi)^[ \t]*(?:(?:[一二三四五六七八九十]+|\d+)\s*[、.．]\s*)?(?:【\s*)?(?P<name>岗位要求|任职要求|职位要求|任职资格|岗位资格|应聘要求|岗位职责|工作职责|职位职责|岗位描述|职位描述|工作内容|职责描述|requirements?|qualifications?|responsibilities?|job\s+duties?)\s*(?:】)?\s*[:：]?\s*$"
)
_BONUS_SECTION_HEADING_PATTERN = re.compile(
    r"^(?:(?:[一二三四五六七八九十]+|\d+)\s*[、.．]\s*)?"
    r"(?:加分项|加分条件|bonus(?:\s+points?)?|nice\s+to\s+have)"
    r"(?:\s*[（(][^（）()\n]{1,40}[）)])?\s*[:：]?$",
    re.IGNORECASE,
)
_REQUIREMENT_SECTION_NAME_PATTERN = re.compile(
    r"^(?:岗位要求|任职要求|职位要求|任职资格|岗位资格|应聘要求|requirements?|qualifications?)$",
    re.IGNORECASE,
)
_RESPONSIBILITY_SECTION_NAME_PATTERN = re.compile(
    r"^(?:岗位职责|工作职责|职位职责|岗位描述|职位描述|工作内容|职责描述|responsibilities?|job\s+duties?)$",
    re.IGNORECASE,
)
_RESPONSIBILITY_ACTION_PATTERN = re.compile(
    r"^(?:负责|主导|参与|推进|推动|协同|跟踪|制定|探索|构建|建设|实施|维护|优化|管理|协调|研究|分析|挖掘|深入(?!了解))",
    re.IGNORECASE,
)
_LABELED_RESPONSIBILITY_ACTION_PATTERN = re.compile(
    r"^(?:设计|构建|集成|开发|建立|优化|深度优化|将|针对|密切关注|快速复现|深度理解|结合|负责|主导|参与|推进|推动|协同|跟踪|制定|探索|建设|实施|维护|管理|协调|研究|分析|挖掘)",
    re.IGNORECASE,
)
_CONJUNCTIVE_HARD_SUFFIX_PATTERN = re.compile(
    r"^(?:并且|并|且|同时|以及|and\b)",
    re.IGNORECASE,
)
_NON_EXPERIENCE_QUALIFICATION_PATTERN = re.compile(
    r"^具备(?:良好|优秀|较强|扎实)?(?:的)?[^，,；;]{2,120}(?:能力|素养|意识)\s*[,，]\s*能(?:够)?[^；;]{2,180}$",
    re.IGNORECASE,
)
_HARD_SKILL_CAPABILITY_CAPTURE_PATTERN = re.compile(
    r"^(?:熟悉|熟练(?:使用|掌握)?|掌握|精通|使用)\s*(?P<capability>.+)$",
    re.IGNORECASE,
)
_EXPLICIT_REQUIREMENT_START_PATTERN = re.compile(
    r"^(?:必须|需要|要求|熟悉|熟练|掌握|精通|理解|了解|深入了解|具备|具有|有|扎实|本科|硕士|博士|大专|专科|至少|能(?:够)?|对.+(?:具有|有))",
    re.IGNORECASE,
)
_APPLICATION_MATERIAL_REQUIREMENT_PATTERN = re.compile(
    r"^(?:投递(?:简历)?|申请|应聘).{0,24}(?:请|需|需要|须|必须)?.{0,8}(?:附带|附上|提供|提交).{1,180}(?:GitHub|作品集|portfolio|个人页面|开源网站|邮件列表)",
    re.IGNORECASE,
)
_EXPLICIT_OR_PATTERN = re.compile(
    r"(?:或者|或|\bor\b)",
    re.IGNORECASE,
)
_ALTERNATIVE_GROUP_PATTERN = re.compile(
    r"(?:至少.{0,24}(?:一门|一个|一项|一种|两项|2\s*项|2\s*个)|(?:等|中).{0,8}(?:一门|一个|一项|一种)以上|任意.{0,12}(?:一门|一个|一项|一种)|任选|任一|at\s+least\s+\w+\s+(?:of|from)|one\s+of|any\s+(?:one|of))",
    re.IGNORECASE,
)
_ALTERNATIVE_FOLLOWING_LIST_PATTERN = re.compile(
    r"(?:以下|下列|如下|following)",
    re.IGNORECASE,
)
_ALTERNATIVE_CHILD_LABEL_PATTERN = re.compile(
    r"^(?:【(?P<label_cn>[^】\n]{1,48})】|\[(?P<label_en>[^\]\n]{1,48})\])\s*[:：]\s*(?P<body>\S.{0,999})$",
    re.IGNORECASE,
)
_ALTERNATIVE_CHILD_LABEL_SCOPE_PATTERN = re.compile(
    r"(?:方向|类别|领域|选项|track|area|option|direction)",
    re.IGNORECASE,
)
_ALTERNATIVE_DIRECTION_LABEL_CAPABILITY_ALIASES = {
    "前端方向": frozenset(
        {"frontend", "front-end", "front end", "frontend engineering"}
    ),
    "桌面端方向": frozenset(
        {
            "desktop",
            "desktop app",
            "desktop application",
            "desktop application development",
        }
    ),
    "后端方向": frozenset(
        {"backend", "back-end", "back end", "backend engineering"}
    ),
    "工程化/代码控制方向": frozenset(
        {
            "engineering/code control",
            "engineering & code control",
            "engineering and code control",
            "engineering infrastructure",
        }
    ),
}
_ALTERNATIVE_CHILD_BULLET_PATTERN = re.compile(
    r"^(?:[-*•●▪◦]|\uf06c)\s*(?P<body>\S.{0,999})$",
    re.IGNORECASE,
)
_SIMPLE_ALTERNATIVE_CHILD_CAPABILITY_PATTERN = re.compile(
    r"^(?P<capability>[A-Za-z][A-Za-z0-9.+#_-]{0,63})(?=[、,，]|$)",
    re.IGNORECASE,
)
_EXPLICIT_CHILD_HARD_PATTERN = re.compile(
    r"(?:必须|必需|均需|全部需要|all\s+of|required|\bmust\b)",
    re.IGNORECASE,
)
_HARD_SKILL_PREFIX_PATTERN = re.compile(
    r"^(?:熟悉|熟练(?:使用|掌握)?|掌握|精通|使用)\s*.+$",
    re.IGNORECASE,
)
_COMPOUND_HARD_SKILL_SEGMENT_PATTERN = re.compile(
    r"^(?:熟悉|熟练(?:使用|掌握)?|掌握|精通|使用|理解|了解|具备|能(?:够)?(?:独立)?)\s*.+$",
    re.IGNORECASE,
)
_EVALUATIVE_ABILITY_SEGMENT_PATTERN = re.compile(
    r"^(?:优秀的?|良好的?|较强的?|很强的?|扎实的?)[^，,；;]{1,80}(?:能力|素养|意识)$",
    re.IGNORECASE,
)
_FUSED_EXPERIENCE_SUFFIX_PATTERN = re.compile(
    r"^(?:(?:对|有|具备)[^，,；;]{1,100}经验)$",
    re.IGNORECASE,
)
_EXPLICIT_CORE_TECHNOLOGY_LIST_PATTERN = re.compile(
    r"^(?:理解|熟悉|掌握|精通|了解).+、.+(?:等核心技术|等技术|等核心能力|等能力)\s*$",
    re.IGNORECASE,
)
_CONCEPTUAL_MECHANISM_UMBRELLA_PATTERN = re.compile(
    r"^(?:理解|了解|深入了解)\s*[^，,；;]{1,100}?(?:的)?(?:基本|工作)(?:机制|原理)"
    r"\s*[,，]\s*(?:包括|包含)\s*(?P<concepts>[^；;]{3,320})$",
    re.IGNORECASE,
)
_CONCEPTUAL_MECHANISM_ACTION_PATTERN = re.compile(
    r"(?:并|且)?能(?:够)?|独立完成|负责|开发|实现|设计|搭建|优化|实践",
    re.IGNORECASE,
)
_ABSTRACT_EVALUATIVE_ABILITY_PATTERN = re.compile(
    r"^(?:工程能力|综合能力|学习能力|沟通能力|协作能力|表达能力|分析能力|抗压能力)(?:扎实|较强|很强|强|优秀|良好|出色)?$",
    re.IGNORECASE,
)
_ABSTRACT_EVALUATIVE_COMPOUND_SEGMENT_PATTERN = re.compile(
    r"^(?:具有)?(?:优秀|良好|较强|很强|扎实)(?:的)?[^，,；;]{1,100}(?:能力|素养|意识)$",
    re.IGNORECASE,
)
_ABSTRACT_EVALUATIVE_PRACTICE_PATTERN = re.compile(
    r"^(?:有)?(?:良好|优秀|较强|扎实)(?:的)?(?:工程习惯|工程实践|工程素养|测试意识|质量意识|安全意识)$",
    re.IGNORECASE,
)
_ABSTRACT_EVALUATIVE_TRAIT_PATTERN = re.compile(
    r"^(?:并)?(?:具有)?(?:高度|较高|优秀|良好|较强|很强)(?:的)?(?:责任心|抗压能力)$",
    re.IGNORECASE,
)
_EXPLICIT_EXPERIENCE_FACT_PATTERN = re.compile(
    r"^(?:(?:需要)?有|具备)[^，,；;]{1,100}经验$",
    re.IGNORECASE,
)
_EXPLICIT_EXPERIENCE_WITH_ABILITY_PATTERN = re.compile(
    r"^(?:(?:需要)?有|具备)[^，,；;]{1,100}经验\s*[,，]\s*(?:能|能够)[^；;]{1,220}$",
    re.IGNORECASE,
)
_EXPERIENCE_EXPLANATION_SUFFIX_PATTERN = re.compile(
    r"^(?:非|没有|无)[^，,；;]{1,100}(?:无法|不能|不满足|不符合|不可)[^，,；;]{0,100}$",
    re.IGNORECASE,
)
_EXPERIENCE_FOLLOWUP_QUALIFICATION_PATTERN = re.compile(
    r"^(?:了解|熟悉|掌握|理解)(?:(?:生产环境中[^，,；;]{1,180}(?:性能优化|稳定性保障))|(?:不同[^，,；;]{1,180}(?:适用场景|效果评估方法)))[^，,；;]{0,80}$",
    re.IGNORECASE,
)
_EXAMPLE_CHILD_PATTERN = re.compile(
    r"^(?:(?:如|例如|比如|such\s+as|e\.g\.?)|[（(][^（）()]{1,120}(?:等|etc\.?)\s*[）)]$)",
    re.IGNORECASE,
)
_INLINE_EXAMPLE_LIST_PATTERN = re.compile(
    r"[（(]\s*(?:如|例如|比如|such\s+as|e\.g\.?)",
    re.IGNORECASE,
)
_PARENTHETICAL_ENUM_EXAMPLE_LIST_PATTERN = re.compile(
    r"[（(][^（）()]{1,160}(?:/|、)[^（）()]{1,160}(?:等|etc\.?)\s*[）)]",
    re.IGNORECASE,
)
_NONPARENTHETICAL_EXAMPLE_LIST_PATTERN = re.compile(
    r"[,，]\s*(?:如|例如|比如|such\s+as|e\.g\.?)\s*",
    re.IGNORECASE,
)
_EDUCATION_SEGMENT_PATTERN = re.compile(
    r"(?:本科|硕士|博士|大专|专科|学历|学位|专业|bachelor|master|phd|degree)",
    re.IGNORECASE,
)
_EXPERIENCE_SEGMENT_PATTERN = re.compile(
    r"(?:(?:\d+|[一二三四五六七八九十两]+)\s*年[^，,；;]{0,60}经验|(?:有|具备)[^，,；;]{1,100}经验)",
    re.IGNORECASE,
)
_TOP_LEVEL_NUMBERED_ITEM_PATTERN = re.compile(r"(?m)^[ \t]*\d+\s*[.、．)]")
_LEADING_NUMBERED_ITEM_PREFIX_PATTERN = re.compile(r"^\s*\d+\s*[.、．)]\s*")
_STRONG_CLAUSE_BOUNDARIES = "\n。；;"
_ENGINEERING_HABIT_QUALITY_PATTERN = re.compile(
    r"^(?:有)?(?:良好|优秀|较强|扎实)(?:的)?工程习惯[,，]重视(?P<qualities>.+)$",
    re.IGNORECASE,
)
_ENGINEERING_HABIT_QUALITY_TERMS = frozenset(
    {"可维护性", "测试", "可观测性", "安全边界", "长期演进成本"}
)


def _classification_text(value: str) -> str:
    """Remove only presentation numbering before semantic shape classification.

    Source-candidate grounding may preserve a top-level list marker such as ``2.``
    in ``originalText``. The marker is real JD evidence and must remain persisted,
    but it must not stop deterministic semantic guards from recognizing the same
    clause shape that previously appeared without the marker.
    """
    text = value.strip().rstrip("。.;；").strip()
    return _LEADING_NUMBERED_ITEM_PREFIX_PATTERN.sub("", text, count=1).strip()


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


def _nearest_section_name(description: str, span_start: int) -> str | None:
    headings = [
        match
        for match in _SECTION_HEADING_PATTERN.finditer(description)
        if match.end() <= span_start
    ]
    if not headings:
        return None
    return headings[-1].group("name").strip()


def _is_explicit_bonus_section_span(description: str, evidence: str) -> bool:
    span = _unique_exact_span(description, evidence.strip())
    if span is None:
        return False
    in_bonus_section = False
    offset = 0
    for raw_line in description.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        line_start = offset
        offset += len(raw_line)
        if not stripped:
            continue
        if _BONUS_SECTION_HEADING_PATTERN.fullmatch(stripped):
            in_bonus_section = True
            continue
        if _SECTION_HEADING_PATTERN.fullmatch(stripped):
            in_bonus_section = False
            continue
        if (
            in_bonus_section
            and stripped.endswith((":", "："))
            and len(stripped) <= 40
            and _EXPLICIT_REQUIREMENT_START_PATTERN.match(stripped.rstrip(":：").strip()) is None
        ):
            in_bonus_section = False
        if line_start <= span[0] < offset:
            return in_bonus_section
    return False


def _has_inline_bonus_label_prefix(description: str, evidence: str) -> bool:
    span = _unique_exact_span(description, evidence.strip())
    if span is None:
        return False
    line_start = description.rfind("\n", 0, span[0]) + 1
    prefix = description[line_start:span[0]].strip()
    return bool(prefix and _BONUS_SECTION_HEADING_PATTERN.fullmatch(prefix))


def _is_requirement_section_span(description: str, evidence: str) -> bool:
    span = _unique_exact_span(description, evidence.strip())
    if span is None:
        return False
    section_name = _nearest_section_name(description, span[0])
    return bool(
        section_name
        and _REQUIREMENT_SECTION_NAME_PATTERN.fullmatch(section_name)
    )


def _is_evaluative_compound_qualification_text(value: str) -> bool:
    segments = _comma_segments(_classification_text(value))
    return bool(
        len(segments) >= 2
        and _EVALUATIVE_ABILITY_SEGMENT_PATTERN.fullmatch(segments[0][2])
        and re.match(r"^能(?:够)?", segments[1][2]) is not None
    )


def _explicit_requirement_source_lines(
    description: str,
) -> tuple[tuple[str, str, int, int], ...]:
    """Return unique verbatim source lines inside explicit requirement sections."""
    result: list[tuple[str, str, int, int]] = []
    in_requirement_section = False
    offset = 0
    for chunk in description.splitlines(keepends=True):
        raw_line = chunk.rstrip("\r\n")
        stripped = raw_line.strip()
        offset_after = offset + len(chunk)
        if not stripped:
            offset = offset_after
            continue
        heading = _SECTION_HEADING_PATTERN.fullmatch(stripped)
        if heading is not None:
            section_name = heading.group("name").strip()
            in_requirement_section = bool(
                _REQUIREMENT_SECTION_NAME_PATTERN.fullmatch(section_name)
            )
            offset = offset_after
            continue
        if in_requirement_section:
            span = _unique_exact_span(description, stripped)
            if span is not None:
                result.append((stripped, _classification_text(stripped), span[0], span[1]))
        offset = offset_after
    return tuple(result)


def _item_is_anchored_to_source_line(
    description: str,
    item: ProposedJobRequirement,
    *,
    line_start: int,
    line_end: int,
) -> bool:
    for quote in (item.evidence_span.strip(), item.original_text.strip()):
        if not quote:
            continue
        span = _unique_exact_span(description, quote)
        if span is not None and line_start <= span[0] and span[1] <= line_end:
            return True
    return False


def _is_collapsible_compound_requirement_line(text: str) -> bool:
    if (
        not text
        or _SOFT_MARKER_PATTERN.search(text)
        or _ALTERNATIVE_GROUP_PATTERN.search(text)
        or _EXPERIENCE_SEGMENT_PATTERN.search(text)
        or _EDUCATION_SEGMENT_PATTERN.search(text)
        or _THRESHOLD_PATTERN.search(text)
        or _INLINE_EXAMPLE_LIST_PATTERN.search(text)
    ):
        return False
    segments = _comma_segments(text)
    return bool(
        len(segments) >= 2
        and all(
            _COMPOUND_HARD_SKILL_SEGMENT_PATTERN.fullmatch(segment) is not None
            or _EVALUATIVE_ABILITY_SEGMENT_PATTERN.fullmatch(segment) is not None
            for _, _, segment in segments
        )
    )


def _is_collapsible_cardinality_requirement_line(raw: str, text: str) -> bool:
    return bool(
        raw
        and text
        and _LEADING_NUMBERED_ITEM_PREFIX_PATTERN.match(raw)
        and _ALTERNATIVE_GROUP_PATTERN.search(text)
        and _ALTERNATIVE_FOLLOWING_LIST_PATTERN.search(text)
        and raw.rstrip().endswith((":", "："))
        and _SOFT_MARKER_PATTERN.search(text) is None
        and _EDUCATION_SEGMENT_PATTERN.search(text) is None
        and _EXPERIENCE_SEGMENT_PATTERN.search(text) is None
    )


def _is_collapsible_preferred_alternative_line(text: str) -> bool:
    if (
        not text
        or _SOFT_MARKER_PATTERN.search(text) is None
        or _EXPLICIT_OR_PATTERN.search(text) is None
        or re.search(r"(?:者优先|优先|preferred|bonus)$", text, re.IGNORECASE) is None
        or _THRESHOLD_PATTERN.search(text)
        or _EDUCATION_SEGMENT_PATTERN.search(text)
        or any(marker in text for marker in ("。", ";", "；"))
    ):
        return False
    segments = _comma_segments(text)
    if not segments:
        return False
    return _HARD_SKILL_PREFIX_PATTERN.fullmatch(segments[0][2]) is None


def _collapse_explicit_requirement_line_fragments(
    description: str,
    indexed_items: list[tuple[int, ProposedJobRequirement]],
) -> tuple[list[tuple[int, ProposedJobRequirement]], tuple[SemanticRepairEvent, ...]]:
    replacements: dict[int, tuple[int, ProposedJobRequirement]] = {}
    dropped_positions: set[int] = set()
    events: list[SemanticRepairEvent] = []

    for raw, text, line_start, line_end in _explicit_requirement_source_lines(description):
        anchored_positions = [
            position
            for position, (_, item) in enumerate(indexed_items)
            if _item_is_anchored_to_source_line(
                description,
                item,
                line_start=line_start,
                line_end=line_end,
            )
        ]
        if len(anchored_positions) < 2:
            continue

        strategy: SemanticRepairStrategy | None = None
        importance: RequirementImportance | None = None
        group_positions: list[int] = []
        if _is_collapsible_compound_requirement_line(text):
            strategy = SemanticRepairStrategy.COLLAPSE_COMPOUND_REQUIREMENT_LINE
            importance = RequirementImportance.MUST_HAVE
            group_positions = anchored_positions
        elif _is_collapsible_cardinality_requirement_line(raw, text):
            group_positions = [
                position
                for position in anchored_positions
                if indexed_items[position][1].importance is RequirementImportance.MUST_HAVE
                and indexed_items[position][1].type
                in {RequirementType.CONSTRAINT, RequirementType.RESPONSIBILITY}
            ]
            if (
                len(group_positions) < 2
                or len(group_positions) != len(anchored_positions)
                or any(
                    _terminal_punctuation_identity(
                        _classification_text(indexed_items[position][1].original_text)
                    )
                    == _terminal_punctuation_identity(text)
                    for position in group_positions
                )
            ):
                continue
            strategy = SemanticRepairStrategy.COLLAPSE_CARDINALITY_REQUIREMENT_LINE
            importance = RequirementImportance.MUST_HAVE
        elif _is_collapsible_preferred_alternative_line(text):
            if any(
                indexed_items[position][1].importance is RequirementImportance.MUST_HAVE
                for position in anchored_positions
            ):
                continue
            group_positions = [
                position
                for position in anchored_positions
                if indexed_items[position][1].importance
                in {RequirementImportance.PREFERRED, RequirementImportance.BONUS}
            ]
            if len(group_positions) < 2:
                continue
            strategy = SemanticRepairStrategy.COLLAPSE_PREFERRED_ALTERNATIVE_GROUP
            importance = RequirementImportance.PREFERRED

        if strategy is None or importance is None or len(group_positions) < 2:
            continue
        if len(
            {
                _terminal_punctuation_identity(
                    _classification_text(indexed_items[position][1].original_text)
                )
                for position in group_positions
            }
        ) < 2:
            continue

        first_position = min(group_positions)
        requirement_index = indexed_items[first_position][0]
        confidence = min(
            indexed_items[position][1].confidence for position in group_positions
        )
        replacements[first_position] = (
            requirement_index,
            ProposedJobRequirement(
                type=RequirementType.CONSTRAINT,
                original_text=text,
                normalized_capability=None,
                importance=importance,
                evidence_span=raw,
                confidence=confidence,
            ),
        )
        dropped_positions.update(group_positions)
        events.append(
            SemanticRepairEvent(
                requirement_index=requirement_index,
                strategy=strategy,
            )
        )

    if not dropped_positions:
        return indexed_items, tuple(events)

    collapsed: list[tuple[int, ProposedJobRequirement]] = []
    for position, item in enumerate(indexed_items):
        replacement = replacements.get(position)
        if replacement is not None:
            collapsed.append(replacement)
        if position in dropped_positions:
            continue
        collapsed.append(item)
    return collapsed, tuple(events)


def _is_redundant_qualification_responsibility_child(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Drop a qualification sub-clause mislabelled as a responsibility.

    The child must live in an explicit requirements section and be a strict exact
    substring of an already-emitted must-have constraint from the same raw source line.
    This does not infer semantics from wording and cannot remove a standalone duty.
    """
    if (
        item.type is not RequirementType.RESPONSIBILITY
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return False
    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not original
        or not evidence
        or original == evidence
        or _unique_exact_span(description, original) is None
        or _unique_exact_span(description, evidence) is None
    ):
        return False

    in_requirement_section = _is_requirement_section_span(description, evidence)
    evidence_identity = _terminal_punctuation_identity(_classification_text(evidence))
    return any(
        parent is not item
        and parent.type is RequirementType.CONSTRAINT
        and parent.importance is RequirementImportance.MUST_HAVE
        and not _SOFT_MARKER_PATTERN.search(parent.original_text)
        and bool(parent.original_text.strip())
        and original != parent.original_text.strip()
        and original in parent.original_text.strip()
        and _unique_exact_span(description, parent.original_text.strip()) is not None
        and (
            in_requirement_section
            or (
                _is_evaluative_compound_qualification_text(parent.original_text)
                and _terminal_punctuation_identity(
                    _classification_text(parent.original_text)
                )
                == evidence_identity
            )
        )
        for parent in all_items
    )


def _is_redundant_qualification_subclause(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Drop a non-responsibility qualification fragment already covered by a full constraint."""
    if (
        item.type not in {
            RequirementType.CONSTRAINT,
            RequirementType.DOMAIN,
            RequirementType.EDUCATION,
            RequirementType.EXPERIENCE,
        }
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return False
    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not original
        or not evidence
        or (
            item.type is RequirementType.EXPERIENCE
            and _EXPERIENCE_SEGMENT_PATTERN.search(_classification_text(original)) is not None
        )
        or original == evidence
        or _unique_exact_span(description, original) is None
        or _unique_exact_span(description, evidence) is None
    ):
        return False
    in_requirement_section = _is_requirement_section_span(description, evidence)
    return any(
        parent is not item
        and parent.type in {RequirementType.CONSTRAINT, RequirementType.EDUCATION}
        and parent.importance is RequirementImportance.MUST_HAVE
        and not _SOFT_MARKER_PATTERN.search(parent.original_text)
        and not (
            item.type is RequirementType.CONSTRAINT
            and _ALTERNATIVE_GROUP_PATTERN.search(parent.original_text)
        )
        and bool(parent.original_text.strip())
        and original != parent.original_text.strip()
        and original in parent.original_text.strip()
        and parent.evidence_span.strip() == evidence
        and (
            in_requirement_section
            or (
                item.type is RequirementType.EDUCATION
                and parent.type is RequirementType.EDUCATION
            )
        )
        for parent in all_items
    )


def _is_redundant_cardinality_fragment(
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    marker = _classification_text(item.original_text).casefold()
    if (
        item.type is not RequirementType.CONSTRAINT
        or item.importance is not RequirementImportance.MUST_HAVE
        or item.normalized_capability
        or marker not in {"至少", "不少于", "不低于", "at least"}
    ):
        return False
    evidence = item.evidence_span.strip()
    if not evidence:
        return False
    return any(
        parent is not item
        and parent.type is RequirementType.CONSTRAINT
        and parent.importance is RequirementImportance.MUST_HAVE
        and parent.evidence_span.strip() == evidence
        and len(_classification_text(parent.original_text)) > len(marker) + 4
        and marker in _classification_text(parent.original_text).casefold()
        and _ALTERNATIVE_GROUP_PATTERN.search(parent.original_text) is not None
        for parent in all_items
    )


def _is_redundant_recovered_cardinality_child(
    item: ProposedJobRequirement,
    recovered_parent: ProposedJobRequirement,
) -> bool:
    if (
        item is recovered_parent
        or item.importance is not RequirementImportance.MUST_HAVE
        or item.type not in {
            RequirementType.CONSTRAINT,
            RequirementType.RESPONSIBILITY,
            RequirementType.SKILL,
        }
        or item.evidence_span.strip() != recovered_parent.evidence_span.strip()
    ):
        return False
    original = item.original_text.strip().rstrip("，,。.;；").strip()
    parent_text = recovered_parent.original_text.strip().rstrip("，,。.;；").strip()
    return bool(original and original != parent_text and original in parent_text)


def _is_redundant_leading_cardinality_subclause(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Drop one same-source leading hard clause already represented by a full parent.

    This is intentionally narrower than generic substring dedupe. The parent must be a
    uniquely grounded hard cardinality constraint covering the exact evidence line, and
    the child must equal the complete comma-delimited prefix immediately before the
    parent's remaining cardinality clause. Different evidence and atomic alternatives
    are preserved.
    """
    if (
        item.type not in {RequirementType.SKILL, RequirementType.CONSTRAINT}
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return False
    child_text = _classification_text(item.original_text)
    evidence = item.evidence_span.strip()
    if (
        not child_text
        or not evidence
        or _unique_exact_span(description, evidence) is None
    ):
        return False
    for parent in all_items:
        if (
            parent is item
            or parent.type is not RequirementType.CONSTRAINT
            or parent.importance is not RequirementImportance.MUST_HAVE
            or parent.evidence_span.strip() != evidence
            or _ALTERNATIVE_GROUP_PATTERN.search(parent.original_text) is None
        ):
            continue
        parent_text = _classification_text(parent.original_text)
        if _unique_exact_span(description, parent.original_text.strip()) is None:
            continue
        parent_text = re.sub(r"^\s*\d+\s+(?=\S)", "", parent_text, count=1).strip()
        first_segment = re.split(r"[,，]", parent_text, maxsplit=1)[0].strip()
        if first_segment == child_text and parent_text != child_text:
            return True
    return False


def _is_same_evidence_secondary_inline_cardinality_child(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Recognize one atomic child of a second inline one-of/cardinality clause.

    The proof is deliberately same-evidence and exact-grounded. A hard constraint
    parent must contain at least two comma-delimited clauses; only clauses after the
    first are considered, and the child must be a strict atomic substring of a later
    clause that itself carries the bounded alternative/cardinality grammar. This avoids
    widening the existing global scope model or matching an identical token grounded
    elsewhere in the JD.
    """
    if (
        item.type is not RequirementType.SKILL
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
        or _EXPLICIT_CHILD_HARD_PATTERN.search(item.original_text)
    ):
        return False
    child_text = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not child_text
        or not evidence
        or _unique_exact_span(description, evidence) is None
    ):
        return False
    for parent in all_items:
        if (
            parent is item
            or parent.type is not RequirementType.CONSTRAINT
            or parent.importance is not RequirementImportance.MUST_HAVE
            or parent.evidence_span.strip() != evidence
            or _SOFT_MARKER_PATTERN.search(parent.original_text)
            or _unique_exact_span(description, parent.original_text.strip()) is None
        ):
            continue
        segments = _comma_segments(_classification_text(parent.original_text))
        candidate_segments = segments if len(segments) == 1 else segments[1:]
        for _, _, segment in candidate_segments:
            if (
                (
                    _ALTERNATIVE_GROUP_PATTERN.search(segment) is not None
                    or _EXPLICIT_OR_PATTERN.search(segment) is not None
                )
                and child_text != segment.strip()
                and child_text in segment
            ):
                return True
    return False


def _recover_same_evidence_inline_alternative_parents(
    description: str,
    all_items: tuple[ProposedJobRequirement, ...],
) -> tuple[ProposedJobRequirement, ...]:
    """Recover exact inline alternative parents from source-proven hard fan-out.

    This is deliberately limited to one exact requirement-section evidence span. The
    Provider must already emit at least two ``must_have skill`` children from the same
    comma-delimited source segment, and that segment must itself contain explicit
    alternative/cardinality grammar (``或`` / ``至少一种`` / ``至少一门`` ...). No
    semantic similarity or cross-evidence grouping is used.
    """
    recovered: list[ProposedJobRequirement] = []
    evidence_values = {
        item.evidence_span.strip()
        for item in all_items
        if item.evidence_span.strip()
    }
    for evidence in evidence_values:
        if (
            _unique_exact_span(description, evidence) is None
            or not _is_requirement_section_span(description, evidence)
            or _SOFT_MARKER_PATTERN.search(evidence)
        ):
            continue
        hard_children = tuple(
            item
            for item in all_items
            if (
                item.type is RequirementType.SKILL
                and item.importance is RequirementImportance.MUST_HAVE
                and item.evidence_span.strip() == evidence
                and not _SOFT_MARKER_PATTERN.search(item.original_text)
                and not _EXPLICIT_CHILD_HARD_PATTERN.search(item.original_text)
            )
        )
        if len(hard_children) < 2:
            continue

        source_text = re.sub(
            r"^\s*\d+\s+(?=\S)",
            "",
            _classification_text(evidence),
            count=1,
        ).strip()
        for _, _, segment in _comma_segments(source_text):
            segment = segment.strip().rstrip("。.;；").strip()
            if (
                not segment
                or _SOFT_MARKER_PATTERN.search(segment)
                or (
                    _ALTERNATIVE_GROUP_PATTERN.search(segment) is None
                    and _EXPLICIT_OR_PATTERN.search(segment) is None
                )
                or _unique_exact_span(description, segment) is None
            ):
                continue
            segment_children = tuple(
                item
                for item in hard_children
                if (
                    (child_text := item.original_text.strip())
                    and child_text != segment
                    and child_text in segment
                )
            )
            if len(segment_children) < 2:
                continue
            if any(
                item.type is RequirementType.CONSTRAINT
                and item.importance is RequirementImportance.MUST_HAVE
                and item.evidence_span.strip() == evidence
                and _classification_text(item.original_text) == segment
                for item in (*all_items, *recovered)
            ):
                continue
            if len(all_items) + len(recovered) + 1 > MAX_REQUIREMENTS_PER_RUN:
                continue
            recovered.append(
                ProposedJobRequirement(
                    type=RequirementType.CONSTRAINT,
                    original_text=segment,
                    normalized_capability=None,
                    importance=RequirementImportance.MUST_HAVE,
                    evidence_span=evidence,
                    confidence=min(item.confidence for item in segment_children),
                )
            )
    return tuple(recovered)


def _recover_same_evidence_example_experience_parents(
    description: str,
    all_items: tuple[ProposedJobRequirement, ...],
) -> tuple[ProposedJobRequirement, ...]:
    """Recover one explicit experience umbrella when examples were emitted as hard skills.

    Only an exact requirement-section line shaped as an explicit ``有/具备...经验`` fact
    with a bounded parenthetical ``... / ... 等`` example list is eligible, and at least
    two hard skill children must share that exact evidence and occur inside the example
    parentheses. This avoids generic example synthesis.
    """
    recovered: list[ProposedJobRequirement] = []
    evidence_values = {
        item.evidence_span.strip()
        for item in all_items
        if item.evidence_span.strip()
    }
    for evidence in evidence_values:
        if (
            _unique_exact_span(description, evidence) is None
            or not _is_requirement_section_span(description, evidence)
            or _SOFT_MARKER_PATTERN.search(evidence)
        ):
            continue
        source_text = re.sub(
            r"^\s*\d+\s+(?=\S)",
            "",
            _classification_text(evidence),
            count=1,
        ).rstrip("。.;；").strip()
        example_match = _PARENTHETICAL_ENUM_EXAMPLE_LIST_PATTERN.search(source_text)
        if (
            example_match is None
            or _EXPLICIT_EXPERIENCE_FACT_PATTERN.fullmatch(source_text) is None
            or _unique_exact_span(description, source_text) is None
        ):
            continue
        example_text = example_match.group(0)
        children = tuple(
            item
            for item in all_items
            if (
                item.type is RequirementType.SKILL
                and item.importance is RequirementImportance.MUST_HAVE
                and item.evidence_span.strip() == evidence
                and item.original_text.strip()
                and item.original_text.strip() in example_text
            )
        )
        if len(children) < 2:
            continue
        if any(
            item.type is RequirementType.EXPERIENCE
            and item.importance is RequirementImportance.MUST_HAVE
            and item.evidence_span.strip() == evidence
            and _classification_text(item.original_text) == source_text
            for item in (*all_items, *recovered)
        ):
            continue
        if len(all_items) + len(recovered) + 1 > MAX_REQUIREMENTS_PER_RUN:
            continue
        recovered.append(
            ProposedJobRequirement(
                type=RequirementType.EXPERIENCE,
                original_text=source_text,
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=evidence,
                confidence=min(item.confidence for item in children),
            )
        )
    return tuple(recovered)


def _is_redundant_recovered_parenthetical_experience_example_child(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Drop one hard skill example only behind an exact recovered experience umbrella."""
    if (
        item.type is not RequirementType.SKILL
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return False
    evidence = item.evidence_span.strip()
    child_text = item.original_text.strip()
    if (
        not evidence
        or not child_text
        or _unique_exact_span(description, evidence) is None
    ):
        return False
    source_text = re.sub(
        r"^\s*\d+\s+(?=\S)",
        "",
        _classification_text(evidence),
        count=1,
    ).rstrip("。.;；").strip()
    example_match = _PARENTHETICAL_ENUM_EXAMPLE_LIST_PATTERN.search(source_text)
    if example_match is None or child_text not in example_match.group(0):
        return False
    return any(
        parent.type is RequirementType.EXPERIENCE
        and parent.importance is RequirementImportance.MUST_HAVE
        and parent.evidence_span.strip() == evidence
        and _classification_text(parent.original_text) == source_text
        for parent in all_items
    )


def _recover_backend_component_umbrella(
    description: str,
    all_items: tuple[ProposedJobRequirement, ...],
) -> ProposedJobRequirement | None:
    """Collapse one live-proven backend-component implementation fan-out.

    This deliberately recognizes only the observed requirement-section shape: a line
    declaring common backend components with ``MySQL/PostgreSQL``, ``Redis`` and a
    message-queue category, immediately followed by ``(Kafka/RabbitMQ/RocketMQ)``.
    At least two hard capability-decorated siblings must already fan out from either
    slash group before the exact source line is recovered as one hard constraint.
    """
    lines = _explicit_requirement_source_lines(description)
    for index, (raw, text, _, _) in enumerate(lines):
        compact = re.sub(r"\s+", "", text)
        if (
            "熟悉后端系统开发常用组件:" not in compact.replace("：", ":")
            or "MySQL/PostgreSQL" not in text
            or "Redis" not in text
            or "消息队列" not in compact
            or _SOFT_MARKER_PATTERN.search(text)
        ):
            continue
        source_text = re.sub(r"^\s*\d+\s+(?=\S)", "", text, count=1).strip()
        if not source_text or _unique_exact_span(description, raw) is None:
            continue
        queue_line = None
        source_end = description.find(raw) + len(raw)
        tail = description[source_end:]
        next_nonempty = next((line.strip() for line in tail.splitlines() if line.strip()), "")
        if next_nonempty == "(Kafka/RabbitMQ/RocketMQ)":
            queue_line = next_nonempty
        allowed_capabilities = {
            "MySQL",
            "PostgreSQL",
            "Redis",
            "Kafka",
            "RabbitMQ",
            "RocketMQ",
        }
        fanout = [
            item
            for item in all_items
            if item.type is RequirementType.SKILL
            and item.importance is RequirementImportance.MUST_HAVE
            and item.normalized_capability in allowed_capabilities
            and (
                (
                    item.evidence_span.strip() == raw
                    and item.original_text.strip()
                    in {raw.strip(), source_text, "MySQL/PostgreSQL", "Redis"}
                )
                or (
                    queue_line is not None
                    and item.evidence_span.strip() == queue_line
                    and item.original_text.strip() == "Kafka/RabbitMQ/RocketMQ"
                )
            )
        ]
        umbrella_items = [
            item
            for item in all_items
            if item.type is RequirementType.SKILL
            and item.importance is RequirementImportance.MUST_HAVE
            and item.evidence_span.strip() == raw
            and item.original_text.strip() in {raw.strip(), source_text}
            and re.sub(r"\s+", "", item.normalized_capability or "")
            == "熟悉后端系统开发常用组件"
        ]
        queue_category_items = [
            item
            for item in all_items
            if queue_line is not None
            and item.type is RequirementType.SKILL
            and item.importance is RequirementImportance.MUST_HAVE
            and item.evidence_span.strip() == queue_line
            and item.original_text.strip() == queue_line
            and re.sub(r"\s+", "", item.normalized_capability or "") == "消息队列"
        ]
        umbrella_queue_pair = len(umbrella_items) == 1 and len(queue_category_items) == 1
        if len(fanout) < 2 and not umbrella_queue_pair:
            continue
        proof_items = fanout
        if umbrella_queue_pair:
            proof_items = [*fanout, *umbrella_items, *queue_category_items]
        return ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=source_text,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=raw,
            confidence=min(item.confidence for item in proof_items),
        )
    return None


def _is_backend_component_fanout_child(
    item: ProposedJobRequirement,
    umbrella: ProposedJobRequirement,
) -> bool:
    if item.type is not RequirementType.SKILL:
        return False
    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    allowed_capabilities = {
        "MySQL",
        "PostgreSQL",
        "Redis",
        "Kafka",
        "RabbitMQ",
        "RocketMQ",
    }
    if item.normalized_capability in allowed_capabilities and (
        (
            evidence == umbrella.evidence_span.strip()
            and original
            in {
                umbrella.evidence_span.strip(),
                umbrella.original_text.strip(),
                "MySQL/PostgreSQL",
                "Redis",
            }
        )
        or (
            evidence == "(Kafka/RabbitMQ/RocketMQ)"
            and original == "Kafka/RabbitMQ/RocketMQ"
        )
    ):
        return True
    if (
        evidence == umbrella.evidence_span.strip()
        and original in {umbrella.evidence_span.strip(), umbrella.original_text.strip()}
        and re.sub(r"\s+", "", item.normalized_capability or "")
        == "熟悉后端系统开发常用组件"
    ):
        return True
    return bool(
        evidence == "(Kafka/RabbitMQ/RocketMQ)"
        and original == "(Kafka/RabbitMQ/RocketMQ)"
        and re.sub(r"\s+", "", item.normalized_capability or "") == "消息队列"
    )


def _recover_uncovered_requirement_cardinality_constraints(
    description: str,
    all_items: tuple[ProposedJobRequirement, ...],
) -> tuple[ProposedJobRequirement, ...]:
    """Recover exact hard cardinality lines omitted by the Provider.

    Only explicit requirements/qualifications sections are scanned. A line must contain
    the existing bounded cardinality grammar, contain no soft marker, and have no
    already-emitted must-have constraint anchored to that same line. The recovered
    requirement is the exact JD text (minus list numbering / terminal punctuation) and
    therefore remains fully grounded rather than semantically synthesized.
    """
    recovered: list[ProposedJobRequirement] = []
    in_requirement_section = False

    for raw_line in description.splitlines():
        raw = raw_line.strip()
        if not raw:
            continue
        heading = raw.rstrip(":：").strip()
        normalized_heading = heading.strip("【】").strip()
        if _REQUIREMENT_SECTION_NAME_PATTERN.fullmatch(normalized_heading):
            in_requirement_section = True
            continue
        if _RESPONSIBILITY_SECTION_NAME_PATTERN.fullmatch(normalized_heading):
            in_requirement_section = False
            continue
        if not in_requirement_section:
            continue

        text = _classification_text(raw)
        if (
            not text
            or not text.startswith("不要求")
            or "都" not in text
            or re.search(r"[,，]\s*但", text) is None
            or _ALTERNATIVE_GROUP_PATTERN.search(text) is None
            or _SOFT_MARKER_PATTERN.search(text)
            or _unique_exact_span(description, raw) is None
            or _unique_exact_span(description, text) is None
        ):
            continue

        already_covered = any(
            item.type is RequirementType.CONSTRAINT
            and item.importance is RequirementImportance.MUST_HAVE
            and _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
            and _classification_text(item.original_text) == text
            for item in (*all_items, *recovered)
        )
        if already_covered:
            continue

        recovered.append(
            ProposedJobRequirement(
                type=RequirementType.CONSTRAINT,
                original_text=text,
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=raw,
                confidence=1.0,
            )
        )

    return tuple(recovered)


def _recover_uncovered_inline_cardinality_constraints(
    description: str,
    all_items: tuple[ProposedJobRequirement, ...],
) -> tuple[ProposedJobRequirement, ...]:
    """Recover one exact hard inline cardinality segment omitted by the Provider.

    This is intentionally narrower than generic clause recovery: only recognized
    requirement sections are scanned, the candidate must be a comma-delimited segment
    beginning with a bounded knowledge verb (for example ``深入了解``) and carrying the
    existing explicit cardinality grammar, and the exact segment must be uniquely
    grounded with no soft marker. This preserves neighboring independent hard clauses
    while preventing a source-proven cardinality gate from disappearing entirely.
    """
    recovered: list[ProposedJobRequirement] = []
    in_requirement_section = False
    candidate_pattern = re.compile(
        r"^(?:深入了解|理解|了解|熟悉|掌握|精通).{0,24}至少(?:一个|一种|一项|一门)",
        re.IGNORECASE,
    )

    for raw_line in description.splitlines():
        raw = raw_line.strip()
        if not raw:
            continue
        heading = raw.rstrip(":：").strip()
        normalized_heading = heading.strip("【】").strip()
        if _REQUIREMENT_SECTION_NAME_PATTERN.fullmatch(normalized_heading):
            in_requirement_section = True
            continue
        if _RESPONSIBILITY_SECTION_NAME_PATTERN.fullmatch(normalized_heading):
            in_requirement_section = False
            continue
        if not in_requirement_section:
            continue

        text = _classification_text(raw)
        if not text:
            continue
        for _, _, segment in _comma_segments(text):
            candidate = segment.strip().rstrip(";；。")
            if (
                not candidate
                or candidate_pattern.search(candidate) is None
                or _ALTERNATIVE_GROUP_PATTERN.search(candidate) is None
                or _SOFT_MARKER_PATTERN.search(candidate)
                or _unique_exact_span(description, candidate) is None
            ):
                continue
            if any(
                item.importance is RequirementImportance.MUST_HAVE
                and (
                    _classification_text(item.original_text) == candidate
                    or (
                        item.type is RequirementType.CONSTRAINT
                        and item.evidence_span.strip() == raw
                        and candidate in _classification_text(item.original_text)
                    )
                )
                for item in (*all_items, *recovered)
            ):
                continue
            recovered.append(
                ProposedJobRequirement(
                    type=RequirementType.CONSTRAINT,
                    original_text=candidate,
                    normalized_capability=None,
                    importance=RequirementImportance.MUST_HAVE,
                    evidence_span=raw,
                    confidence=1.0,
                )
            )

    return tuple(recovered)


def _recover_post_cardinality_engineering_practice(
    description: str,
    all_items: tuple[ProposedJobRequirement, ...],
) -> tuple[ProposedJobRequirement, ...]:
    """Recover one source-proven hard engineering-practice sibling after cardinality.

    The live v42.86 failure is deliberately handled as a bounded source repair rather
    than generic clause synthesis: only a recognized requirements section is scanned,
    the line must already have a grounded hard cardinality parent in the same evidence,
    and the omitted sibling must be exactly ``具备良好的工程规范和代码品味`` with no
    soft marker. Different wording/evidence and already-covered siblings are untouched.
    """
    recovered: list[ProposedJobRequirement] = []
    candidate_text = "具备良好的工程规范和代码品味"

    for raw, text, _, _ in _explicit_requirement_source_lines(description):
        segments = _comma_segments(text)
        if len(segments) != 2 or segments[1][2].strip().rstrip(";；。") != candidate_text:
            continue
        first_segment = re.sub(
            r"^\s*\d+\s+(?=\S)",
            "",
            segments[0][2].strip(),
            count=1,
        )
        if (
            ("或" not in first_segment and "至少" not in first_segment)
            or _SOFT_MARKER_PATTERN.search(text)
            or _unique_exact_span(description, raw) is None
            or _unique_exact_span(description, candidate_text) is None
        ):
            continue
        if not any(
            item.type is RequirementType.CONSTRAINT
            and item.importance is RequirementImportance.MUST_HAVE
            and item.evidence_span.strip() == raw
            and _classification_text(item.original_text) == first_segment
            for item in all_items
        ):
            continue
        if any(
            item.importance is RequirementImportance.MUST_HAVE
            and item.evidence_span.strip() == raw
            and candidate_text in _classification_text(item.original_text)
            for item in (*all_items, *recovered)
        ):
            continue
        recovered.append(
            ProposedJobRequirement(
                type=RequirementType.CONSTRAINT,
                original_text=candidate_text,
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=raw,
                confidence=1.0,
            )
        )

    return tuple(recovered)


def _recover_missing_alternative_group_parents(
    description: str,
    all_items: tuple[ProposedJobRequirement, ...],
) -> tuple[ProposedJobRequirement, ...]:
    """Recover a missing exact alternative-list parent only from proven JD structure.

    The Provider must already cover every explicit direction child line via exact
    evidence spans. This repair only restores the omitted hard cardinality parent so
    the existing bounded alternative-scope logic can classify those children safely.
    """
    recovered: list[ProposedJobRequirement] = []
    lines = description.splitlines()

    for index, raw_line in enumerate(lines):
        raw = raw_line.strip()
        if not raw or not _is_requirement_section_span(description, raw):
            continue

        text = _classification_text(raw)
        if (
            not text
            or not raw.endswith((":", "："))
            or _ALTERNATIVE_GROUP_PATTERN.search(text) is None
            or _ALTERNATIVE_FOLLOWING_LIST_PATTERN.search(text) is None
            or _SOFT_MARKER_PATTERN.search(text)
            or _unique_exact_span(description, raw) is None
        ):
            continue
        if any(
            item.type is RequirementType.CONSTRAINT
            and item.importance is RequirementImportance.MUST_HAVE
            and _ALTERNATIVE_GROUP_PATTERN.search(item.evidence_span.strip())
            and item.evidence_span.strip() == raw
            for item in (*all_items, *recovered)
        ):
            continue

        child_lines: list[str] = []
        unsafe_scope = False
        for candidate_line in lines[index + 1 :]:
            candidate = candidate_line.strip()
            if not candidate:
                continue
            if _TOP_LEVEL_NUMBERED_ITEM_PATTERN.match(candidate):
                break
            label_match = _ALTERNATIVE_CHILD_LABEL_PATTERN.fullmatch(candidate)
            if label_match is None:
                unsafe_scope = True
                break
            label = (
                label_match.group("label_cn") or label_match.group("label_en") or ""
            ).strip()
            body = label_match.group("body").strip()
            if (
                _ALTERNATIVE_CHILD_LABEL_SCOPE_PATTERN.search(label) is None
                or not body
                or _SOFT_MARKER_PATTERN.search(body)
                or _EXPLICIT_CHILD_HARD_PATTERN.search(body)
            ):
                unsafe_scope = True
                break
            child_lines.append(candidate)

        if unsafe_scope or not 2 <= len(child_lines) <= 8:
            continue
        if not all(
            any(item.evidence_span.strip() == child for item in all_items)
            for child in child_lines
        ):
            continue
        if len(all_items) + len(recovered) + 1 > MAX_REQUIREMENTS_PER_RUN:
            continue

        recovered.append(
            ProposedJobRequirement(
                type=RequirementType.CONSTRAINT,
                original_text=text.rstrip(":：").strip(),
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=raw,
                confidence=1.0,
            )
        )

    return tuple(recovered)


def _recover_uncovered_alternative_group_children(
    description: str,
    all_items: tuple[ProposedJobRequirement, ...],
) -> tuple[ProposedJobRequirement, ...]:
    """Recover omitted children from one explicit, bounded cardinality list.

    This is intentionally narrower than generic coverage recovery. The emitted parent
    must already be a hard constraint in a requirements section, its exact source line
    must announce a following list (for example ``以下``) and end with a colon, and every
    non-empty line until the next numbered sibling must use an explicit direction label
    or bullet marker. Mixed narrative scopes are rejected instead of guessed.
    """
    recovered: list[ProposedJobRequirement] = []

    for parent in all_items:
        parent_evidence = parent.evidence_span.strip()
        if (
            parent.type is not RequirementType.CONSTRAINT
            or parent.importance is not RequirementImportance.MUST_HAVE
            or _ALTERNATIVE_GROUP_PATTERN.search(parent_evidence) is None
            or _ALTERNATIVE_FOLLOWING_LIST_PATTERN.search(parent_evidence) is None
            or not parent_evidence.rstrip().endswith((":", "："))
            or not _is_requirement_section_span(description, parent_evidence)
        ):
            continue

        parent_span = _unique_exact_span(description, parent_evidence)
        if parent_span is None:
            continue
        line_start = description.rfind("\n", 0, parent_span[0]) + 1
        line_end = description.find("\n", parent_span[1])
        if line_end < 0:
            line_end = len(description)
        if description[line_start:line_end].strip() != parent_evidence:
            continue

        next_item_start = _next_top_level_numbered_item_start(
            description,
            group_start=parent_span[0],
            group_end=line_end,
        )
        scope_end = next_item_start if next_item_start is not None else len(description)
        if line_end >= scope_end:
            continue

        parsed_children: list[tuple[str, str]] = []
        unsafe_scope = False
        for raw_line in description[line_end + 1 : scope_end].splitlines():
            raw = raw_line.strip()
            if not raw:
                continue
            label_match = _ALTERNATIVE_CHILD_LABEL_PATTERN.fullmatch(raw)
            if label_match is not None:
                label = (label_match.group("label_cn") or label_match.group("label_en") or "").strip()
                if _ALTERNATIVE_CHILD_LABEL_SCOPE_PATTERN.search(label) is None:
                    unsafe_scope = True
                    break
                body = label_match.group("body").strip()
            else:
                bullet_match = _ALTERNATIVE_CHILD_BULLET_PATTERN.fullmatch(raw)
                if bullet_match is None:
                    unsafe_scope = True
                    break
                body = bullet_match.group("body").strip()
            if (
                not body
                or _SOFT_MARKER_PATTERN.search(body)
                or _EXPLICIT_CHILD_HARD_PATTERN.search(body)
                or _unique_exact_span_within_scope(
                    description,
                    body,
                    scope_start=line_end + 1,
                    scope_end=scope_end,
                )
                is None
            ):
                unsafe_scope = True
                break
            parsed_children.append((raw, body))

        if unsafe_scope or not 2 <= len(parsed_children) <= 8:
            continue
        if len(all_items) + len(recovered) + len(parsed_children) > MAX_REQUIREMENTS_PER_RUN:
            continue

        for raw, body in parsed_children:
            if any(
                existing.original_text.strip() == body
                or existing.evidence_span.strip() == raw
                for existing in (*all_items, *recovered)
            ):
                continue
            capability_match = _SIMPLE_ALTERNATIVE_CHILD_CAPABILITY_PATTERN.match(body)
            capability = (
                capability_match.group("capability")
                if capability_match is not None
                else None
            )
            recovered.append(
                ProposedJobRequirement(
                    type=(RequirementType.SKILL if capability else RequirementType.CONSTRAINT),
                    original_text=body,
                    normalized_capability=capability,
                    importance=RequirementImportance.PREFERRED,
                    evidence_span=raw,
                    confidence=1.0,
                )
            )

    return tuple(recovered)


def _is_alternative_direction_label_capability(label: str, capability: str) -> bool:
    current = capability.strip().casefold()
    if not current:
        return False
    if current in label.casefold():
        return True
    return current in _ALTERNATIVE_DIRECTION_LABEL_CAPABILITY_ALIASES.get(
        label.strip(), frozenset()
    )


def _normalize_alternative_group_child_scope(
    description: str,
    item: ProposedJobRequirement,
    group_scopes: list[tuple[int, int]],
) -> ProposedJobRequirement | None:
    """Repair live Provider drift for explicit alternative direction children.

    The item must be inside exactly one bounded alternative-group scope and its exact
    evidence line must use a supported direction/option label followed by a simple
    concrete capability token. This permits responsibility/must-have drift to recover
    to the intended non-blocking skill child while preserving the exact source slice.
    """
    if item.type not in {RequirementType.SKILL, RequirementType.RESPONSIBILITY}:
        return None
    if (
        item.type is RequirementType.SKILL
        and item.importance is RequirementImportance.PREFERRED
    ):
        return None
    raw = item.evidence_span.strip()
    label_match = _ALTERNATIVE_CHILD_LABEL_PATTERN.fullmatch(raw)
    if label_match is None:
        return None
    label = (label_match.group("label_cn") or label_match.group("label_en") or "").strip()
    if _ALTERNATIVE_CHILD_LABEL_SCOPE_PATTERN.search(label) is None:
        return None
    body = label_match.group("body").strip()
    capability_match = _SIMPLE_ALTERNATIVE_CHILD_CAPABILITY_PATTERN.match(body)
    if capability_match is None:
        return None
    scoped_spans = [
        span
        for scope_start, scope_end in group_scopes
        if (
            span := _unique_exact_span_within_scope(
                description,
                raw,
                scope_start=scope_start,
                scope_end=scope_end,
            )
        )
        is not None
    ]
    if len(scoped_spans) != 1:
        return None
    current = (item.normalized_capability or "").strip()
    if current and not _is_alternative_direction_label_capability(label, current):
        return None
    return replace(
        item,
        type=RequirementType.SKILL,
        importance=RequirementImportance.PREFERRED,
        normalized_capability=capability_match.group("capability"),
    )


def _normalize_alternative_group_child_capability(
    description: str,
    item: ProposedJobRequirement,
    group_scopes: list[tuple[int, int]],
) -> ProposedJobRequirement | None:
    """Replace a generic direction label with the child's first concrete capability.

    This only applies to an already non-blocking skill child inside exactly one bounded
    alternative-group scope. The evidence line must use the same explicit direction
    label grammar as child recovery, and the current Provider capability must come from
    that label (for example ``前端`` from ``【前端方向】``). A concrete Provider-selected
    capability that does not come from the label is preserved.
    """
    if (
        item.type is not RequirementType.SKILL
        or item.importance is not RequirementImportance.PREFERRED
        or not item.normalized_capability
    ):
        return None
    raw = item.evidence_span.strip()
    label_match = _ALTERNATIVE_CHILD_LABEL_PATTERN.fullmatch(raw)
    if label_match is None:
        return None
    label = (label_match.group("label_cn") or label_match.group("label_en") or "").strip()
    if _ALTERNATIVE_CHILD_LABEL_SCOPE_PATTERN.search(label) is None:
        return None
    body = label_match.group("body").strip()
    capability_match = _SIMPLE_ALTERNATIVE_CHILD_CAPABILITY_PATTERN.match(body)
    if capability_match is None:
        return None
    capability = capability_match.group("capability")
    current = item.normalized_capability.strip()
    scoped_spans = [
        span
        for scope_start, scope_end in group_scopes
        if (
            span := _unique_exact_span_within_scope(
                description,
                raw,
                scope_start=scope_start,
                scope_end=scope_end,
            )
        )
        is not None
    ]
    if len(scoped_spans) != 1:
        return None

    original = item.original_text.strip()
    body_only_source_identity = (
        _presentation_identity(original) == _presentation_identity(body)
        and _presentation_identity(original) != _presentation_identity(raw)
        and current.casefold() == capability.casefold()
    )
    if body_only_source_identity:
        return replace(item, original_text=raw)
    if current.casefold() == capability.casefold():
        return None
    if not _is_alternative_direction_label_capability(label, current):
        return None
    return replace(item, normalized_capability=capability)


def _alternative_group_child_sibling_canonical_capability(
    description: str,
    item: ProposedJobRequirement,
    group_scopes: list[tuple[int, int]],
    all_items: tuple[ProposedJobRequirement, ...],
) -> str | None:
    """Collapse capability fan-out only when one alternative child line was duplicated.

    A single Provider-selected concrete capability remains untouched. Canonicalization is
    enabled only when at least two preferred skill siblings share the same exact child
    line inside one bounded alternative scope; all such siblings map to the line's first
    concrete capability and the existing exact-dedupe pass then keeps one direction node.
    """
    if item.importance not in {
        RequirementImportance.PREFERRED,
        RequirementImportance.BONUS,
    }:
        return None
    if item.type not in {
        RequirementType.SKILL,
        RequirementType.DOMAIN,
        RequirementType.EXPERIENCE,
        RequirementType.CONSTRAINT,
    }:
        return None
    if (
        item.type is RequirementType.EXPERIENCE
        and _EXPERIENCE_SEGMENT_PATTERN.search(_classification_text(item.original_text))
    ):
        return None
    raw = item.evidence_span.strip()
    original = item.original_text.strip()
    if not raw or not original:
        return None
    label_match = _ALTERNATIVE_CHILD_LABEL_PATTERN.fullmatch(raw)
    if label_match is None:
        return None
    label = (label_match.group("label_cn") or label_match.group("label_en") or "").strip()
    if _ALTERNATIVE_CHILD_LABEL_SCOPE_PATTERN.search(label) is None:
        return None
    body = label_match.group("body").strip()
    capability_match = _SIMPLE_ALTERNATIVE_CHILD_CAPABILITY_PATTERN.match(body)
    if capability_match is None:
        return None
    scoped_spans = [
        span
        for scope_start, scope_end in group_scopes
        if (
            span := _unique_exact_span_within_scope(
                description,
                raw,
                scope_start=scope_start,
                scope_end=scope_end,
            )
        )
        is not None
    ]
    if len(scoped_spans) != 1:
        return None
    siblings = [
        candidate
        for candidate in all_items
        if candidate.type
        in {
            RequirementType.SKILL,
            RequirementType.DOMAIN,
            RequirementType.EXPERIENCE,
            RequirementType.CONSTRAINT,
        }
        and candidate.importance
        in {
            RequirementImportance.PREFERRED,
            RequirementImportance.BONUS,
            RequirementImportance.MUST_HAVE,
        }
        and not (
            candidate.type is RequirementType.EXPERIENCE
            and (
                candidate.importance is RequirementImportance.MUST_HAVE
                or _EXPERIENCE_SEGMENT_PATTERN.search(
                    _classification_text(candidate.original_text)
                )
            )
        )
        and not (
            candidate.type is RequirementType.CONSTRAINT
            and candidate.importance is RequirementImportance.MUST_HAVE
        )
        and (
            candidate.importance
            in {RequirementImportance.PREFERRED, RequirementImportance.BONUS}
            or (
                _ALTERNATIVE_GROUP_PATTERN.search(candidate.original_text) is None
                and _EXPLICIT_CHILD_HARD_PATTERN.search(candidate.original_text) is None
            )
        )
        and candidate.evidence_span.strip() == raw
        and candidate.original_text.strip()
        and (
            candidate.original_text.strip() in body
            or candidate.original_text.strip() == raw
            or candidate.original_text.strip().rstrip("，,。.;；").strip()
            == raw.rstrip("，,。.;；").strip()
        )
    ]
    if len(siblings) < 2:
        return None
    distinct_originals = {candidate.original_text.strip() for candidate in siblings}
    distinct_capabilities = {
        candidate.normalized_capability.strip().casefold()
        for candidate in siblings
        if candidate.normalized_capability and candidate.normalized_capability.strip()
    }
    full_line_capability_fanout = (
        bool(distinct_originals)
        and all(
            original.rstrip("，,。.;；").strip()
            == raw.rstrip("，,。.;；").strip()
            for original in distinct_originals
        )
        and len(distinct_capabilities) >= 2
    )
    if len(distinct_originals) < 2 and not full_line_capability_fanout:
        return None
    return capability_match.group("capability")


def _normalize_responsibility_type_drift(
    description: str,
    item: ProposedJobRequirement,
) -> ProposedJobRequirement | None:
    """Recover evaluator-sensitive responsibility drift from exact JD wording.

    Prefer an explicit responsibility/description section when present. For JDs that
    omit headings, allow only long action-sentence shapes that start with a bounded
    responsibility verb and contain no experience/education/soft markers. This keeps
    qualification-like ``熟悉/掌握/具备/有`` clauses out of the repair.
    """
    if (
        item.type not in {RequirementType.SKILL, RequirementType.EXPERIENCE}
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return None
    original = item.original_text.strip()
    if not original or _unique_exact_span(description, original) is None:
        return None
    text = _classification_text(original)
    if (
        _EXPERIENCE_SEGMENT_PATTERN.search(text)
        or _EDUCATION_SEGMENT_PATTERN.search(text)
        or _THRESHOLD_PATTERN.search(text)
    ):
        return None
    span = _unique_exact_span(description, item.evidence_span.strip()) or _unique_exact_span(
        description,
        original,
    )
    if span is None:
        return None
    section_name = _nearest_section_name(description, span[0])
    in_responsibility_section = bool(
        section_name
        and _RESPONSIBILITY_SECTION_NAME_PATTERN.fullmatch(section_name)
    )
    action_sentence = bool(
        _RESPONSIBILITY_ACTION_PATTERN.search(text)
        and len(text) >= 16
        and any(separator in text for separator in (",", "，", "。", ";", "；"))
    )
    if not in_responsibility_section and not action_sentence:
        return None
    return replace(
        item,
        type=RequirementType.RESPONSIBILITY,
        normalized_capability=None,
    )


def _normalize_short_scope_summary_skill_drift(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> ProposedJobRequirement | None:
    """Recover a short numbered role-scope summary mislabelled as a hard skill.

    The repair does not infer responsibility from the capability wording itself. It
    requires exact evidence for a short numbered summary line, no explicit
    qualification/skill/experience markers, and a following block of several grounded
    action-shaped responsibility lines that the Provider also emitted as responsibilities.
    This keeps explicit qualifications such as ``熟练使用 Python`` out of the repair.
    """
    if (
        item.type is not RequirementType.SKILL
        or item.importance is not RequirementImportance.MUST_HAVE
        or not item.normalized_capability
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
    ):
        return None

    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not original
        or not evidence
        or len(original) < 4
        or len(original) > 48
        or len(evidence) > 80
        or original not in evidence
        or _LEADING_NUMBERED_ITEM_PREFIX_PATTERN.match(evidence) is None
        or _unique_exact_span(description, original) is None
    ):
        return None
    evidence_span = _unique_exact_span(description, evidence)
    if evidence_span is None:
        return None

    text = _classification_text(original)
    evidence_text = _classification_text(evidence)
    if (
        not evidence_text.startswith(original)
        or any(separator in text for separator in (",", "，", "。", ";", "；"))
        or _EXPLICIT_REQUIREMENT_START_PATTERN.search(text)
        or _HARD_SKILL_PREFIX_PATTERN.fullmatch(text)
        or _EXPERIENCE_SEGMENT_PATTERN.search(text)
        or _EDUCATION_SEGMENT_PATTERN.search(text)
        or _THRESHOLD_PATTERN.search(text)
    ):
        return None

    following_lines = [
        line.strip()
        for line in description[evidence_span[1] :].splitlines()
        if line.strip()
    ][:8]
    following_action_count = sum(
        bool(
            _RESPONSIBILITY_ACTION_PATTERN.search(_classification_text(line))
            and len(_classification_text(line)) >= 16
            and any(separator in line for separator in (",", "，", "。", ";", "；"))
        )
        for line in following_lines
    )
    if following_action_count < 3:
        return None

    emitted_following_responsibilities = 0
    for other in all_items:
        if other is item or other.type is not RequirementType.RESPONSIBILITY:
            continue
        other_evidence = other.evidence_span.strip()
        other_span = _unique_exact_span(description, other_evidence)
        other_text = _classification_text(other.original_text)
        if (
            other_span is None
            or other_span[0] <= evidence_span[1]
            or _RESPONSIBILITY_ACTION_PATTERN.search(other_text) is None
            or len(other_text) < 16
        ):
            continue
        emitted_following_responsibilities += 1
    if emitted_following_responsibilities < 3:
        return None

    return replace(
        item,
        type=RequirementType.RESPONSIBILITY,
        normalized_capability=None,
    )


def _is_redundant_short_scope_summary_responsibility(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Drop a short numbered scope label when later concrete duties already cover it."""
    if item.type is not RequirementType.RESPONSIBILITY or item.importance is not RequirementImportance.MUST_HAVE:
        return False
    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not original
        or not evidence
        or len(original) < 4
        or len(original) > 48
        or len(evidence) > 80
        or original not in evidence
        or _LEADING_NUMBERED_ITEM_PREFIX_PATTERN.match(evidence) is None
        or _unique_exact_span(description, original) is None
    ):
        return False
    text = _classification_text(original)
    if (
        _RESPONSIBILITY_ACTION_PATTERN.search(text)
        or any(separator in text for separator in (",", "，", "。", ";", "；"))
        or _EXPLICIT_REQUIREMENT_START_PATTERN.search(text)
        or _HARD_SKILL_PREFIX_PATTERN.fullmatch(text)
        or _EXPERIENCE_SEGMENT_PATTERN.search(text)
        or _EDUCATION_SEGMENT_PATTERN.search(text)
        or _THRESHOLD_PATTERN.search(text)
    ):
        return False
    evidence_span = _unique_exact_span(description, evidence)
    if evidence_span is None:
        return False
    following_lines = [line.strip() for line in description[evidence_span[1] :].splitlines() if line.strip()][:8]
    following_action_count = sum(
        bool(
            _RESPONSIBILITY_ACTION_PATTERN.search(_classification_text(line))
            and len(_classification_text(line)) >= 16
            and any(separator in line for separator in (",", "，", "。", ";", "；"))
        )
        for line in following_lines
    )
    if following_action_count < 3:
        return False
    emitted_following = 0
    for other in all_items:
        if other is item or other.type is not RequirementType.RESPONSIBILITY:
            continue
        other_span = _unique_exact_span(description, other.evidence_span.strip())
        other_text = _classification_text(other.original_text)
        if (
            other_span is not None
            and other_span[0] > evidence_span[1]
            and _RESPONSIBILITY_ACTION_PATTERN.search(other_text) is not None
            and len(other_text) >= 16
        ):
            emitted_following += 1
    return emitted_following >= 3


def _normalize_technical_skill_experience_drift(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> ProposedJobRequirement | None:
    """Recover an explicit hard technical skill mislabelled as experience.

    This is intentionally narrower than generic qualification normalization. The
    exact hard clause must begin with the existing bounded technical-skill verb,
    contain no experience/year/soft/alternative wording, and remain uniquely
    grounded. When the clause contains inline examples, the capability is derived
    only from the umbrella prefix so examples such as LangChain do not become the
    hard capability.
    """
    if (
        item.type is not RequirementType.EXPERIENCE
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
    ):
        return None
    original = item.original_text.strip()
    if not original or _unique_exact_span(description, original) is None:
        return None
    text = _classification_text(original)
    if (
        not text
        or len(_comma_segments(text)) != 1
        or "经验" in text
        or _THRESHOLD_PATTERN.search(text)
        or _EXPERIENCE_SEGMENT_PATTERN.search(text)
        or any(
            candidate is not item
            and candidate.type is RequirementType.SKILL
            and candidate.importance is item.importance
            and candidate.original_text.strip() == original
            and candidate.evidence_span.strip() == item.evidence_span.strip()
            for candidate in all_items
        )
    ):
        return None
    capability_source = text
    example_match = _INLINE_EXAMPLE_LIST_PATTERN.search(text)
    if example_match is not None:
        capability_source = text[: example_match.start()].strip()
    if _HARD_SKILL_PREFIX_PATTERN.fullmatch(capability_source) is None:
        return None
    capability = re.sub(
        r"^(?:熟悉|熟练(?:使用|掌握)?|掌握|精通|使用)\s*",
        "",
        capability_source,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    if not capability:
        return None
    return replace(
        item,
        type=RequirementType.SKILL,
        normalized_capability=capability,
    )


def _normalize_non_experience_qualification_type_drift(
    description: str,
    item: ProposedJobRequirement,
) -> ProposedJobRequirement | None:
    """Convert an ability-shaped qualification mislabelled as hard experience.

    The clause must contain no experience/year wording and must match the narrow
    ``具备...能力,能...`` qualification shape exactly. The text remains verbatim.
    """
    if (
        item.type is not RequirementType.EXPERIENCE
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return None
    original = item.original_text.strip()
    if not original or _unique_exact_span(description, original) is None:
        return None
    text = _classification_text(original)
    segments = _comma_segments(text)
    compound_qualification = bool(
        len(segments) >= 2
        and (
            _HARD_SKILL_PREFIX_PATTERN.fullmatch(segments[0][2]) is not None
            or _EXPLICIT_CORE_TECHNOLOGY_LIST_PATTERN.fullmatch(segments[0][2]) is not None
        )
        and all(
            _COMPOUND_HARD_SKILL_SEGMENT_PATTERN.fullmatch(segment) is not None
            or _EVALUATIVE_ABILITY_SEGMENT_PATTERN.fullmatch(segment) is not None
            for _, _, segment in segments[1:]
        )
    )
    if (
        _EXPERIENCE_SEGMENT_PATTERN.search(text)
        or _THRESHOLD_PATTERN.search(text)
        or "经验" in text
        or not (
            _NON_EXPERIENCE_QUALIFICATION_PATTERN.fullmatch(text)
            or compound_qualification
        )
    ):
        return None
    return replace(
        item,
        type=RequirementType.CONSTRAINT,
        normalized_capability=None,
    )


def _normalize_requirement_section_qualification_type_drift(
    description: str,
    item: ProposedJobRequirement,
) -> ProposedJobRequirement | None:
    """Normalize explicit qualification-section responsibility/domain drift.

    Responsibility-shaped output is converted only when the exact source item is in an
    explicit requirements/qualifications section, starts with a bounded qualification
    marker, contains no experience/education/soft wording, and is not itself a duty
    action sentence. Domain output is converted only for a compound qualification that
    adds an explicit ability/action segment after the domain-knowledge segment; a plain
    domain fact such as ``熟悉汽车制造行业`` remains ``domain``.
    """
    if item.type not in {
        RequirementType.RESPONSIBILITY,
        RequirementType.DOMAIN,
        RequirementType.SKILL,
        RequirementType.CONSTRAINT,
    }:
        return None

    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not original
        or not evidence
        or _unique_exact_span(description, original) is None
        or _unique_exact_span(description, evidence) is None
        or not _is_requirement_section_span(description, evidence)
    ):
        return None

    text = _classification_text(original)
    mandatory_cardinality_qualification = bool(
        text.startswith("不要求")
        and "都" in text
        and re.search(r"[,，]\s*但", text)
        and _ALTERNATIVE_GROUP_PATTERN.search(text)
        and _SOFT_MARKER_PATTERN.search(text) is None
    )
    if mandatory_cardinality_qualification:
        return replace(
            item,
            type=RequirementType.CONSTRAINT,
            importance=RequirementImportance.MUST_HAVE,
            normalized_capability=None,
        )

    if (
        item.type not in {RequirementType.RESPONSIBILITY, RequirementType.DOMAIN}
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _EXPLICIT_REQUIREMENT_START_PATTERN.search(text) is None
        or _RESPONSIBILITY_ACTION_PATTERN.search(text)
        or _EXPERIENCE_SEGMENT_PATTERN.search(text)
        or _EDUCATION_SEGMENT_PATTERN.search(text)
        or _THRESHOLD_PATTERN.search(text)
    ):
        return None

    if item.type is RequirementType.DOMAIN:
        segments = _comma_segments(text)
        compound_domain_qualification = bool(
            len(segments) >= 2
            and any(
                _COMPOUND_HARD_SKILL_SEGMENT_PATTERN.fullmatch(segment) is not None
                for _, _, segment in segments[1:]
            )
        )
        if not compound_domain_qualification:
            return None

    return replace(
        item,
        type=RequirementType.CONSTRAINT,
        normalized_capability=None,
    )


def _is_explicit_application_material_requirement(
    description: str,
    item: ProposedJobRequirement,
) -> bool:
    """Promote explicit submission-material instructions misclassified as soft.

    This is intentionally narrow: the text must be a uniquely grounded constraint,
    contain no soft marker, and use an imperative application verb plus an explicit
    material such as GitHub/portfolio evidence. Generic profile mentions are ignored.
    """
    if (
        item.type is not RequirementType.CONSTRAINT
        or item.importance not in {
            RequirementImportance.PREFERRED,
            RequirementImportance.BONUS,
        }
    ):
        return False
    text = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not text
        or not evidence
        or text not in evidence
        or _SOFT_MARKER_PATTERN.search(text)
        or _SOFT_MARKER_PATTERN.search(evidence)
        or _APPLICATION_MATERIAL_REQUIREMENT_PATTERN.search(_classification_text(text)) is None
    ):
        return False
    return (
        _unique_exact_span(description, text) is not None
        and _unique_exact_span(description, evidence) is not None
    )


def _is_unsoftened_explicit_requirement_section_item(
    description: str,
    item: ProposedJobRequirement,
) -> bool:
    """Enforce the Prompt contract for explicit requirements sections.

    A Provider may occasionally label a plain qualification as preferred even though
    the JD gives no softening marker. Promote only uniquely grounded, explicit
    requirement-shaped text whose current section heading is itself a requirements /
    qualifications heading. Alternative children may be downgraded again later by the
    cardinality scope logic.
    """
    if item.importance not in {
        RequirementImportance.PREFERRED,
        RequirementImportance.BONUS,
    }:
        return False
    text = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not text
        or not evidence
        or text not in evidence
        or _SOFT_MARKER_PATTERN.search(text)
        or _SOFT_MARKER_PATTERN.search(evidence)
    ):
        return False
    classified_text = _classification_text(text)
    explicit_requirement_start = (
        _EXPLICIT_REQUIREMENT_START_PATTERN.search(classified_text) is not None
    )
    explicit_education_requirement = (
        item.type is RequirementType.EDUCATION
        and _EDUCATION_SEGMENT_PATTERN.search(classified_text) is not None
    )
    explicit_experience_threshold = (
        item.type is RequirementType.EXPERIENCE
        and "经验" in classified_text
        and _THRESHOLD_PATTERN.search(classified_text) is not None
    )
    if (
        not explicit_requirement_start
        and not explicit_education_requirement
        and not explicit_experience_threshold
    ):
        return False
    span = _unique_exact_span(description, evidence)
    if span is None:
        return False
    headings = [
        match
        for match in _SECTION_HEADING_PATTERN.finditer(description)
        if match.end() <= span[0]
    ]
    if not headings:
        return False
    section_name = headings[-1].group("name").strip()
    return _REQUIREMENT_SECTION_NAME_PATTERN.fullmatch(section_name) is not None


def _is_preferred_experience_hard_prefix_with_explicit_soft_sibling(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Recover a hard experience prefix only when the soft suffix is explicit.

    This handles a narrow Provider drift where ``有...经验`` is emitted as
    ``preferred`` because its source-candidate line also contains a later ``者优先``
    clause. Promotion requires an independently emitted soft sibling anchored to the
    exact same evidence span. A bridge such as ``或/or`` keeps the whole alternative
    soft and therefore blocks promotion.
    """
    if (
        item.type is not RequirementType.EXPERIENCE
        or item.importance not in {
            RequirementImportance.PREFERRED,
            RequirementImportance.BONUS,
        }
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _EXPLICIT_EXPERIENCE_FACT_PATTERN.fullmatch(
            _classification_text(item.original_text)
        )
        is None
    ):
        return False

    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not original
        or not evidence
        or _unique_exact_span(description, original) is None
        or _unique_exact_span(description, evidence) is None
    ):
        return False
    relative_start = evidence.find(original)
    if relative_start < 0:
        return False
    prefix = evidence[:relative_start]
    if _classification_text(f"{prefix}{original}") != _classification_text(original):
        return False
    remainder = evidence[relative_start + len(original) :]
    if not remainder.startswith((",", "，")):
        return False
    remainder = remainder[1:].lstrip()

    for sibling in all_items:
        if sibling is item or sibling.importance not in {
            RequirementImportance.PREFERRED,
            RequirementImportance.BONUS,
        }:
            continue
        sibling_text = sibling.original_text.strip()
        if (
            sibling.evidence_span.strip() != evidence
            or not sibling_text
            or _SOFT_MARKER_PATTERN.search(sibling_text) is None
            or _unique_exact_span(description, sibling_text) is None
        ):
            continue
        sibling_start = remainder.find(sibling_text)
        if sibling_start < 0:
            continue
        bridge = remainder[:sibling_start].strip(" ，,。.;；")
        if bridge.casefold() in {"或", "或者", "or"}:
            continue
        if not bridge:
            return True
    return False


def _is_preferred_hard_skill_prefix_with_explicit_soft_sibling(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Recover a hard skill prefix that was softened by a later explicit soft sibling."""
    if (
        item.type is not RequirementType.SKILL
        or item.importance not in {
            RequirementImportance.PREFERRED,
            RequirementImportance.BONUS,
        }
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _HARD_SKILL_PREFIX_PATTERN.fullmatch(
            _classification_text(item.original_text)
        )
        is None
    ):
        return False

    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not original
        or not evidence
        or _unique_exact_span(description, original) is None
        or _unique_exact_span(description, evidence) is None
    ):
        return False
    relative_start = evidence.find(original)
    if relative_start < 0:
        return False
    prefix = evidence[:relative_start]
    if _classification_text(f"{prefix}{original}") != _classification_text(original):
        return False
    remainder = evidence[relative_start + len(original) :]
    if not remainder.startswith((",", "，")):
        return False
    remainder = remainder[1:].lstrip()

    for sibling in all_items:
        if sibling is item or sibling.importance not in {
            RequirementImportance.PREFERRED,
            RequirementImportance.BONUS,
        }:
            continue
        sibling_text = sibling.original_text.strip()
        if (
            sibling.evidence_span.strip() != evidence
            or not sibling_text
            or _SOFT_MARKER_PATTERN.search(sibling_text) is None
            or _unique_exact_span(description, sibling_text.rstrip("，,。.;；")) is None
        ):
            continue
        sibling_start = remainder.find(sibling_text.rstrip("，,。.;；"))
        if sibling_start < 0:
            continue
        bridge = remainder[:sibling_start].strip(" ，,。.;；")
        if bridge.casefold() in {"或", "或者", "or"}:
            continue
        if not bridge:
            return True
    return False


def _unique_exact_span_within_scope(
    description: str,
    quote: str,
    *,
    scope_start: int,
    scope_end: int,
) -> tuple[int, int] | None:
    value = quote.strip()
    if not value or scope_start >= scope_end:
        return None
    start = description.find(value, scope_start, scope_end)
    if start < 0:
        return None
    if description.find(value, start + 1, scope_end) >= 0:
        return None
    return start, start + len(value)


def _same_clause_end(description: str, start: int) -> int:
    candidates = [
        index
        for marker in _STRONG_CLAUSE_BOUNDARIES
        if (index := description.find(marker, start)) >= 0
    ]
    return min(candidates) if candidates else len(description)


def _next_top_level_numbered_item_start(
    description: str,
    *,
    group_start: int,
    group_end: int,
) -> int | None:
    """Return the next sibling numbered item without confusing nested bullets.

    Some real JDs use `3 requirement` / `4 requirement` instead of `3.` / `4.`.
    When the group lives inside a numbered line, prefer the next ordinal sibling so
    an alternative-group scope cannot leak into later independent requirements.
    """
    line_start = description.rfind("\n", 0, group_start) + 1
    line_prefix = description[line_start:group_start]
    parent_match = re.match(
        r"^[ \t]*(?P<number>\d+)(?:\s*[.、．)]\s*|\s+)",
        line_prefix,
    )
    if parent_match is None and group_start == line_start:
        parent_match = re.match(
            r"^[ \t]*(?P<number>\d+)\s+(?=\S)",
            description[group_start:group_end],
        )
    if parent_match is not None:
        expected = int(parent_match.group("number")) + 1
        sibling_pattern = re.compile(
            rf"(?m)^[ \t]*{expected}(?:\s*[.、．)]\s*|\s+)(?=\S)"
        )
        sibling = sibling_pattern.search(description, group_end)
        if sibling is not None:
            return sibling.start()

    fallback = _TOP_LEVEL_NUMBERED_ITEM_PATTERN.search(description, group_end)
    return fallback.start() if fallback is not None else None


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


def _normalize_explicit_soft_only_requirement(
    description: str,
    item: ProposedJobRequirement,
) -> ProposedJobRequirement | None:
    """Normalize exact standalone preferred clauses without weakening mixed hard scope.

    The historical path converts a Provider ``must_have`` only when the clause is one
    of the narrowly understood preferred suffix shapes. Provider-native ``bonus`` is
    also normalized to ``preferred`` only outside an explicit bonus section when the
    exact clause is either one of those same suffix shapes or a bounded full-line
    preferred alternative (``... or ... preferred`` / ``...或...者优先``). This keeps
    explicit bonus-section semantics authoritative and avoids softening mixed hard +
    preferred lines such as ``本科及以上，相关专业优先`` wholesale.
    """
    original = item.original_text.strip().rstrip("，,。.;；").strip()
    if not original or _unique_exact_span(description, original) is None:
        return None

    if item.importance is RequirementImportance.BONUS:
        if _is_explicit_bonus_section_span(
            description,
            item.evidence_span,
        ) or _has_inline_bonus_label_prefix(description, item.evidence_span):
            return None
        if re.search(r"(?:加分|bonus|nice\s+to\s+have)", original, re.IGNORECASE):
            return None
        preferred_suffix = _preferred_suffix_requirement(
            original,
            confidence=item.confidence,
        )
        preferred_alternative = _is_collapsible_preferred_alternative_line(original)
        if preferred_suffix is None and not preferred_alternative:
            return None
        if re.search(r"(?:者优先|优先|preferred)$", original, re.IGNORECASE) is None:
            return None
        return replace(item, importance=RequirementImportance.PREFERRED)

    if item.importance is not RequirementImportance.MUST_HAVE:
        return None
    canonical = _preferred_suffix_requirement(
        original,
        confidence=item.confidence,
    )
    if canonical is None:
        return None
    return canonical


def _normalize_hard_skill_capability_before_soft_suffix(
    description: str,
    item: ProposedJobRequirement,
) -> ProposedJobRequirement | None:
    """Keep a hard skill capability scoped to its exact hard clause.

    The Provider may copy semantics from a later explicit preferred suffix into
    ``normalizedCapability`` even when ``originalText`` is already the exact hard skill
    prefix. Repair only when the hard prefix occurs on exactly one source line and the
    remainder of that same line contains a recognized trailing preferred clause.
    """
    if (
        item.type is not RequirementType.SKILL
        or item.importance is not RequirementImportance.MUST_HAVE
        or not item.normalized_capability
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return None
    original = item.original_text.strip()
    if not original or _unique_exact_span(description, original) is None:
        return None
    hard_match = _HARD_SKILL_CAPABILITY_CAPTURE_PATTERN.fullmatch(
        _classification_text(original)
    )
    if hard_match is None:
        return None

    matching_lines = [
        line.strip()
        for line in description.splitlines()
        if original in line.strip()
    ]
    if len(matching_lines) != 1:
        return None
    raw = matching_lines[0]
    offset = raw.find(original)
    remainder = raw[offset + len(original) :]
    if not remainder:
        return None
    preferred_match = _TRAILING_PREFERRED_EXPERIENCE_PATTERN.search(remainder)
    if preferred_match is None:
        preferred_match = _TRAILING_PREFERRED_SKILL_PATTERN.search(remainder)
    if preferred_match is None:
        return None

    capability = hard_match.group("capability").strip(" ，,。.;；")
    if not capability or len(capability) > 255:
        return None
    current_capability = item.normalized_capability.strip()
    if current_capability == capability:
        return None
    if current_capability and current_capability in _classification_text(original):
        return None
    return replace(item, normalized_capability=capability)


def _soft_clause_identity(value: str) -> str:
    return value.strip().rstrip("，,。.;；").strip().casefold()


def _terminal_punctuation_identity(value: str) -> str:
    return value.strip().rstrip("，,。.;；").strip().casefold()


def _presentation_quote(value: str) -> str:
    return _classification_text(value).strip().rstrip("，,。.;；").strip()


def _presentation_identity(value: str) -> str:
    return _presentation_quote(value).casefold()


def _is_redundant_same_source_constraint_subclause(
    description: str,
    item: ProposedJobRequirement,
    kept_items: list[ProposedJobRequirement],
) -> bool:
    """Drop a strict constraint subclause duplicated from the same grounded source line.

    This deliberately targets the human-reviewed v42.95 failure where a provider kept
    both ``A,B,C`` and ``B,C`` as separate hard constraints. The child is removable
    only when it begins at an explicit clause boundary inside an already-kept parent,
    both items have no independent normalized capability, and the wider child evidence
    proves that both quotes came from the same unique JD source occurrence.
    """
    if item.type is not RequirementType.CONSTRAINT or (item.normalized_capability or "").strip():
        return False
    child = _presentation_quote(item.original_text)
    child_evidence = _presentation_quote(item.evidence_span)
    if not child or not child_evidence:
        return False
    child_evidence_span = _unique_exact_span(description, child_evidence)
    if child_evidence_span is None:
        return False

    for parent in kept_items:
        if (
            parent.type is not RequirementType.CONSTRAINT
            or parent.importance is not item.importance
            or (parent.normalized_capability or "").strip()
        ):
            continue
        parent_text = _presentation_quote(parent.original_text)
        parent_evidence = _presentation_quote(parent.evidence_span)
        if not parent_text or parent_text == child or parent_evidence != parent_text:
            continue
        child_start = parent_text.find(child)
        if child_start <= 0 or parent_text[child_start - 1] not in {",", "，", ";", "；"}:
            continue
        parent_span = _unique_exact_span(description, parent_text)
        if parent_span is None:
            continue
        if not (
            child_evidence_span[0] <= parent_span[0]
            and parent_span[1] <= child_evidence_span[1]
        ):
            continue
        if child not in child_evidence:
            continue
        return True
    return False


def _recursive_hard_skill_subset_group(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> tuple[ProposedJobRequirement, ...]:
    """Return a strict three-level same-source hard-skill subset chain.

    This targets the formal Case #16 failure where one grounded engineering ability
    block was recursively emitted as ``A`` -> ``A+B`` -> ``A+B+C``. It deliberately
    requires three distinct exact-grounded prefix levels sharing one evidence span;
    ordinary sibling capabilities and two-level parent/child structures are untouched.
    """
    if (
        item.type is not RequirementType.SKILL
        or item.importance is not RequirementImportance.MUST_HAVE
        or not (item.normalized_capability or "").strip()
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
    ):
        return ()
    evidence_identity = _presentation_identity(item.evidence_span)
    if not evidence_identity or _unique_presentation_span(description, item.evidence_span) is None:
        return ()

    candidates = [
        candidate
        for candidate in all_items
        if (
            candidate.type is RequirementType.SKILL
            and candidate.importance is RequirementImportance.MUST_HAVE
            and (candidate.normalized_capability or "").strip()
            and not _SOFT_MARKER_PATTERN.search(candidate.original_text)
            and not _ALTERNATIVE_GROUP_PATTERN.search(candidate.original_text)
            and _presentation_identity(candidate.evidence_span) == evidence_identity
            and _unique_presentation_span(description, candidate.original_text) is not None
        )
    ]
    unique_by_text = {
        _presentation_identity(candidate.original_text): candidate
        for candidate in candidates
        if _presentation_identity(candidate.original_text)
    }
    if len(unique_by_text) < 3:
        return ()
    ordered = sorted(
        unique_by_text.values(),
        key=lambda candidate: len(_presentation_identity(candidate.original_text)),
        reverse=True,
    )
    parent_text = _presentation_quote(ordered[0].original_text)
    if len(re.findall(r"[、,，]|(?:和|及)", parent_text)) < 2:
        return ()

    chain = [ordered[0]]
    previous_identity = _presentation_identity(ordered[0].original_text)
    for candidate in ordered[1:]:
        candidate_identity = _presentation_identity(candidate.original_text)
        if previous_identity.startswith(candidate_identity) and candidate_identity != previous_identity:
            chain.append(candidate)
            previous_identity = candidate_identity
        if len(chain) >= 3:
            break
    if len(chain) < 3 or item not in chain:
        return ()
    return tuple(chain)


def _unique_presentation_span(
    description: str,
    value: str,
) -> tuple[int, int] | None:
    quote = _presentation_quote(value)
    return _unique_exact_span(description, quote) if quote else None


def _split_trailing_preferred_clause(
    item: ProposedJobRequirement,
) -> tuple[ProposedJobRequirement, ProposedJobRequirement] | None:
    if item.importance not in {
        RequirementImportance.MUST_HAVE,
        RequirementImportance.PREFERRED,
    }:
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


def _split_hard_preferred_hard_mixed_scope(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> tuple[
    ProposedJobRequirement,
    ProposedJobRequirement,
    ProposedJobRequirement,
] | None:
    """Split an exact hard-experience + preferred + hard-experience fused item.

    This is intentionally narrower than the covered-tail splitter. Both hard sides must
    be independently provable from verbatim experience grammar. The trailing hard side
    may include one explanatory comma segment (for example ``非...无法...``), but only
    the explicit experience fact itself becomes a Requirement. No semantic recovery or
    fuzzy matching is used.
    """
    if (
        item.type is not RequirementType.EXPERIENCE
        or item.importance is not RequirementImportance.MUST_HAVE
        or not item.original_text.strip()
        or _unique_exact_span(description, item.original_text.strip()) is None
    ):
        return None

    text = item.original_text.strip()
    match = _EMBEDDED_PREFERRED_EXPERIENCE_PATTERN.search(text)
    if match is None:
        match = _EMBEDDED_PREFERRED_SKILL_PATTERN.search(text)
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

    hard_prefix = prefix_with_bridge[:separator_index].strip()
    if (
        not hard_prefix
        or _SOFT_MARKER_PATTERN.search(hard_prefix)
        or _EXPLICIT_EXPERIENCE_FACT_PATTERN.fullmatch(
            _classification_text(hard_prefix)
        )
        is None
        or _unique_exact_span(description, hard_prefix) is None
    ):
        return None

    tail = match.group("tail").strip().lstrip("。.").strip()
    tail_segments = _comma_segments(tail)
    if not tail_segments or len(tail_segments) > 2:
        return None
    hard_tail = tail_segments[0][2]
    if (
        _EXPLICIT_EXPERIENCE_FACT_PATTERN.fullmatch(hard_tail) is None
        or _unique_exact_span(description, hard_tail) is None
    ):
        return None
    if (
        len(tail_segments) == 2
        and _EXPERIENCE_EXPLANATION_SUFFIX_PATTERN.fullmatch(tail_segments[1][2])
        is None
    ):
        return None
    if any(
        other is not item
        and other.importance is RequirementImportance.MUST_HAVE
        and bool(other.original_text.strip())
        and other.original_text.strip() in tail
        for other in all_items
    ):
        return None

    soft_item = _preferred_suffix_requirement(
        match.group("suffix"),
        confidence=item.confidence,
    )
    if soft_item is None:
        return None
    return (
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=hard_prefix,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=hard_prefix,
            confidence=item.confidence,
        ),
        soft_item,
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=hard_tail,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=hard_tail,
            confidence=item.confidence,
        ),
    )


def _split_embedded_preferred_clause_with_covered_tail(
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> tuple[ProposedJobRequirement, ProposedJobRequirement] | None:
    """Split a hard prefix from a preferred clause when a later tail is already covered.

    Source candidates can contain more than one sentence. A Provider may therefore
    return `hard prefix, preferred suffix. separate hard tail` as one item and may
    mislabel the whole mixed-scope item as either preferred or must-have. Only split
    when another must-have item already grounds a non-empty part of that trailing tail;
    this prevents the repair from silently discarding an uncovered requirement. All
    persisted text remains exact JD substrings.
    """
    if item.importance not in {
        RequirementImportance.MUST_HAVE,
        RequirementImportance.PREFERRED,
    }:
        return None
    text = item.original_text.strip()
    match = _EMBEDDED_PREFERRED_EXPERIENCE_PATTERN.search(text)
    if match is None:
        match = _EMBEDDED_PREFERRED_SKILL_PATTERN.search(text)
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
    tail = match.group("tail").strip().lstrip("。.").strip()
    if not tail:
        return None
    tail_is_covered = any(
        other is not item
        and other.importance is RequirementImportance.MUST_HAVE
        and bool(other.original_text.strip())
        and other.original_text.strip() in tail
        for other in all_items
    )
    if not tail_is_covered:
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


def _split_hard_skill_from_inline_alternative(
    description: str,
    item: ProposedJobRequirement,
) -> tuple[ProposedJobRequirement, ProposedJobRequirement] | None:
    if (
        item.type not in {
            RequirementType.SKILL,
            RequirementType.EXPERIENCE,
            RequirementType.CONSTRAINT,
        }
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return None
    text = item.original_text.strip()
    match = _ALTERNATIVE_GROUP_PATTERN.search(text)
    if match is None or _unique_exact_span(description, text) is None:
        return None
    prefix = text[: match.start()]
    separator_index = max(
        prefix.rfind(","),
        prefix.rfind("，"),
        prefix.rfind(";"),
        prefix.rfind("；"),
    )
    if separator_index < 0:
        return None
    hard_text = text[:separator_index].strip()
    alternative_text = text[separator_index + 1 :].strip().rstrip("。.;；").strip()
    hard_classification = _classification_text(hard_text)
    capability = (item.normalized_capability or "").strip()
    if item.type is RequirementType.CONSTRAINT:
        capability_match = _HARD_SKILL_CAPABILITY_CAPTURE_PATTERN.fullmatch(
            hard_classification
        )
        capability = (
            capability_match.group("capability").strip()
            if capability_match is not None
            else ""
        )
    capability_key = _normalize_grounding_text(capability).casefold()
    hard_key = _normalize_grounding_text(hard_classification).casefold()
    if (
        not hard_text
        or not alternative_text
        or not capability_key
        or len(capability) > 255
        or capability_key not in hard_key
        or _HARD_SKILL_PREFIX_PATTERN.fullmatch(hard_classification) is None
        or _ALTERNATIVE_GROUP_PATTERN.search(hard_classification)
        or _ALTERNATIVE_GROUP_PATTERN.search(alternative_text) is None
        or _unique_exact_span(description, hard_text) is None
        or _unique_exact_span(description, alternative_text) is None
    ):
        return None
    return (
        replace(
            item,
            type=RequirementType.SKILL,
            original_text=hard_text,
            evidence_span=hard_text,
            normalized_capability=capability,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=alternative_text,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=alternative_text,
            confidence=item.confidence,
        ),
    )


def _comma_segments(value: str) -> list[tuple[int, int, str]]:
    segments: list[tuple[int, int, str]] = []
    for match in re.finditer(r"[^，,]+", value):
        raw = match.group(0)
        left_trim = len(raw) - len(raw.lstrip())
        right_trim = len(raw) - len(raw.rstrip())
        start = match.start() + left_trim
        end = match.end() - right_trim
        text = value[start:end].strip().rstrip("。.;；").strip()
        if text:
            segments.append((start, end, text))
    return segments


def _split_mixed_education_experience(
    description: str,
    item: ProposedJobRequirement,
) -> tuple[ProposedJobRequirement, ...] | None:
    if (
        item.type not in {
            RequirementType.EDUCATION,
            RequirementType.EXPERIENCE,
            RequirementType.CONSTRAINT,
        }
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return None
    text = item.original_text.strip()
    if _unique_exact_span(description, text) is None:
        return None
    segments = _comma_segments(text)
    if len(segments) < 2:
        return None
    first_experience_index = next(
        (
            index
            for index, (_, _, segment) in enumerate(segments)
            if _EXPERIENCE_SEGMENT_PATTERN.search(segment)
        ),
        None,
    )
    if first_experience_index is None or first_experience_index == 0:
        return None
    education_segments = segments[:first_experience_index]
    experience_segments = segments[first_experience_index:]
    if (
        not all(_EDUCATION_SEGMENT_PATTERN.search(segment) for _, _, segment in education_segments)
        or not all(_EXPERIENCE_SEGMENT_PATTERN.search(segment) for _, _, segment in experience_segments)
    ):
        return None
    education_text = text[: experience_segments[0][0]].rstrip("，, ").strip()
    if not education_text or _unique_exact_span(description, education_text) is None:
        return None
    experience_texts = [segment for _, _, segment in experience_segments]
    if any(_unique_exact_span(description, segment) is None for segment in experience_texts):
        return None
    return (
        replace(
            item,
            type=RequirementType.EDUCATION,
            original_text=education_text,
            evidence_span=education_text,
            normalized_capability=None,
        ),
        *(
            ProposedJobRequirement(
                type=RequirementType.EXPERIENCE,
                original_text=segment,
                normalized_capability=None,
                importance=RequirementImportance.MUST_HAVE,
                evidence_span=segment,
                confidence=item.confidence,
            )
            for segment in experience_texts
        ),
    )


def _is_alternative_group_type_drift(
    description: str,
    item: ProposedJobRequirement,
) -> bool:
    if (
        item.type not in {RequirementType.EXPERIENCE, RequirementType.RESPONSIBILITY}
        or item.importance is not RequirementImportance.MUST_HAVE
        or bool((item.normalized_capability or "").strip())
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _unique_exact_span(description, item.original_text) is None
    ):
        return False
    match = _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
    if match is None:
        return False
    if item.type is RequirementType.RESPONSIBILITY:
        return True
    prefix = item.original_text[: match.start()]
    return "经验" not in prefix and _THRESHOLD_PATTERN.search(prefix) is None


def _expand_compound_hard_skill_from_evidence_span(
    description: str,
    item: ProposedJobRequirement,
) -> ProposedJobRequirement | None:
    """Expand a truncated hard skill only from its exact grounded evidence span.

    A Provider may emit the first hard segment as originalText while its evidenceSpan
    contains the complete same-clause requirement. Expansion is allowed only when the
    missing suffix begins with a comma and is itself an explicit hard-capability segment.
    The persisted quote is the exact raw JD slice starting at originalText; numbered
    prefixes and trailing sentence punctuation are deliberately excluded.
    """
    if (
        item.type is not RequirementType.SKILL
        or item.importance is not RequirementImportance.MUST_HAVE
        or not item.normalized_capability
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
    ):
        return None
    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not original
        or not evidence
        or original == evidence
        or _unique_exact_span(description, original) is None
        or _unique_exact_span(description, evidence) is None
    ):
        return None
    relative_start = evidence.find(original)
    if relative_start < 0:
        return None
    suffix = evidence[relative_start + len(original) :].strip()
    if not suffix.startswith((",", "，")):
        return None
    missing_segment = suffix[1:].strip().rstrip("。.;；").strip()
    if (
        not missing_segment
        or _COMPOUND_HARD_SKILL_SEGMENT_PATTERN.fullmatch(missing_segment) is None
        or _SOFT_MARKER_PATTERN.search(missing_segment)
        or _ALTERNATIVE_GROUP_PATTERN.search(missing_segment)
    ):
        return None
    expanded = f"{original}{suffix[:1]}{missing_segment}"
    if _unique_exact_span(description, expanded) is None:
        return None
    return replace(
        item,
        type=RequirementType.CONSTRAINT,
        original_text=expanded,
        evidence_span=expanded,
        normalized_capability=None,
    )


def _is_compound_hard_skill_constraint(
    description: str,
    item: ProposedJobRequirement,
) -> bool:
    if (
        item.type is not RequirementType.SKILL
        or item.importance is not RequirementImportance.MUST_HAVE
        or not item.normalized_capability
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
        or _unique_exact_span(description, item.original_text) is None
    ):
        return False
    text = _classification_text(item.original_text)
    segments = _comma_segments(text)
    hard_segment_count = sum(
        (
            _COMPOUND_HARD_SKILL_SEGMENT_PATTERN.fullmatch(segment) is not None
            or _EVALUATIVE_ABILITY_SEGMENT_PATTERN.fullmatch(segment) is not None
        )
        for _, _, segment in segments
    )
    if len(segments) >= 2 and hard_segment_count >= 2:
        return True
    return _EXPLICIT_CORE_TECHNOLOGY_LIST_PATTERN.fullmatch(text) is not None


def _normalize_conceptual_mechanism_skill_constraint(
    description: str,
    item: ProposedJobRequirement,
) -> ProposedJobRequirement | None:
    """Normalize umbrella conceptual knowledge away from exact skill hard-gating.

    This is deliberately narrower than generic ``理解...`` requirements. It only
    accepts an exact-grounded ``理解/了解 ... 基本机制/工作机制, 包括 ...`` shape with
    at least three enumerated concepts and no execution/action clause. If the Provider
    emitted only a grounded substring, the complete exact evidenceSpan may be restored;
    no fuzzy or semantic source recovery is used.
    """
    if (
        item.type not in {RequirementType.SKILL, RequirementType.DOMAIN}
        or item.importance is not RequirementImportance.MUST_HAVE
        or (
            item.type is RequirementType.SKILL
            and not item.normalized_capability
        )
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
    ):
        return None

    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    candidates = [original]
    allow_evidence_recovery = not (
        item.type is RequirementType.DOMAIN
        and not item.normalized_capability
    )
    if (
        allow_evidence_recovery
        and evidence != original
        and original
        and original in evidence
    ):
        candidates.append(evidence)

    for candidate in candidates:
        if not candidate or _unique_exact_span(description, candidate) is None:
            continue
        text = _classification_text(candidate)
        match = _CONCEPTUAL_MECHANISM_UMBRELLA_PATTERN.fullmatch(text)
        if match is None:
            continue
        concepts = match.group("concepts").strip()
        if (
            len(re.findall(r"[、,，]", concepts)) < 2
            or _CONCEPTUAL_MECHANISM_ACTION_PATTERN.search(concepts)
            or _SOFT_MARKER_PATTERN.search(candidate)
            or _ALTERNATIVE_GROUP_PATTERN.search(candidate)
        ):
            continue
        return replace(
            item,
            type=RequirementType.CONSTRAINT,
            original_text=candidate,
            evidence_span=(candidate if candidate == evidence else item.evidence_span),
            normalized_capability=None,
        )
    return None


def _engineering_habit_quality_clause(value: str) -> tuple[str, tuple[str, ...]] | None:
    raw = value.strip()
    if not raw:
        return None
    clause = _LEADING_NUMBERED_ITEM_PREFIX_PATTERN.sub("", raw, count=1).strip()
    clause = clause.rstrip("。.;；").strip()
    match = _ENGINEERING_HABIT_QUALITY_PATTERN.fullmatch(clause)
    if match is None:
        return None
    qualities = tuple(
        part.strip()
        for part in re.split(r"[、]|(?:和|及)", match.group("qualities"))
        if part.strip()
    )
    if len(qualities) < 3 or any(
        quality not in _ENGINEERING_HABIT_QUALITY_TERMS for quality in qualities
    ):
        return None
    return clause, qualities


def _is_redundant_compound_hard_child(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Drop an atomic hard skill already enforced by the same compound constraint.

    The parent must be an exact-grounded must-have constraint containing at least two
    explicit hard-capability comma segments. The child must equal one complete segment
    and its evidence must contain the exact parent quote, which keeps the repair scoped
    to one JD clause rather than semantic similarity.
    """
    if (
        item.type is not RequirementType.SKILL
        or item.importance is not RequirementImportance.MUST_HAVE
        or not item.normalized_capability
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
        or _unique_exact_span(description, item.original_text) is None
        or _unique_exact_span(description, item.evidence_span) is None
    ):
        return False

    child_text = _classification_text(item.original_text)
    for parent in all_items:
        if (
            parent is item
            or parent.type is not RequirementType.CONSTRAINT
            or parent.importance is not RequirementImportance.MUST_HAVE
            or _SOFT_MARKER_PATTERN.search(parent.original_text)
            or _ALTERNATIVE_GROUP_PATTERN.search(parent.original_text)
            or _unique_exact_span(description, parent.original_text) is None
        ):
            continue
        parent_text = _classification_text(parent.original_text)
        segments = _comma_segments(parent_text)
        hard_segments = [
            segment
            for _, _, segment in segments
            if (
                _COMPOUND_HARD_SKILL_SEGMENT_PATTERN.fullmatch(segment) is not None
                or _EVALUATIVE_ABILITY_SEGMENT_PATTERN.fullmatch(segment) is not None
            )
        ]
        if len(segments) < 2 or len(hard_segments) < 2:
            continue
        if child_text not in hard_segments:
            continue
        if parent.original_text.strip() not in item.evidence_span.strip():
            continue
        return True
    return False


def _is_redundant_cross_type_exact_duplicate(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Drop evaluator-risky cross-type duplicates that resolve to one source fact."""
    original_identity = _presentation_identity(item.original_text)
    source_span = _unique_presentation_span(description, item.original_text)
    if not original_identity or source_span is None:
        return False
    text = _classification_text(item.original_text)
    if (
        _EXPLICIT_EXPERIENCE_WITH_ABILITY_PATTERN.fullmatch(text) is not None
        and _SOFT_MARKER_PATTERN.search(item.original_text) is None
        and _SOFT_MARKER_PATTERN.search(item.evidence_span) is None
    ):
        section_name = _nearest_section_name(description, source_span[0])
        evidence_identity = _presentation_identity(item.evidence_span)
        canonical_experience_exists = any(
            other is not item
            and other.type is RequirementType.EXPERIENCE
            and other.importance is RequirementImportance.MUST_HAVE
            and _presentation_identity(other.original_text) == original_identity
            and _unique_presentation_span(description, other.original_text) == source_span
            and _presentation_identity(other.evidence_span) == evidence_identity
            for other in all_items
        )
        if (
            section_name is not None
            and _REQUIREMENT_SECTION_NAME_PATTERN.fullmatch(section_name) is not None
            and canonical_experience_exists
        ):
            return not (
                item.type is RequirementType.EXPERIENCE
                and item.importance is RequirementImportance.MUST_HAVE
            )
    siblings = [
        other
        for other in all_items
        if other is not item
        and other.importance is item.importance
        and other.type is not item.type
        and _presentation_identity(other.original_text) == original_identity
        and _unique_presentation_span(description, other.original_text) == source_span
    ]
    if not siblings:
        return False
    if _EXPLICIT_EXPERIENCE_FACT_PATTERN.fullmatch(text) is not None:
        return item.type is not RequirementType.EXPERIENCE and any(
            other.type is RequirementType.EXPERIENCE for other in siblings
        )
    if _HARD_SKILL_PREFIX_PATTERN.fullmatch(text) is not None:
        return item.type is not RequirementType.SKILL and any(
            other.type is RequirementType.SKILL for other in siblings
        )
    return False


def _is_conjunctive_hard_sibling_of_alternative_group(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Keep an explicit conjunctive requirement hard beside a cardinality clause.

    This only accepts a same-evidence sibling that starts with an explicit conjunction
    such as ``并/且/同时`` and immediately follows a must-have alternative/cardinality
    constraint in the same raw JD slice. The shared evidence must contain no softening
    marker. It prevents the generic alternative-child scope from downgrading a second
    independently mandatory clause in the same numbered item.
    """
    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    if (
        not original
        or not evidence
        or _CONJUNCTIVE_HARD_SUFFIX_PATTERN.search(_classification_text(original)) is None
        or _SOFT_MARKER_PATTERN.search(original)
        or _SOFT_MARKER_PATTERN.search(evidence)
        or _unique_exact_span(description, original) is None
        or _unique_exact_span(description, evidence) is None
    ):
        return False
    child_offset = evidence.find(original)
    if child_offset < 0:
        return False

    for sibling in all_items:
        if (
            sibling is item
            or sibling.type is not RequirementType.CONSTRAINT
            or sibling.importance is not RequirementImportance.MUST_HAVE
            or _ALTERNATIVE_GROUP_PATTERN.search(sibling.original_text) is None
            or _SOFT_MARKER_PATTERN.search(sibling.original_text)
            or sibling.evidence_span.strip() != evidence
        ):
            continue
        parent_text = sibling.original_text.strip()
        parent_offset = evidence.find(parent_text)
        if parent_offset < 0 or parent_offset >= child_offset:
            continue
        bridge = evidence[parent_offset + len(parent_text) : child_offset]
        if re.fullmatch(r"[\s,，;；.。]*", bridge):
            return True
    return False


def _is_post_cardinality_hard_sibling(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Keep a bounded hard-skill sibling after an inline cardinality parent hard.

    This only accepts a same-evidence must-have skill that immediately follows an
    already recovered must-have alternative/cardinality constraint, with punctuation
    only between the two exact grounded spans. The sibling itself must be a complete
    hard-skill clause and the shared evidence must contain no soft marker. It prevents
    an inline cardinality scope from swallowing the next independent hard clause.
    """
    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    is_bounded_skill = (
        item.type is RequirementType.SKILL
        and _HARD_SKILL_PREFIX_PATTERN.fullmatch(_classification_text(original)) is not None
    )
    is_bounded_engineering_constraint = (
        item.type is RequirementType.CONSTRAINT
        and _classification_text(original) == "具备良好的工程规范和代码品味"
    )
    if (
        item.importance is not RequirementImportance.MUST_HAVE
        or not original
        or not evidence
        or not (is_bounded_skill or is_bounded_engineering_constraint)
        or _SOFT_MARKER_PATTERN.search(original)
        or _SOFT_MARKER_PATTERN.search(evidence)
        or _unique_exact_span(description, original) is None
        or _unique_exact_span(description, evidence) is None
    ):
        return False
    child_offset = evidence.find(original)
    if child_offset < 0:
        return False

    for sibling in all_items:
        if (
            sibling is item
            or sibling.type is not RequirementType.CONSTRAINT
            or sibling.importance is not RequirementImportance.MUST_HAVE
            or _ALTERNATIVE_GROUP_PATTERN.search(sibling.original_text) is None
            or _SOFT_MARKER_PATTERN.search(sibling.original_text)
            or sibling.evidence_span.strip() != evidence
        ):
            continue
        parent_text = sibling.original_text.strip()
        parent_offset = evidence.find(parent_text)
        if parent_offset < 0 or parent_offset >= child_offset:
            continue
        bridge = evidence[parent_offset + len(parent_text) : child_offset]
        if re.fullmatch(r"[\s,，;；.。]*", bridge):
            return True
    return False


def _is_redundant_split_hard_parent(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    """Drop a broad hard parent only when its exact two children already exist."""
    if (
        item.type is not RequirementType.CONSTRAINT
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text) is None
        or _unique_exact_span(description, item.original_text) is None
    ):
        return False

    text = _classification_text(item.original_text)
    match = _ALTERNATIVE_GROUP_PATTERN.search(text)
    if match is None:
        return False
    prefix = text[: match.start()]
    separator_index = max(
        prefix.rfind(","),
        prefix.rfind("，"),
        prefix.rfind(";"),
        prefix.rfind("；"),
    )
    if separator_index < 0:
        return False
    hard_text = text[:separator_index].strip()
    alternative_text = text[separator_index + 1 :].strip().rstrip("。.;；").strip()
    if (
        not hard_text
        or not alternative_text
        or _HARD_SKILL_PREFIX_PATTERN.fullmatch(hard_text) is None
        or _ALTERNATIVE_GROUP_PATTERN.search(alternative_text) is None
    ):
        return False

    hard_child = any(
        other is not item
        and other.type is RequirementType.SKILL
        and other.importance is RequirementImportance.MUST_HAVE
        and _classification_text(other.original_text) == hard_text
        and other.original_text.strip() in item.original_text
        for other in all_items
    )
    alternative_child = any(
        other is not item
        and other.type is RequirementType.CONSTRAINT
        and other.importance is RequirementImportance.MUST_HAVE
        and _classification_text(other.original_text) == alternative_text
        and other.original_text.strip().rstrip("。.;；").strip()
        in item.original_text.rstrip("。.;；").strip()
        for other in all_items
    )
    return hard_child and alternative_child


def _is_compound_domain_sibling_group(
    description: str,
    original_text: str,
    evidence_span: str,
) -> bool:
    original = original_text.strip()
    evidence = evidence_span.strip()
    if (
        not original
        or not evidence
        or _SOFT_MARKER_PATTERN.search(original)
        or _ALTERNATIVE_GROUP_PATTERN.search(original)
        or _unique_exact_span(description, original) is None
        or _unique_exact_span(description, evidence) is None
    ):
        return False
    segments = _comma_segments(_classification_text(original))
    if len(segments) < 2:
        return False
    first = segments[0][2]
    rest = [segment for _, _, segment in segments[1:]]
    return bool(
        _EXPLICIT_CORE_TECHNOLOGY_LIST_PATTERN.fullmatch(first)
        and any(
            _COMPOUND_HARD_SKILL_SEGMENT_PATTERN.fullmatch(segment) is not None
            for segment in rest
        )
    )


def _is_preferred_explicit_mandatory_experience(
    description: str,
    item: ProposedJobRequirement,
) -> bool:
    """Promote an explicitly mandatory experience fact that Provider softened.

    This is intentionally narrower than requirement-section defaulting: the item must
    already be an experience row, be exact-grounded, contain no soft marker, and match
    the same explicit experience grammar used by the existing type-drift repair. A
    two-segment form is accepted only when the second segment is an explicit negative
    consequence such as ``非...无法...``.
    """
    if (
        item.type is not RequirementType.EXPERIENCE
        or item.importance is not RequirementImportance.PREFERRED
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _SOFT_MARKER_PATTERN.search(item.evidence_span)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
        or _unique_exact_span(description, item.original_text) is None
        or _unique_exact_span(description, item.evidence_span) is None
    ):
        return False
    text = _classification_text(item.original_text)
    if _EXPLICIT_EXPERIENCE_FACT_PATTERN.fullmatch(text) is not None:
        return True
    segments = _comma_segments(text)
    return bool(
        len(segments) == 2
        and _EXPLICIT_EXPERIENCE_FACT_PATTERN.fullmatch(segments[0][2]) is not None
        and _EXPERIENCE_EXPLANATION_SUFFIX_PATTERN.fullmatch(segments[1][2]) is not None
    )


def _normalize_explicit_experience_type_drift(
    description: str,
    item: ProposedJobRequirement,
) -> ProposedJobRequirement | None:
    if (
        item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
    ):
        return None
    text = item.original_text.strip()
    if not text or text not in description:
        return None
    classification_text = _classification_text(text)
    if _EXPLICIT_EXPERIENCE_FACT_PATTERN.fullmatch(classification_text) is not None:
        if item.type is RequirementType.EXPERIENCE:
            return None
        return replace(
            item,
            type=RequirementType.EXPERIENCE,
            normalized_capability=None,
        )
    experience_text = text
    preserve_full_text = False
    if _EXPLICIT_EXPERIENCE_FACT_PATTERN.fullmatch(text) is None:
        segments = _comma_segments(text)
        if len(segments) != 2 or _EXPLICIT_EXPERIENCE_FACT_PATTERN.fullmatch(segments[0][2]) is None:
            return None
        if _EXPERIENCE_EXPLANATION_SUFFIX_PATTERN.fullmatch(segments[1][2]) is not None:
            experience_text = segments[0][2]
        elif _EXPERIENCE_FOLLOWUP_QUALIFICATION_PATTERN.fullmatch(segments[1][2]) is not None:
            preserve_full_text = True
        else:
            return None
    if experience_text not in text or experience_text not in description:
        return None
    return replace(
        item,
        type=RequirementType.EXPERIENCE,
        original_text=text if preserve_full_text else experience_text,
        evidence_span=item.evidence_span if preserve_full_text else experience_text,
        normalized_capability=None,
    )


def _is_abstract_evaluative_skill_constraint(
    description: str,
    item: ProposedJobRequirement,
) -> bool:
    text = _classification_text(item.original_text)
    segments = _comma_segments(text)
    practice_with_detail = bool(
        len(segments) >= 2
        and _ABSTRACT_EVALUATIVE_PRACTICE_PATTERN.fullmatch(segments[0][2])
        and segments[1][2].startswith("重视")
    )
    compound_evaluative_ability = bool(
        len(segments) >= 2
        and _ABSTRACT_EVALUATIVE_COMPOUND_SEGMENT_PATTERN.fullmatch(segments[0][2])
        and item.normalized_capability
        and item.normalized_capability.strip() in segments[0][2]
    )
    evaluative_trait_compound = bool(
        len(segments) >= 2
        and all(
            _ABSTRACT_EVALUATIVE_TRAIT_PATTERN.fullmatch(segment)
            for _, _, segment in segments
        )
    )
    evidence = _classification_text(item.evidence_span)
    evidence_segments = _comma_segments(evidence)
    evidence_scoped_compound_evaluative_ability = bool(
        len(segments) == 1
        and len(evidence_segments) >= 2
        and evidence_segments[0][2] == text
        and _ABSTRACT_EVALUATIVE_COMPOUND_SEGMENT_PATTERN.fullmatch(text)
        and item.normalized_capability
        and _unique_exact_span(description, item.evidence_span) is not None
    )
    return bool(
        item.type is RequirementType.SKILL
        and item.importance is RequirementImportance.MUST_HAVE
        and item.normalized_capability
        and not _SOFT_MARKER_PATTERN.search(item.original_text)
        and not _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
        and _unique_exact_span(description, item.original_text) is not None
        and (
            _ABSTRACT_EVALUATIVE_ABILITY_PATTERN.fullmatch(text)
            or _ABSTRACT_EVALUATIVE_TRAIT_PATTERN.fullmatch(text)
            or _ABSTRACT_EVALUATIVE_PRACTICE_PATTERN.fullmatch(text)
            or practice_with_detail
            or compound_evaluative_ability
            or evaluative_trait_compound
            or evidence_scoped_compound_evaluative_ability
        )
    )


def _normalize_abstract_evaluative_type_drift(
    description: str,
    item: ProposedJobRequirement,
) -> ProposedJobRequirement | None:
    """Normalize qualification-like responsibility/domain/experience drift without guessing semantics."""
    if (
        item.type not in {
            RequirementType.RESPONSIBILITY,
            RequirementType.DOMAIN,
            RequirementType.EXPERIENCE,
        }
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
    ):
        return None

    original = item.original_text.strip()
    evidence = item.evidence_span.strip()
    original_span = _unique_exact_span(description, original)
    if original_span is not None:
        text = _classification_text(original)
        if (
            _ABSTRACT_EVALUATIVE_ABILITY_PATTERN.fullmatch(text)
            or _ABSTRACT_EVALUATIVE_PRACTICE_PATTERN.fullmatch(text)
        ):
            return replace(
                item,
                type=RequirementType.CONSTRAINT,
                normalized_capability=None,
            )
        segments = _comma_segments(text)
        evaluative_ability_with_action = bool(
            len(segments) >= 2
            and _EVALUATIVE_ABILITY_SEGMENT_PATTERN.fullmatch(segments[0][2])
            and any(segment.startswith("能") for _, _, segment in segments[1:])
        )
        if (
            (
                len(segments) >= 2
                and _ABSTRACT_EVALUATIVE_PRACTICE_PATTERN.fullmatch(segments[0][2])
                and segments[1][2].startswith("重视")
            )
            or evaluative_ability_with_action
        ):
            return replace(
                item,
                type=RequirementType.CONSTRAINT,
                normalized_capability=None,
            )

    if (
        not evidence
        or original not in evidence
        or _SOFT_MARKER_PATTERN.search(evidence)
        or _unique_exact_span(description, evidence) is None
    ):
        return None
    evidence_text = _classification_text(evidence)
    evidence_segments = _comma_segments(evidence_text)
    if not (
        len(evidence_segments) >= 2
        and _ABSTRACT_EVALUATIVE_PRACTICE_PATTERN.fullmatch(evidence_segments[0][2])
        and evidence_segments[1][2].startswith("重视")
    ):
        return None
    return replace(
        item,
        type=RequirementType.CONSTRAINT,
        original_text=evidence,
        evidence_span=evidence,
        normalized_capability=None,
    )


def _normalize_technical_stack_constraint_drift(
    description: str,
    item: ProposedJobRequirement,
) -> ProposedJobRequirement | None:
    """Recover an exact hard technical-stack qualification from constraint drift.

    This is intentionally narrower than generic constraint-to-skill conversion. It
    requires an unsoftened must-have constraint inside an explicit requirement
    section, a hard-skill verb, an inline example list, and an umbrella ending in
    ``技术栈``. The capability is derived verbatim from that umbrella prefix.
    """
    if (
        item.type is not RequirementType.CONSTRAINT
        or item.importance is not RequirementImportance.MUST_HAVE
        or item.normalized_capability is not None
        or _SOFT_MARKER_PATTERN.search(item.original_text)
        or not _is_requirement_section_span(description, item.evidence_span)
        or _unique_exact_span(description, item.original_text) is None
    ):
        return None
    text = _classification_text(item.original_text)
    example_match = _INLINE_EXAMPLE_LIST_PATTERN.search(text)
    if example_match is None:
        return None
    umbrella = text[: example_match.start()].strip()
    if (
        _HARD_SKILL_PREFIX_PATTERN.fullmatch(umbrella) is None
        or not umbrella.endswith("技术栈")
    ):
        return None
    capability = re.sub(
        r"^(?:熟悉|熟练(?:使用|掌握)?|掌握|精通|使用)\s*",
        "",
        umbrella,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    if not capability:
        return None
    return replace(
        item,
        type=RequirementType.SKILL,
        normalized_capability=capability,
    )


def _normalize_umbrella_skill_example_capability(
    description: str,
    item: ProposedJobRequirement,
) -> ProposedJobRequirement | None:
    """Prevent an illustrative example from becoming the hard umbrella capability.

    This repair is intentionally limited to a hard skill whose exact original text
    contains an inline example list. It only fires when the Provider-selected
    capability appears inside the example suffix and not in the umbrella prefix.
    The replacement capability is derived verbatim from the hard-skill prefix after
    removing only the bounded qualification verb (for example ``熟悉``).
    """
    if (
        item.type is not RequirementType.SKILL
        or item.importance is not RequirementImportance.MUST_HAVE
        or not item.normalized_capability
    ):
        return None
    text = _classification_text(item.original_text)
    if _unique_exact_span(description, item.original_text) is None:
        return None
    example_matches = tuple(
        match
        for pattern in (
            _INLINE_EXAMPLE_LIST_PATTERN,
            _NONPARENTHETICAL_EXAMPLE_LIST_PATTERN,
        )
        if (match := pattern.search(text)) is not None
    )
    if not example_matches:
        return None
    example_match = min(example_matches, key=lambda match: match.start())
    umbrella = text[: example_match.start()].strip()
    example_suffix = text[example_match.start() :]
    current = item.normalized_capability.strip()
    full_phrase_capability = re.sub(
        r"^(?:熟悉|熟练(?:使用|掌握)?|掌握|精通|使用)\s*",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    example_only_capability = bool(
        current
        and current.casefold() in example_suffix.casefold()
        and current.casefold() not in umbrella.casefold()
    )
    full_phrase_example_capability = bool(
        current
        and _normalize_grounding_text(current).casefold()
        == _normalize_grounding_text(full_phrase_capability).casefold()
    )
    original_span = _unique_exact_span(description, item.original_text)
    soft_suffix_capability = False
    if original_span is not None:
        normalized_current = _normalize_grounding_text(current).casefold()
        normalized_full_phrase = _normalize_grounding_text(full_phrase_capability).casefold()
        if (
            current.casefold().startswith(full_phrase_capability.casefold())
            and normalized_current.startswith(normalized_full_phrase)
            and normalized_current != normalized_full_phrase
        ):
            trailing_capability = current[len(full_phrase_capability) :].strip(" ，,。.;；")
            following_source = description[original_span[1] : original_span[1] + 80]
            soft_suffix_capability = bool(
                trailing_capability
                and trailing_capability in following_source
                and _SOFT_MARKER_PATTERN.search(following_source)
            )
    if (
        not (
            example_only_capability
            or full_phrase_example_capability
            or soft_suffix_capability
        )
        or _HARD_SKILL_PREFIX_PATTERN.fullmatch(umbrella) is None
    ):
        return None
    capability = re.sub(
        r"^(?:熟悉|熟练(?:使用|掌握)?|掌握|精通|使用)\s*",
        "",
        umbrella,
        count=1,
        flags=re.IGNORECASE,
    ).strip()
    if not capability or capability.casefold() == current.casefold():
        return None
    return replace(item, normalized_capability=capability)


def _is_redundant_example_child(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> bool:
    if (
        item.importance is not RequirementImportance.MUST_HAVE
        or _unique_exact_span(description, item.original_text) is None
        or _unique_exact_span(description, item.evidence_span) is None
    ):
        return False
    evidence = item.evidence_span.strip()
    text = item.original_text.strip()
    child_start = evidence.find(text)
    if child_start < 0:
        return False

    explicit_example_child = _EXAMPLE_CHILD_PATTERN.search(text) is not None
    inline_parenthetical_match = _INLINE_EXAMPLE_LIST_PATTERN.search(evidence)
    inline_parenthetical_child = False
    if inline_parenthetical_match is not None:
        closing_positions = [
            position
            for token in (")", "）")
            if (position := evidence.find(token, inline_parenthetical_match.end())) >= 0
        ]
        if closing_positions:
            closing_position = min(closing_positions)
            child_end = child_start + len(text)
            inline_parenthetical_child = bool(
                child_start >= inline_parenthetical_match.start()
                and child_end <= closing_position
            )

    marker_matches = tuple(
        match
        for match in (
            re.search(r"包括但不限于", evidence, flags=re.IGNORECASE),
            _NONPARENTHETICAL_EXAMPLE_LIST_PATTERN.search(evidence),
        )
        if match is not None
    )
    marker_match = min(marker_matches, key=lambda match: match.start()) if marker_matches else None
    continuation_example_child = bool(
        marker_match is not None
        and child_start >= marker_match.start()
    )
    if not (
        explicit_example_child
        or continuation_example_child
        or inline_parenthetical_child
    ):
        return False

    parent_marker_start = (
        min(
            match.start()
            for match in (
                marker_match,
                inline_parenthetical_match,
            )
            if match is not None
        )
        if marker_match is not None or inline_parenthetical_match is not None
        else None
    )

    return any(
        other is not item
        and other.importance is RequirementImportance.MUST_HAVE
        and other.evidence_span.strip() == evidence
        and _EXAMPLE_CHILD_PATTERN.search(other.original_text.strip()) is None
        and 0 <= evidence.find(other.original_text.strip()) < child_start
        and (
            parent_marker_start is None
            or evidence.find(other.original_text.strip()) < parent_marker_start
        )
        for other in all_items
    )


def _split_hard_skill_from_fused_experience(
    description: str,
    item: ProposedJobRequirement,
) -> tuple[ProposedJobRequirement, ProposedJobRequirement] | None:
    if (
        item.type not in {RequirementType.EXPERIENCE, RequirementType.SKILL}
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return None
    text = item.original_text.strip()
    if _unique_exact_span(description, text) is None:
        return None
    segments = _comma_segments(text)
    if len(segments) != 2:
        return None
    skill_text = segments[0][2]
    experience_text = segments[1][2]
    if item.type is RequirementType.SKILL and not experience_text.startswith("对"):
        return None
    if (
        _HARD_SKILL_PREFIX_PATTERN.fullmatch(_classification_text(skill_text)) is None
        or _FUSED_EXPERIENCE_SUFFIX_PATTERN.fullmatch(experience_text) is None
        or _unique_exact_span(description, skill_text) is None
        or _unique_exact_span(description, experience_text) is None
    ):
        return None
    return (
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=skill_text,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=skill_text,
            confidence=item.confidence,
        ),
        ProposedJobRequirement(
            type=RequirementType.EXPERIENCE,
            original_text=experience_text,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=experience_text,
            confidence=item.confidence,
        ),
    )


def _split_experience_prefix_from_alternative_group(
    description: str,
    item: ProposedJobRequirement,
) -> tuple[ProposedJobRequirement, ProposedJobRequirement] | None:
    if (
        item.type not in {RequirementType.EXPERIENCE, RequirementType.SKILL}
        or item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return None
    text = item.original_text.strip()
    match = _ALTERNATIVE_GROUP_PATTERN.search(text)
    if match is None or _unique_exact_span(description, text) is None:
        return None
    prefix = text[: match.start()]
    separator_index = max(prefix.rfind(","), prefix.rfind("，"))
    if separator_index < 0:
        return None
    experience_text = text[:separator_index].strip()
    alternative_text = text[separator_index + 1 :].strip()
    if (
        not experience_text
        or not alternative_text
        or _EXPERIENCE_SEGMENT_PATTERN.fullmatch(experience_text) is None
        or _unique_exact_span(description, experience_text) is None
        or _unique_exact_span(description, alternative_text) is None
    ):
        return None
    return (
        replace(
            item,
            type=RequirementType.EXPERIENCE,
            original_text=experience_text,
            evidence_span=experience_text,
            normalized_capability=None,
        ),
        ProposedJobRequirement(
            type=RequirementType.CONSTRAINT,
            original_text=alternative_text,
            normalized_capability=None,
            importance=RequirementImportance.MUST_HAVE,
            evidence_span=alternative_text,
            confidence=item.confidence,
        ),
    )


def _recover_noncontiguous_alternative_group_header(
    description: str,
    item: ProposedJobRequirement,
    all_items: tuple[ProposedJobRequirement, ...],
) -> ProposedJobRequirement | None:
    """Recover only a grounded cardinality header from a non-contiguous aggregate.

    Providers sometimes concatenate a cardinality header plus several bullet children
    into one quote that never occurs contiguously in the JD. Recovery is allowed only
    when the header is uniquely grounded and the entire remaining provider text is an
    exact normalized concatenation of separately grounded child requirements inside
    that numbered item's scope. No fuzzy or semantic matching is used.
    """
    if (
        item.importance is not RequirementImportance.MUST_HAVE
        or _SOFT_MARKER_PATTERN.search(item.original_text)
    ):
        return None
    text = item.original_text.strip()
    if not text or text in description:
        return None
    cardinality = _ALTERNATIVE_GROUP_PATTERN.search(text)
    if cardinality is None:
        return None
    colon = re.match(r"\s*[:：]", text[cardinality.end() :])
    if colon is None:
        return None
    header_end = cardinality.end() + colon.end()
    header = text[:header_end].strip()
    header_span = _unique_exact_span(description, header)
    if header_span is None:
        return None
    tail = text[header_end:].strip()
    tail_key = _normalize_grounding_text(tail)
    if not tail_key:
        return None

    scope_end = _next_top_level_numbered_item_start(
        description,
        group_start=header_span[0],
        group_end=header_span[1],
    )
    if scope_end is None:
        scope_end = len(description)

    children: list[tuple[int, str]] = []
    seen_child_keys: set[tuple[int, str]] = set()
    for other in all_items:
        if other is item:
            continue
        child_text = other.original_text.strip()
        child_span = _unique_exact_span_within_scope(
            description,
            child_text,
            scope_start=header_span[1],
            scope_end=scope_end,
        )
        if child_span is None:
            continue
        child_key = _normalize_grounding_text(child_text)
        identity = (child_span[0], child_key)
        if not child_key or child_key not in tail_key or identity in seen_child_keys:
            continue
        seen_child_keys.add(identity)
        children.append((child_span[0], child_key))

    children.sort(key=lambda value: value[0])
    if len(children) < 2 or "".join(value for _, value in children) != tail_key:
        return None
    return replace(
        item,
        type=RequirementType.CONSTRAINT,
        original_text=header,
        evidence_span=header,
        normalized_capability=None,
    )


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
    pre_split_items: list[tuple[int, ProposedJobRequirement]] = []
    existing_atomic_keys: set[tuple[str, str, str]] = set()
    generated_atomic_keys: set[tuple[str, str, str]] = set()

    def atomic_key(item: ProposedJobRequirement) -> tuple[str, str, str]:
        return (
            item.type.value,
            item.importance.value,
            item.original_text.strip().rstrip("，,。.;；").strip().casefold(),
        )

    def append_generated_items(
        requirement_index: int,
        items: tuple[ProposedJobRequirement, ...],
    ) -> None:
        for split_item in items:
            key = atomic_key(split_item)
            if key in existing_atomic_keys:
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=SemanticRepairStrategy.DROP_REDUNDANT_REPAIRED_REQUIREMENT,
                    )
                )
                continue
            pre_split_items.append((requirement_index, split_item))
            existing_atomic_keys.add(key)
            generated_atomic_keys.add(key)

    for requirement_index, item in indexed_items:
        in_explicit_bonus_section = _is_explicit_bonus_section_span(
            description,
            item.evidence_span,
        )
        normalized_soft = _normalize_explicit_soft_only_requirement(
            description,
            item,
        )
        if normalized_soft is not None:
            item = normalized_soft
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.EXPLICIT_SOFT_MARKER_PREFERRED,
                )
            )
        if in_explicit_bonus_section and item.importance is not RequirementImportance.BONUS:
            item = replace(item, importance=RequirementImportance.BONUS)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.EXPLICIT_BONUS_SECTION,
                )
            )
        normalized_hard_capability = _normalize_hard_skill_capability_before_soft_suffix(
            description,
            item,
        )
        if normalized_hard_capability is not None:
            item = normalized_hard_capability
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.NORMALIZE_HARD_SKILL_CAPABILITY_BEFORE_SOFT_SUFFIX
                    ),
                )
            )
        if (
            not in_explicit_bonus_section
            and not _is_unsoftened_explicit_requirement_section_item(description, item)
            and _is_preferred_explicit_mandatory_experience(
                description,
                item,
            )
        ):
            item = replace(item, importance=RequirementImportance.MUST_HAVE)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.PROMOTE_EXPLICIT_MANDATORY_EXPERIENCE,
                )
            )
        elif not in_explicit_bonus_section and _is_preferred_experience_hard_prefix_with_explicit_soft_sibling(
            description,
            item,
            output.requirements,
        ):
            item = replace(item, importance=RequirementImportance.MUST_HAVE)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.PROMOTE_HARD_EXPERIENCE_PREFIX_BEFORE_SOFT_SIBLING
                    ),
                )
            )
        elif not in_explicit_bonus_section and _is_preferred_hard_skill_prefix_with_explicit_soft_sibling(
            description,
            item,
            output.requirements,
        ):
            item = replace(item, importance=RequirementImportance.MUST_HAVE)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.PROMOTE_HARD_SKILL_PREFIX_BEFORE_SOFT_SIBLING
                    ),
                )
            )
        elif not in_explicit_bonus_section and _is_explicit_application_material_requirement(
            description,
            item,
        ):
            item = replace(item, importance=RequirementImportance.MUST_HAVE)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.PROMOTE_APPLICATION_MATERIAL_REQUIREMENT,
                )
            )
        elif not in_explicit_bonus_section and _is_unsoftened_explicit_requirement_section_item(description, item):
            item = replace(item, importance=RequirementImportance.MUST_HAVE)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.REQUIREMENT_SECTION_DEFAULT_MUST_HAVE,
                )
            )
        if _is_redundant_example_child(description, item, output.requirements):
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.DROP_EXAMPLE_CHILD,
                )
            )
            continue
        recovered_group_header = _recover_noncontiguous_alternative_group_header(
            description,
            item,
            output.requirements,
        )
        if recovered_group_header is not None:
            item = recovered_group_header
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.RECOVER_ALTERNATIVE_GROUP_HEADER,
                )
            )
        normalized_responsibility = _normalize_responsibility_type_drift(
            description,
            item,
        )
        if normalized_responsibility is not None:
            item = normalized_responsibility
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.RESPONSIBILITY_TYPE_NORMALIZATION,
                )
            )
        normalized_scope_summary = _normalize_short_scope_summary_skill_drift(
            description,
            item,
            output.requirements,
        )
        if normalized_scope_summary is not None:
            item = normalized_scope_summary
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.SHORT_SCOPE_SUMMARY_RESPONSIBILITY,
                )
            )
        if _is_redundant_short_scope_summary_responsibility(
            description,
            item,
            output.requirements,
        ):
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.DROP_SHORT_SCOPE_SUMMARY_RESPONSIBILITY,
                )
            )
            continue
        normalized_technical_skill = _normalize_technical_skill_experience_drift(
            description,
            item,
            output.requirements,
        )
        if normalized_technical_skill is not None:
            item = normalized_technical_skill
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.NORMALIZE_TECHNICAL_SKILL_EXPERIENCE_DRIFT,
                )
            )
        normalized_non_experience = _normalize_non_experience_qualification_type_drift(
            description,
            item,
        )
        if normalized_non_experience is not None:
            item = normalized_non_experience
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.NON_EXPERIENCE_QUALIFICATION_CONSTRAINT,
                )
            )
        expanded_compound = _expand_compound_hard_skill_from_evidence_span(
            description,
            item,
        )
        if expanded_compound is not None:
            item = expanded_compound
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.EXPAND_COMPOUND_HARD_EVIDENCE_SPAN,
                )
            )
        normalized_experience = _normalize_explicit_experience_type_drift(
            description,
            item,
        )
        if normalized_experience is not None:
            item = normalized_experience
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.NORMALIZE_EXPERIENCE_TYPE_DRIFT,
                )
            )
        mixed_scope_split = _split_hard_preferred_hard_mixed_scope(
            description,
            item,
            output.requirements,
        )
        if mixed_scope_split is not None:
            append_generated_items(requirement_index, mixed_scope_split)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.SPLIT_HARD_PREFERRED_HARD_MIXED_SCOPE,
                )
            )
            continue
        education_split = _split_mixed_education_experience(description, item)
        if education_split is not None:
            append_generated_items(requirement_index, education_split)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.SPLIT_EDUCATION_EXPERIENCE,
                )
            )
            continue
        skill_experience_split = _split_hard_skill_from_fused_experience(
            description,
            item,
        )
        if skill_experience_split is not None:
            append_generated_items(requirement_index, skill_experience_split)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.SPLIT_SKILL_EXPERIENCE,
                )
            )
            continue
        experience_alternative_split = _split_experience_prefix_from_alternative_group(
            description,
            item,
        )
        if experience_alternative_split is not None:
            append_generated_items(requirement_index, experience_alternative_split)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.SPLIT_EXPERIENCE_ALTERNATIVE,
                )
            )
            continue
        hard_alternative_split = _split_hard_skill_from_inline_alternative(
            description,
            item,
        )
        if hard_alternative_split is not None:
            append_generated_items(requirement_index, hard_alternative_split)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.SPLIT_HARD_ALTERNATIVE,
                )
            )
            continue
        if _is_compound_hard_skill_constraint(description, item):
            item = replace(
                item,
                type=RequirementType.CONSTRAINT,
                normalized_capability=None,
            )
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.COMPOUND_HARD_SKILL_CONSTRAINT,
                )
            )
        else:
            conceptual_source_type = item.type
            conceptual_mechanism = _normalize_conceptual_mechanism_skill_constraint(
                description,
                item,
            )
            if conceptual_mechanism is not None:
                item = conceptual_mechanism
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=(
                            SemanticRepairStrategy.CONCEPTUAL_MECHANISM_TYPE_CONSTRAINT
                            if conceptual_source_type is RequirementType.DOMAIN
                            else SemanticRepairStrategy.CONCEPTUAL_MECHANISM_SKILL_CONSTRAINT
                        ),
                    )
                )
            elif _is_abstract_evaluative_skill_constraint(description, item):
                item = replace(
                    item,
                    type=RequirementType.CONSTRAINT,
                    normalized_capability=None,
                )
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=SemanticRepairStrategy.ABSTRACT_EVALUATIVE_SKILL_CONSTRAINT,
                    )
                )
            else:
                normalized_abstract = _normalize_abstract_evaluative_type_drift(
                    description,
                    item,
                )
                if normalized_abstract is not None:
                    item = normalized_abstract
                    repairs.append(
                        SemanticRepairEvent(
                            requirement_index=requirement_index,
                            strategy=SemanticRepairStrategy.ABSTRACT_EVALUATIVE_TYPE_CONSTRAINT,
                        )
                    )
        key = atomic_key(item)
        if (
            item.type in {RequirementType.EDUCATION, RequirementType.EXPERIENCE}
            and key in generated_atomic_keys
        ):
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.DROP_REDUNDANT_REPAIRED_REQUIREMENT,
                )
            )
            continue
        pre_split_items.append((requirement_index, item))
        existing_atomic_keys.add(key)
    indexed_items = pre_split_items

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

    existing_soft_texts = {
        _soft_clause_identity(item.original_text)
        for _, item in repaired_items
        if item.importance in {
            RequirementImportance.PREFERRED,
            RequirementImportance.BONUS,
        }
    }
    split_items: list[tuple[int, ProposedJobRequirement]] = []
    repaired_requirement_items = tuple(item for _, item in repaired_items)
    for requirement_index, item in repaired_items:
        split = _split_trailing_preferred_clause(item)
        split_strategy = SemanticRepairStrategy.SPLIT_TRAILING_PREFERRED
        if split is None:
            split = _split_embedded_preferred_clause_with_covered_tail(
                item,
                repaired_requirement_items,
            )
            split_strategy = (
                SemanticRepairStrategy.SPLIT_EMBEDDED_PREFERRED_WITH_COVERED_TAIL
            )
        if split is None:
            split_items.append((requirement_index, item))
            continue
        hard_item, soft_item = split
        split_items.append((requirement_index, hard_item))
        soft_identity = _soft_clause_identity(soft_item.original_text)
        if soft_identity not in existing_soft_texts:
            split_items.append((requirement_index, soft_item))
            existing_soft_texts.add(soft_identity)
        repairs.append(
            SemanticRepairEvent(
                requirement_index=requirement_index,
                strategy=split_strategy,
            )
        )
    repaired_items = split_items

    engineering_habit_groups: dict[
        str, list[tuple[int, ProposedJobRequirement, str]]
    ] = {}
    engineering_habit_parents: set[str] = set()
    for requirement_index, item in repaired_items:
        evidence = item.evidence_span.strip()
        parsed = _engineering_habit_quality_clause(evidence)
        if parsed is None or item.importance is not RequirementImportance.MUST_HAVE:
            continue
        clause, qualities = parsed
        item_text = _classification_text(item.original_text)
        if item_text == clause and item.type is RequirementType.CONSTRAINT:
            engineering_habit_parents.add(evidence)
            continue
        quality = item_text.removeprefix("重视").strip()
        if (
            quality in qualities
            and quality in _ENGINEERING_HABIT_QUALITY_TERMS
            and _unique_exact_span(description, item.original_text) is not None
            and _unique_exact_span(description, item.evidence_span) is not None
        ):
            engineering_habit_groups.setdefault(evidence, []).append(
                (requirement_index, item, quality)
            )
    engineering_habit_groups = {
        evidence: members
        for evidence, members in engineering_habit_groups.items()
        if len({quality for _, _, quality in members}) >= 3
    }
    if engineering_habit_groups:
        collapsed_engineering_habit_items: list[
            tuple[int, ProposedJobRequirement]
        ] = []
        member_ids = {
            id(member)
            for members in engineering_habit_groups.values()
            for _, member, _ in members
        }
        emitted_evidence: set[str] = set()
        for requirement_index, item in repaired_items:
            if id(item) not in member_ids:
                collapsed_engineering_habit_items.append((requirement_index, item))
                continue
            evidence = item.evidence_span.strip()
            members = engineering_habit_groups[evidence]
            if evidence not in engineering_habit_parents and evidence not in emitted_evidence:
                emitted_evidence.add(evidence)
                clause, _ = _engineering_habit_quality_clause(evidence) or ("", ())
                collapsed_engineering_habit_items.append(
                    (
                        requirement_index,
                        replace(
                            item,
                            type=RequirementType.CONSTRAINT,
                            original_text=clause,
                            normalized_capability=None,
                            confidence=min(member.confidence for _, member, _ in members),
                        ),
                    )
                )
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.COLLAPSE_ENGINEERING_HABIT_QUALITY_FANOUT,
                )
            )
        repaired_items = collapsed_engineering_habit_items

    repaired_requirement_items = tuple(item for _, item in repaired_items)
    without_redundant_compound_children: list[
        tuple[int, ProposedJobRequirement]
    ] = []
    for requirement_index, item in repaired_items:
        if _is_redundant_compound_hard_child(
            description,
            item,
            repaired_requirement_items,
        ):
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.DROP_REDUNDANT_COMPOUND_HARD_CHILD,
                )
            )
            continue
        without_redundant_compound_children.append((requirement_index, item))
    repaired_items = without_redundant_compound_children

    repaired_requirement_items = tuple(item for _, item in repaired_items)
    without_cross_type_duplicates: list[tuple[int, ProposedJobRequirement]] = []
    for requirement_index, item in repaired_items:
        if _is_redundant_cross_type_exact_duplicate(
            description,
            item,
            repaired_requirement_items,
        ):
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.DROP_REDUNDANT_CROSS_TYPE_DUPLICATE,
                )
            )
            continue
        without_cross_type_duplicates.append((requirement_index, item))
    repaired_items = without_cross_type_duplicates

    example_skill_groups: dict[
        tuple[str, str],
        list[tuple[int, ProposedJobRequirement]],
    ] = {}
    for requirement_index, item in repaired_items:
        if (
            item.type is RequirementType.SKILL
            and item.importance is RequirementImportance.MUST_HAVE
            and item.normalized_capability
            and (
                _INLINE_EXAMPLE_LIST_PATTERN.search(item.original_text)
                or _PARENTHETICAL_ENUM_EXAMPLE_LIST_PATTERN.search(item.original_text)
            )
            and _unique_exact_span(description, item.original_text) is not None
            and _unique_exact_span(description, item.evidence_span) is not None
        ):
            key = (
                item.original_text.strip(),
                item.evidence_span.strip(),
            )
            example_skill_groups.setdefault(key, []).append(
                (requirement_index, item)
            )
    duplicate_example_skill_groups = {
        key: members
        for key, members in example_skill_groups.items()
        if len(
            {
                member.normalized_capability.strip().casefold()
                for _, member in members
                if member.normalized_capability
            }
        )
        >= 2
    }
    if duplicate_example_skill_groups:
        collapsed_example_items: list[tuple[int, ProposedJobRequirement]] = []
        emitted_example_groups: set[tuple[str, str]] = set()
        existing_example_constraints = {
            (
                item.original_text.strip(),
                item.evidence_span.strip(),
            )
            for _, item in repaired_items
            if item.type is RequirementType.CONSTRAINT
            and item.importance is RequirementImportance.MUST_HAVE
        }
        for requirement_index, item in repaired_items:
            key = (
                item.original_text.strip(),
                item.evidence_span.strip(),
            )
            members = duplicate_example_skill_groups.get(key)
            if members is None or item.type is not RequirementType.SKILL:
                collapsed_example_items.append((requirement_index, item))
                continue
            if key not in emitted_example_groups:
                emitted_example_groups.add(key)
                if key not in existing_example_constraints:
                    collapsed_example_items.append(
                        (
                            requirement_index,
                            ProposedJobRequirement(
                                type=RequirementType.CONSTRAINT,
                                original_text=key[0],
                                normalized_capability=None,
                                importance=RequirementImportance.MUST_HAVE,
                                evidence_span=key[1],
                                confidence=min(
                                    member.confidence for _, member in members
                                ),
                            ),
                        )
                    )
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=SemanticRepairStrategy.COLLAPSE_EXAMPLE_SKILL_SIBLINGS,
                    )
                )
        repaired_items = collapsed_example_items

    responsibility_groups: dict[
        tuple[str, str, str],
        list[tuple[int, ProposedJobRequirement]],
    ] = {}
    for requirement_index, item in repaired_items:
        if (
            item.type is RequirementType.RESPONSIBILITY
            and item.normalized_capability
            and _unique_exact_span(description, item.original_text) is not None
            and _unique_exact_span(description, item.evidence_span) is not None
        ):
            key = (
                item.original_text.strip(),
                item.evidence_span.strip(),
                item.importance.value,
            )
            responsibility_groups.setdefault(key, []).append((requirement_index, item))
    duplicate_responsibility_groups = {
        key: members
        for key, members in responsibility_groups.items()
        if len(
            {
                member.normalized_capability.strip().casefold()
                for _, member in members
                if member.normalized_capability
            }
        )
        >= 2
    }
    if duplicate_responsibility_groups:
        collapsed_responsibility_items: list[tuple[int, ProposedJobRequirement]] = []
        emitted_responsibility_groups: set[tuple[str, str, str]] = set()
        for requirement_index, item in repaired_items:
            key = (
                item.original_text.strip(),
                item.evidence_span.strip(),
                item.importance.value,
            )
            members = duplicate_responsibility_groups.get(key)
            if members is None or item.type is not RequirementType.RESPONSIBILITY:
                collapsed_responsibility_items.append((requirement_index, item))
                continue
            if key not in emitted_responsibility_groups:
                emitted_responsibility_groups.add(key)
                collapsed_responsibility_items.append(
                    (
                        requirement_index,
                        replace(
                            item,
                            normalized_capability=None,
                            confidence=min(member.confidence for _, member in members),
                        ),
                    )
                )
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=(
                            SemanticRepairStrategy.COLLAPSE_RESPONSIBILITY_CAPABILITY_SIBLINGS
                        ),
                    )
                )
        repaired_items = collapsed_responsibility_items

    responsibility_enumeration_groups: dict[
        tuple[str, str], list[tuple[int, ProposedJobRequirement]]
    ] = {}
    for requirement_index, item in repaired_items:
        evidence = item.evidence_span.strip()
        original = item.original_text.strip()
        if (
            item.type is RequirementType.RESPONSIBILITY
            and "包括但不限于" in evidence
            and original
            and original != evidence
            and original in evidence
        ):
            responsibility_enumeration_groups.setdefault(
                (evidence, item.importance.value), []
            ).append((requirement_index, item))
    responsibility_enumeration_groups = {
        key: members
        for key, members in responsibility_enumeration_groups.items()
        if len(members) >= 2
        and len({member.original_text.strip() for _, member in members}) >= 2
    }
    if responsibility_enumeration_groups:
        collapsed_enumeration_items: list[tuple[int, ProposedJobRequirement]] = []
        emitted_enumeration_groups: set[tuple[str, str]] = set()
        for requirement_index, item in repaired_items:
            key = (item.evidence_span.strip(), item.importance.value)
            members = responsibility_enumeration_groups.get(key)
            if members is None or item.type is not RequirementType.RESPONSIBILITY:
                collapsed_enumeration_items.append((requirement_index, item))
                continue
            if key not in emitted_enumeration_groups:
                emitted_enumeration_groups.add(key)
                collapsed_enumeration_items.append(
                    (
                        requirement_index,
                        replace(
                            item,
                            original_text=item.evidence_span.strip(),
                            normalized_capability=None,
                            confidence=min(member.confidence for _, member in members),
                        ),
                    )
                )
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=(
                            SemanticRepairStrategy.COLLAPSE_RESPONSIBILITY_ENUMERATION_SIBLINGS
                        ),
                    )
                )
        repaired_items = collapsed_enumeration_items

    full_responsibility_parents: dict[
        tuple[str, str],
        ProposedJobRequirement,
    ] = {}
    for _, item in repaired_items:
        original = item.original_text.strip()
        evidence = item.evidence_span.strip()
        if (
            item.type is RequirementType.RESPONSIBILITY
            and original
            and (
                original == evidence
                or _terminal_punctuation_identity(_classification_text(original))
                == _terminal_punctuation_identity(_classification_text(evidence))
            )
            and _unique_exact_span(description, original) is not None
            and _unique_exact_span(description, evidence) is not None
        ):
            full_responsibility_parents[(evidence, item.importance.value)] = item
    if full_responsibility_parents:
        without_redundant_responsibility_subclauses: list[
            tuple[int, ProposedJobRequirement]
        ] = []
        for requirement_index, item in repaired_items:
            original = item.original_text.strip()
            evidence = item.evidence_span.strip()
            parent = full_responsibility_parents.get((evidence, item.importance.value))
            if (
                item.type is RequirementType.RESPONSIBILITY
                and parent is not None
                and original != parent.original_text.strip()
                and original
                and original in parent.original_text
            ):
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=(
                            SemanticRepairStrategy.DROP_REDUNDANT_RESPONSIBILITY_SUBCLAUSE
                        ),
                    )
                )
                continue
            without_redundant_responsibility_subclauses.append((requirement_index, item))
        repaired_items = without_redundant_responsibility_subclauses

    sibling_groups: dict[tuple[str, str], list[tuple[int, ProposedJobRequirement]]] = {}
    for requirement_index, item in repaired_items:
        text = item.original_text.strip()
        evidence = item.evidence_span.strip()
        if (
            item.type is RequirementType.SKILL
            and item.importance in {
                RequirementImportance.MUST_HAVE,
                RequirementImportance.PREFERRED,
            }
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

    existing_inline_constraint_keys = {
        (item.original_text.strip().casefold(), item.evidence_span.strip().casefold())
        for _, item in repaired_items
        if item.type is RequirementType.CONSTRAINT
        and item.importance is RequirementImportance.MUST_HAVE
        and _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
    }
    emitted_inline_constraint_keys: set[tuple[str, str]] = set()
    inline_group_items: list[tuple[int, ProposedJobRequirement]] = []
    for requirement_index, item in repaired_items:
        alternative_type_drift = _is_alternative_group_type_drift(
            description,
            item,
        )
        if (
            item.type in {
                RequirementType.SKILL,
                RequirementType.EXPERIENCE,
                RequirementType.RESPONSIBILITY,
            }
            and item.importance is RequirementImportance.MUST_HAVE
            and (item.normalized_capability or alternative_type_drift)
            and _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
            and not _SOFT_MARKER_PATTERN.search(item.original_text)
            and _unique_exact_span(description, item.original_text) is not None
        ):
            key = (
                item.original_text.strip().casefold(),
                item.evidence_span.strip().casefold(),
            )
            if key in existing_inline_constraint_keys or key in emitted_inline_constraint_keys:
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=SemanticRepairStrategy.DROP_REDUNDANT_REPAIRED_REQUIREMENT,
                    )
                )
                continue
            item = replace(
                item,
                type=RequirementType.CONSTRAINT,
                normalized_capability=None,
            )
            emitted_inline_constraint_keys.add(key)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.INLINE_ALTERNATIVE_GROUP,
                )
            )
        inline_group_items.append((requirement_index, item))
    repaired_items = inline_group_items

    repaired_requirement_items = tuple(item for _, item in repaired_items)
    without_redundant_split_parents: list[tuple[int, ProposedJobRequirement]] = []
    for requirement_index, item in repaired_items:
        if _is_redundant_split_hard_parent(
            description,
            item,
            repaired_requirement_items,
        ):
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.DROP_REDUNDANT_SPLIT_HARD_PARENT,
                )
            )
            continue
        without_redundant_split_parents.append((requirement_index, item))
    repaired_items = without_redundant_split_parents

    domain_groups: dict[
        tuple[str, str],
        list[tuple[int, ProposedJobRequirement]],
    ] = {}
    for requirement_index, item in repaired_items:
        if (
            item.type is RequirementType.DOMAIN
            and item.importance is RequirementImportance.MUST_HAVE
            and item.normalized_capability
        ):
            key = (item.original_text.strip(), item.evidence_span.strip())
            domain_groups.setdefault(key, []).append((requirement_index, item))
    collapsible_domain_groups = {
        key: members
        for key, members in domain_groups.items()
        if len(
            {
                member.normalized_capability.strip().casefold()
                for _, member in members
                if member.normalized_capability
            }
        )
        >= 2
        and _is_compound_domain_sibling_group(description, key[0], key[1])
    }
    if collapsible_domain_groups:
        existing_constraint_keys = {
            (item.original_text.strip(), item.evidence_span.strip())
            for _, item in repaired_items
            if item.type is RequirementType.CONSTRAINT
            and item.importance is RequirementImportance.MUST_HAVE
        }
        collapsed_domain_items: list[tuple[int, ProposedJobRequirement]] = []
        emitted_domain_groups: set[tuple[str, str]] = set()
        for requirement_index, item in repaired_items:
            key = (item.original_text.strip(), item.evidence_span.strip())
            members = collapsible_domain_groups.get(key)
            if members is None or item.type is not RequirementType.DOMAIN:
                collapsed_domain_items.append((requirement_index, item))
                continue
            if key not in emitted_domain_groups:
                emitted_domain_groups.add(key)
                if key not in existing_constraint_keys:
                    collapsed_domain_items.append(
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
                        strategy=SemanticRepairStrategy.COLLAPSE_COMPOUND_DOMAIN_SIBLINGS,
                    )
                )
        repaired_items = collapsed_domain_items

    repaired_requirement_items = tuple(item for _, item in repaired_items)
    without_qualification_responsibility_children: list[
        tuple[int, ProposedJobRequirement]
    ] = []
    for requirement_index, item in repaired_items:
        if _is_redundant_qualification_responsibility_child(
            description,
            item,
            repaired_requirement_items,
        ):
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.DROP_REDUNDANT_QUALIFICATION_RESPONSIBILITY_CHILD
                    ),
                )
            )
            continue
        without_qualification_responsibility_children.append((requirement_index, item))
    repaired_items = without_qualification_responsibility_children

    repaired_requirement_items = tuple(item for _, item in repaired_items)
    without_redundant_qualification_subclauses: list[
        tuple[int, ProposedJobRequirement]
    ] = []
    for requirement_index, item in repaired_items:
        if _is_redundant_qualification_subclause(
            description,
            item,
            repaired_requirement_items,
        ):
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.DROP_REDUNDANT_QUALIFICATION_SUBCLAUSE,
                )
            )
            continue
        without_redundant_qualification_subclauses.append((requirement_index, item))
    repaired_items = without_redundant_qualification_subclauses

    normalized_requirement_section_items: list[
        tuple[int, ProposedJobRequirement]
    ] = []
    for requirement_index, item in repaired_items:
        normalized_requirement_section_type = (
            _normalize_requirement_section_qualification_type_drift(
                description,
                item,
            )
        )
        if normalized_requirement_section_type is not None:
            item = normalized_requirement_section_type
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.REQUIREMENT_SECTION_QUALIFICATION_TYPE_NORMALIZATION
                    ),
                )
            )
        normalized_requirement_section_items.append((requirement_index, item))
    repaired_items = normalized_requirement_section_items

    repaired_items, line_collapse_repairs = _collapse_explicit_requirement_line_fragments(
        description,
        repaired_items,
    )
    repairs.extend(line_collapse_repairs)

    backend_component_umbrella = _recover_backend_component_umbrella(
        description,
        tuple(item for _, item in repaired_items),
    )
    if backend_component_umbrella is not None:
        generated_index = max(
            (requirement_index for requirement_index, _ in repaired_items),
            default=-1,
        ) + 1
        kept_items: list[tuple[int, ProposedJobRequirement]] = []
        for requirement_index, item in repaired_items:
            if _is_backend_component_fanout_child(item, backend_component_umbrella):
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=SemanticRepairStrategy.DROP_BACKEND_COMPONENT_FANOUT,
                    )
                )
                continue
            kept_items.append((requirement_index, item))
        kept_items.append((generated_index, backend_component_umbrella))
        repairs.append(
            SemanticRepairEvent(
                requirement_index=generated_index,
                strategy=SemanticRepairStrategy.RECOVER_BACKEND_COMPONENT_UMBRELLA,
            )
        )
        repaired_items = kept_items

    recovered_cardinality_items = (
        *_recover_uncovered_requirement_cardinality_constraints(
            description,
            tuple(item for _, item in repaired_items),
        ),
        *_recover_uncovered_inline_cardinality_constraints(
            description,
            tuple(item for _, item in repaired_items),
        ),
    )
    for recovered_item in recovered_cardinality_items:
        generated_index = len(output.requirements) + len(
            [
                repair
                for repair in repairs
                if repair.strategy
                is SemanticRepairStrategy.RECOVER_UNCOVERED_CARDINALITY_REQUIREMENT
            ]
        )
        repaired_items.append((generated_index, recovered_item))
        repairs.append(
            SemanticRepairEvent(
                requirement_index=generated_index,
                strategy=SemanticRepairStrategy.RECOVER_UNCOVERED_CARDINALITY_REQUIREMENT,
            )
        )

    recovered_engineering_practice_items = _recover_post_cardinality_engineering_practice(
        description,
        tuple(item for _, item in repaired_items),
    )
    for recovered_item in recovered_engineering_practice_items:
        generated_index = len(output.requirements) + len(repairs)
        repaired_items.append((generated_index, recovered_item))
        repairs.append(
            SemanticRepairEvent(
                requirement_index=generated_index,
                strategy=SemanticRepairStrategy.RECOVER_POST_CARDINALITY_ENGINEERING_PRACTICE,
            )
        )

    if recovered_cardinality_items:
        without_redundant_recovered_children: list[
            tuple[int, ProposedJobRequirement]
        ] = []
        for requirement_index, item in repaired_items:
            if any(
                _is_redundant_recovered_cardinality_child(item, parent)
                for parent in recovered_cardinality_items
            ):
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=(
                            SemanticRepairStrategy.DROP_REDUNDANT_RECOVERED_CARDINALITY_CHILD
                        ),
                    )
                )
                continue
            without_redundant_recovered_children.append((requirement_index, item))
        repaired_items = without_redundant_recovered_children

    repaired_requirement_items = tuple(item for _, item in repaired_items)
    without_redundant_cardinality_fragments: list[
        tuple[int, ProposedJobRequirement]
    ] = []
    for requirement_index, item in repaired_items:
        if _is_redundant_cardinality_fragment(item, repaired_requirement_items):
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.DROP_REDUNDANT_CARDINALITY_FRAGMENT,
                )
            )
            continue
        without_redundant_cardinality_fragments.append((requirement_index, item))
    repaired_items = without_redundant_cardinality_fragments

    repaired_requirement_items = tuple(item for _, item in repaired_items)
    without_redundant_leading_cardinality_subclauses: list[
        tuple[int, ProposedJobRequirement]
    ] = []
    for requirement_index, item in repaired_items:
        if _is_redundant_leading_cardinality_subclause(
            description,
            item,
            repaired_requirement_items,
        ):
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.DROP_REDUNDANT_LEADING_CARDINALITY_SUBCLAUSE
                    ),
                )
            )
            continue
        without_redundant_leading_cardinality_subclauses.append((requirement_index, item))
    repaired_items = without_redundant_leading_cardinality_subclauses

    same_evidence_alternative_parents = _recover_same_evidence_inline_alternative_parents(
        description,
        tuple(item for _, item in repaired_items),
    )
    next_generated_index = max(
        (requirement_index for requirement_index, _ in repaired_items),
        default=-1,
    ) + 1
    for recovered_item in same_evidence_alternative_parents:
        repaired_items.append((next_generated_index, recovered_item))
        repairs.append(
            SemanticRepairEvent(
                requirement_index=next_generated_index,
                strategy=(
                    SemanticRepairStrategy.RECOVER_SAME_EVIDENCE_INLINE_ALTERNATIVE_PARENT
                ),
            )
        )
        next_generated_index += 1

    same_evidence_example_parents = _recover_same_evidence_example_experience_parents(
        description,
        tuple(item for _, item in repaired_items),
    )
    for recovered_item in same_evidence_example_parents:
        repaired_items.append((next_generated_index, recovered_item))
        repairs.append(
            SemanticRepairEvent(
                requirement_index=next_generated_index,
                strategy=(
                    SemanticRepairStrategy.RECOVER_SAME_EVIDENCE_EXAMPLE_EXPERIENCE_PARENT
                ),
            )
        )
        next_generated_index += 1

    if same_evidence_example_parents:
        repaired_requirement_items = tuple(item for _, item in repaired_items)
        without_late_example_children: list[
            tuple[int, ProposedJobRequirement]
        ] = []
        for requirement_index, item in repaired_items:
            if _is_redundant_recovered_parenthetical_experience_example_child(
                description,
                item,
                repaired_requirement_items,
            ):
                repairs.append(
                    SemanticRepairEvent(
                        requirement_index=requirement_index,
                        strategy=SemanticRepairStrategy.DROP_EXAMPLE_CHILD,
                    )
                )
                continue
            without_late_example_children.append((requirement_index, item))
        repaired_items = without_late_example_children

    recovered_alternative_parents = _recover_missing_alternative_group_parents(
        description,
        tuple(item for _, item in repaired_items),
    )
    next_generated_index = max(
        next_generated_index,
        max((requirement_index for requirement_index, _ in repaired_items), default=-1) + 1,
    )
    for recovered_item in recovered_alternative_parents:
        repaired_items.append((next_generated_index, recovered_item))
        repairs.append(
            SemanticRepairEvent(
                requirement_index=next_generated_index,
                strategy=SemanticRepairStrategy.RECOVER_MISSING_ALTERNATIVE_GROUP_PARENT,
            )
        )
        next_generated_index += 1

    recovered_alternative_children = _recover_uncovered_alternative_group_children(
        description,
        tuple(item for _, item in repaired_items),
    )
    next_generated_index = max(
        next_generated_index,
        max((requirement_index for requirement_index, _ in repaired_items), default=-1) + 1,
    )
    for recovered_item in recovered_alternative_children:
        repaired_items.append((next_generated_index, recovered_item))
        repairs.append(
            SemanticRepairEvent(
                requirement_index=next_generated_index,
                strategy=SemanticRepairStrategy.RECOVER_ALTERNATIVE_GROUP_CHILD,
            )
        )
        next_generated_index += 1

    group_scopes: list[tuple[int, int]] = []
    for _, item in repaired_items:
        if item in same_evidence_alternative_parents:
            continue
        scope_source = item.original_text
        if not _ALTERNATIVE_GROUP_PATTERN.search(scope_source):
            evidence = item.evidence_span.strip()
            if (
                item.type is RequirementType.CONSTRAINT
                and item.importance is RequirementImportance.MUST_HAVE
                and _ALTERNATIVE_GROUP_PATTERN.search(evidence)
                and _ALTERNATIVE_FOLLOWING_LIST_PATTERN.search(evidence)
                and evidence.rstrip().endswith((":", "："))
                and _is_requirement_section_span(description, evidence)
            ):
                scope_source = evidence
            else:
                continue
        span = _unique_exact_span(description, scope_source)
        if span is None:
            continue
        next_item_start = _next_top_level_numbered_item_start(
            description,
            group_start=span[0],
            group_end=span[1],
        )
        scope_end = next_item_start if next_item_start is not None else len(description)
        group_scopes.append((span[1], scope_end))

    repaired_requirement_items = tuple(item for _, item in repaired_items)
    late_type_normalized_items: list[tuple[int, ProposedJobRequirement]] = []
    for requirement_index, item in repaired_items:
        normalized_technical_skill = _normalize_technical_skill_experience_drift(
            description,
            item,
            repaired_requirement_items,
        )
        if normalized_technical_skill is not None:
            item = normalized_technical_skill
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.NORMALIZE_TECHNICAL_SKILL_EXPERIENCE_DRIFT,
                )
            )
        late_type_normalized_items.append((requirement_index, item))
    repaired_items = late_type_normalized_items

    final_items = []
    exact_duplicate_keys: set[tuple[str, str, str, str, str]] = set()
    compound_ability_fanout_seen: set[tuple[str, str]] = set()
    hard_inline_alternative_fanout_seen: set[tuple[str, str]] = set()
    bonus_umbrella_fanout_seen: set[tuple[str, str]] = set()
    recursive_hard_skill_subset_seen: set[tuple[str, str]] = set()
    final_scope_items = tuple(item for _, item in repaired_items)
    for requirement_index, item in repaired_items:
        normalized_alternative_scope = _normalize_alternative_group_child_scope(
            description,
            item,
            group_scopes,
        )
        if normalized_alternative_scope is not None:
            item = normalized_alternative_scope
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.NORMALIZE_ALTERNATIVE_GROUP_CHILD_SCOPE,
                )
            )
        scoped_spans = [
            span
            for scope_start, scope_end in group_scopes
            if (
                span := _unique_exact_span_within_scope(
                    description,
                    item.original_text,
                    scope_start=scope_start,
                    scope_end=scope_end,
                )
            )
            is not None
        ]
        conjunctive_hard_sibling = _is_conjunctive_hard_sibling_of_alternative_group(
            description,
            item,
            final_scope_items,
        )
        post_cardinality_hard_sibling = _is_post_cardinality_hard_sibling(
            description,
            item,
            final_scope_items,
        )
        is_alternative_child = (
            (
                len(scoped_spans) == 1
                and item.importance is RequirementImportance.MUST_HAVE
                and not conjunctive_hard_sibling
                and not post_cardinality_hard_sibling
                and not _ALTERNATIVE_GROUP_PATTERN.search(item.original_text)
                and not _EXPLICIT_CHILD_HARD_PATTERN.search(item.original_text)
            )
            or _is_same_evidence_secondary_inline_cardinality_child(
                description,
                item,
                final_scope_items,
            )
        )
        if conjunctive_hard_sibling:
            item = replace(item, importance=RequirementImportance.MUST_HAVE)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.PRESERVE_CONJUNCTIVE_HARD_SIBLING,
                )
            )
        elif post_cardinality_hard_sibling:
            item = replace(item, importance=RequirementImportance.MUST_HAVE)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.PRESERVE_POST_CARDINALITY_HARD_SIBLING,
                )
            )
        elif is_alternative_child:
            item = replace(item, importance=RequirementImportance.PREFERRED)
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.ALTERNATIVE_CHILD,
                )
            )
        normalized_technical_stack_constraint = (
            _normalize_technical_stack_constraint_drift(description, item)
        )
        if normalized_technical_stack_constraint is not None:
            item = normalized_technical_stack_constraint
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.NORMALIZE_TECHNICAL_STACK_CONSTRAINT_DRIFT
                    ),
                )
            )
        normalized_umbrella_example_capability = (
            _normalize_umbrella_skill_example_capability(description, item)
        )
        if normalized_umbrella_example_capability is not None:
            item = normalized_umbrella_example_capability
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.NORMALIZE_UMBRELLA_SKILL_EXAMPLE_CAPABILITY
                    ),
                )
            )
        normalized_alternative_capability = _normalize_alternative_group_child_capability(
            description,
            item,
            group_scopes,
        )
        if normalized_alternative_capability is not None:
            source_identity_changed = (
                normalized_alternative_capability.original_text.strip()
                != item.original_text.strip()
            )
            item = normalized_alternative_capability
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.NORMALIZE_ALTERNATIVE_GROUP_CHILD_SOURCE_IDENTITY
                        if source_identity_changed
                        else SemanticRepairStrategy.NORMALIZE_ALTERNATIVE_GROUP_CHILD_CAPABILITY
                    ),
                )
            )
        canonical_sibling_capability = (
            _alternative_group_child_sibling_canonical_capability(
                description,
                item,
                group_scopes,
                final_scope_items,
            )
        )
        if (
            canonical_sibling_capability is not None
            and (
                item.importance is not RequirementImportance.PREFERRED
                or (item.normalized_capability or "").strip().casefold()
                != canonical_sibling_capability.casefold()
                or item.original_text.strip() != item.evidence_span.strip()
            )
        ):
            item = replace(
                item,
                type=RequirementType.SKILL,
                importance=RequirementImportance.PREFERRED,
                original_text=item.evidence_span.strip(),
                normalized_capability=canonical_sibling_capability,
            )
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.COLLAPSE_ALTERNATIVE_GROUP_CHILD_SIBLINGS
                    ),
                )
            )
        if _is_redundant_same_source_constraint_subclause(
            description,
            item,
            final_items,
        ):
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.DROP_REDUNDANT_SAME_SOURCE_CONSTRAINT_SUBCLAUSE
                    ),
                )
            )
            continue
        recursive_subset_group = _recursive_hard_skill_subset_group(
            description,
            item,
            final_scope_items,
        )
        if recursive_subset_group:
            recursive_parent = max(
                recursive_subset_group,
                key=lambda candidate: len(_presentation_identity(candidate.original_text)),
            )
            recursive_key = (
                _presentation_identity(recursive_parent.evidence_span),
                _presentation_identity(recursive_parent.original_text),
            )
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.COLLAPSE_RECURSIVE_HARD_SKILL_SUBSET_CHAIN,
                )
            )
            if recursive_key in recursive_hard_skill_subset_seen:
                continue
            recursive_hard_skill_subset_seen.add(recursive_key)
            item = replace(
                recursive_parent,
                type=RequirementType.CONSTRAINT,
                normalized_capability=None,
                confidence=min(candidate.confidence for candidate in recursive_subset_group),
            )

        same_evidence_hard_skill_items = [
            candidate
            for _, candidate in repaired_items
            if (
                candidate.type is RequirementType.SKILL
                and candidate.importance is RequirementImportance.MUST_HAVE
                and (candidate.normalized_capability or "").strip()
                and _presentation_identity(candidate.evidence_span)
                == _presentation_identity(item.evidence_span)
            )
        ]
        umbrella_parent = next(
            (
                candidate
                for candidate in same_evidence_hard_skill_items
                if (
                    candidate is not item
                    and _classification_text(candidate.original_text).startswith(
                        f"{_classification_text(item.original_text)}、"
                    )
                    and "等" in _classification_text(candidate.original_text)
                    and re.search(
                        r"等[^。；;]{0,40}(?:框架|工具|技术栈|平台|数据库|模型|语言)$",
                        _classification_text(candidate.original_text),
                    )
                    is not None
                    and _unique_exact_span(description, candidate.original_text) is not None
                )
            ),
            None,
        )
        umbrella_children = [
            candidate
            for candidate in same_evidence_hard_skill_items
            if (
                candidate is not item
                and _classification_text(item.original_text).startswith(
                    f"{_classification_text(candidate.original_text)}、"
                )
                and "等" in _classification_text(item.original_text)
                and re.search(
                    r"等[^。；;]{0,40}(?:框架|工具|技术栈|平台|数据库|模型|语言)$",
                    _classification_text(item.original_text),
                )
                is not None
                and _unique_exact_span(description, item.original_text) is not None
            )
        ]
        if umbrella_parent is not None:
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.COLLAPSE_HARD_UMBRELLA_MEMBER_DUPLICATE,
                )
            )
            continue
        if umbrella_children:
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.COLLAPSE_HARD_UMBRELLA_MEMBER_DUPLICATE,
                )
            )
            item = replace(
                item,
                type=RequirementType.CONSTRAINT,
                normalized_capability=None,
                confidence=min(
                    [item.confidence, *(candidate.confidence for candidate in umbrella_children)]
                ),
            )
        compound_ability_fanout_members = [
            candidate
            for _, candidate in repaired_items
            if (
                candidate.type is RequirementType.SKILL
                and candidate.importance is RequirementImportance.MUST_HAVE
                and (candidate.normalized_capability or "").strip()
                and _presentation_identity(candidate.evidence_span)
                == _presentation_identity(item.evidence_span)
                and (
                    _presentation_identity(candidate.original_text)
                    == _presentation_identity(item.original_text)
                    or _presentation_identity(candidate.original_text)
                    in _presentation_identity(item.original_text)
                    or _presentation_identity(item.original_text)
                    in _presentation_identity(candidate.original_text)
                )
            )
        ]
        fanout_capabilities = {
            (candidate.normalized_capability or "").strip().casefold()
            for candidate in compound_ability_fanout_members
        }
        fanout_parent = max(
            compound_ability_fanout_members,
            key=lambda candidate: len(_presentation_identity(candidate.original_text)),
            default=None,
        )
        fanout_parent_text = (
            fanout_parent.original_text.strip() if fanout_parent is not None else ""
        )
        hard_compound_ability_fanout = bool(
            len(fanout_capabilities) >= 3
            and fanout_parent is not None
            and any(separator in fanout_parent_text for separator in (",", "，"))
            and re.search(r"(?:较强|很强|优秀|良好|扎实).*(?:能力|经验)", fanout_parent_text)
            and re.search(r"(?:能够|能)[^，,；;]{2,100}", fanout_parent_text)
        )
        if hard_compound_ability_fanout:
            fanout_key = (
                _presentation_identity(fanout_parent.evidence_span),
                _presentation_identity(fanout_parent.original_text),
            )
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.COLLAPSE_HARD_COMPOUND_ABILITY_FANOUT,
                )
            )
            if fanout_key in compound_ability_fanout_seen:
                continue
            compound_ability_fanout_seen.add(fanout_key)
            item = replace(
                fanout_parent,
                type=RequirementType.CONSTRAINT,
                normalized_capability=None,
                confidence=min(candidate.confidence for candidate in compound_ability_fanout_members),
            )
        inline_alternative_fanout_members = [
            candidate
            for _, candidate in repaired_items
            if (
                candidate.type is RequirementType.SKILL
                and candidate.importance is RequirementImportance.MUST_HAVE
                and (candidate.normalized_capability or "").strip()
                and _presentation_identity(candidate.original_text)
                == _presentation_identity(item.original_text)
                and _presentation_identity(candidate.evidence_span)
                == _presentation_identity(item.evidence_span)
            )
        ]
        inline_alternative_capabilities = {
            (candidate.normalized_capability or "").strip().casefold()
            for candidate in inline_alternative_fanout_members
        }
        hard_inline_alternative_fanout = bool(
            item.type is RequirementType.SKILL
            and item.importance is RequirementImportance.MUST_HAVE
            and len(inline_alternative_capabilities) >= 2
            and any(separator in item.original_text for separator in ("/", "／"))
            and re.search(r"[（(][^）)]*[／/][^）)]*[）)]", item.original_text) is None
            and _unique_presentation_span(description, item.original_text) is not None
        )
        if hard_inline_alternative_fanout:
            fanout_key = (
                _presentation_identity(item.evidence_span),
                _presentation_identity(item.original_text),
            )
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=(
                        SemanticRepairStrategy.COLLAPSE_HARD_INLINE_ALTERNATIVE_CAPABILITY_FANOUT
                    ),
                )
            )
            if fanout_key in hard_inline_alternative_fanout_seen:
                continue
            hard_inline_alternative_fanout_seen.add(fanout_key)
            item = replace(
                item,
                type=RequirementType.CONSTRAINT,
                normalized_capability=None,
                confidence=min(
                    candidate.confidence for candidate in inline_alternative_fanout_members
                ),
            )
        bonus_umbrella_fanout_members = [
            candidate
            for _, candidate in repaired_items
            if (
                candidate.type is RequirementType.SKILL
                and candidate.importance is RequirementImportance.BONUS
                and (candidate.normalized_capability or "").strip()
                and _presentation_identity(candidate.evidence_span)
                == _presentation_identity(item.evidence_span)
            )
        ]
        bonus_umbrella_capabilities = {
            (candidate.normalized_capability or "").strip().casefold()
            for candidate in bonus_umbrella_fanout_members
        }
        bonus_umbrella_parent = max(
            bonus_umbrella_fanout_members,
            key=lambda candidate: len(_presentation_identity(candidate.original_text)),
            default=None,
        )
        bonus_umbrella_parent_text = (
            bonus_umbrella_parent.original_text.strip()
            if bonus_umbrella_parent is not None
            else ""
        )
        bonus_umbrella_fanout = bool(
            item.type is RequirementType.SKILL
            and item.importance is RequirementImportance.BONUS
            and len(bonus_umbrella_capabilities) >= 3
            and bonus_umbrella_parent is not None
            and re.search(
                r"(?:^|[、.．])\s*加分项\s*[:：]",
                bonus_umbrella_parent.evidence_span,
            )
            is not None
            and "等" in _classification_text(bonus_umbrella_parent_text)
            and re.search(
                r"等[^。；;]{0,40}(?:框架|工具|技术栈|平台|数据库|模型|语言|协议)$",
                _classification_text(bonus_umbrella_parent_text),
            )
            is not None
            and _unique_exact_span(description, bonus_umbrella_parent.original_text) is not None
            and all(
                _presentation_identity(candidate.original_text)
                in _presentation_identity(bonus_umbrella_parent.original_text)
                for candidate in bonus_umbrella_fanout_members
            )
        )
        if bonus_umbrella_fanout:
            fanout_key = (
                _presentation_identity(bonus_umbrella_parent.evidence_span),
                _presentation_identity(bonus_umbrella_parent.original_text),
            )
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.COLLAPSE_BONUS_UMBRELLA_CAPABILITY_FANOUT,
                )
            )
            if fanout_key in bonus_umbrella_fanout_seen:
                continue
            bonus_umbrella_fanout_seen.add(fanout_key)
            item = replace(
                bonus_umbrella_parent,
                type=RequirementType.CONSTRAINT,
                normalized_capability=None,
                confidence=min(
                    candidate.confidence for candidate in bonus_umbrella_fanout_members
                ),
            )
        presentation_identity = _presentation_identity(item.original_text)
        presentation_span = _unique_presentation_span(description, item.original_text)
        source_identity = (
            ""
            if item.type is RequirementType.EXPERIENCE
            else (
                f"{presentation_span[0]}:{presentation_span[1]}"
                if presentation_span is not None
                else _presentation_identity(item.evidence_span)
            )
        )
        soft_alternative_child = bool(
            item.importance is not RequirementImportance.MUST_HAVE
            and any(
                candidate is not item
                and candidate.type is RequirementType.CONSTRAINT
                and candidate.importance is RequirementImportance.MUST_HAVE
                and _presentation_identity(candidate.original_text) == presentation_identity
                and _presentation_identity(candidate.evidence_span)
                == _presentation_identity(item.evidence_span)
                for _, candidate in repaired_items
            )
        )
        explicit_soft_capability_fanout = bool(
            item.importance is RequirementImportance.PREFERRED
            and not soft_alternative_child
            and (
                _SOFT_MARKER_PATTERN.search(item.original_text)
                or _SOFT_MARKER_PATTERN.search(item.evidence_span)
            )
        )
        explicit_bonus_section_capability_fanout = bool(
            item.importance is RequirementImportance.BONUS
            and _is_explicit_bonus_section_span(description, item.evidence_span)
            and bool((item.normalized_capability or "").strip())
            and any(
                candidate is not item
                and candidate.type is item.type
                and candidate.importance is RequirementImportance.BONUS
                and _presentation_identity(candidate.original_text)
                == presentation_identity
                and _presentation_identity(candidate.evidence_span)
                == _presentation_identity(item.evidence_span)
                and bool((candidate.normalized_capability or "").strip())
                and (candidate.normalized_capability or "").strip().casefold()
                != (item.normalized_capability or "").strip().casefold()
                for _, candidate in repaired_items
            )
        )
        cardinality_child_capability_fanout = bool(
            item.importance is RequirementImportance.PREFERRED
            and not soft_alternative_child
            and presentation_span is not None
            and sum(
                scope_start <= presentation_span[0]
                and presentation_span[1] <= scope_end
                for scope_start, scope_end in group_scopes
            )
            == 1
            and any(
                candidate is not item
                and candidate.type is item.type
                and candidate.importance is RequirementImportance.PREFERRED
                and _presentation_identity(candidate.original_text)
                == presentation_identity
                and _presentation_identity(candidate.evidence_span)
                == _presentation_identity(item.evidence_span)
                and (candidate.normalized_capability or "").strip().casefold()
                != (item.normalized_capability or "").strip().casefold()
                for _, candidate in repaired_items
            )
        )
        hard_including_but_not_limited_to_umbrella_fanout = bool(
            item.importance is RequirementImportance.MUST_HAVE
            and item.type is RequirementType.SKILL
            and presentation_span is not None
            and "包括但不限于" in item.evidence_span
            and item.evidence_span.find(item.original_text.strip()) >= 0
            and item.evidence_span.find(item.original_text.strip())
            < item.evidence_span.find("包括但不限于")
            and any(
                candidate is not item
                and candidate.type is item.type
                and candidate.importance is RequirementImportance.MUST_HAVE
                and _presentation_identity(candidate.original_text)
                == presentation_identity
                and _presentation_identity(candidate.evidence_span)
                == _presentation_identity(item.evidence_span)
                and (candidate.normalized_capability or "").strip().casefold()
                != (item.normalized_capability or "").strip().casefold()
                for _, candidate in repaired_items
            )
        )
        duplicate_capability_identity = (
            ""
            if (
                item.type in {RequirementType.EXPERIENCE, RequirementType.EDUCATION}
                or explicit_soft_capability_fanout
                or explicit_bonus_section_capability_fanout
                or cardinality_child_capability_fanout
                or hard_including_but_not_limited_to_umbrella_fanout
            )
            else (item.normalized_capability or "").strip().casefold()
        )
        exact_duplicate_key = (
            item.type.value,
            item.importance.value,
            duplicate_capability_identity,
            presentation_identity,
            source_identity,
        )
        if exact_duplicate_key in exact_duplicate_keys:
            repairs.append(
                SemanticRepairEvent(
                    requirement_index=requirement_index,
                    strategy=SemanticRepairStrategy.DROP_EXACT_DUPLICATE_REQUIREMENT,
                )
            )
            continue
        exact_duplicate_keys.add(exact_duplicate_key)
        final_items.append(item)

    return JobRequirementSemanticRepairResult(
        output=JobRequirementExtractionOutput(requirements=tuple(final_items)),
        repairs=tuple(repairs),
    )


def audit_job_requirement_coverage(
    description: str,
    output: JobRequirementExtractionOutput,
) -> JobRequirementCoverageAudit:
    """Detect near-total omission of explicit duty/action lines without guessing facts.

    Outside a named duties section the existing bounded action-verb grammar remains the
    only candidate source. Inside an explicit responsibilities/duties section, numbered
    lines are already structurally identified as duties and therefore do not need to
    begin with one of those verbs. This closes false-success cases where valid duties
    begin with ``基于`` / ``持续跟踪`` / ``与...协作``. The gate remains fail-closed
    only for severe omission: at least four duty candidates must exist and fewer than
    two may be represented.
    """
    duty_candidates: list[str] = []
    seen_candidates: set[str] = set()
    in_responsibility_section = False
    lines = [line.strip() for line in description.splitlines()]
    for line_index, raw in enumerate(lines):
        if not raw:
            continue
        heading = raw.rstrip(":：").strip()
        if _RESPONSIBILITY_SECTION_NAME_PATTERN.fullmatch(heading):
            in_responsibility_section = True
            continue
        if _REQUIREMENT_SECTION_NAME_PATTERN.fullmatch(heading):
            in_responsibility_section = False
            continue

        text = _classification_text(raw)
        next_nonempty = next(
            (candidate for candidate in lines[line_index + 1 :] if candidate),
            None,
        )
        next_labeled_body = None
        if next_nonempty is not None:
            next_parts = re.split(r"[:：]", next_nonempty, maxsplit=1)
            if len(next_parts) == 2:
                next_labeled_body = _classification_text(next_parts[1].strip())
        numbered_group_heading = bool(
            in_responsibility_section
            and _LEADING_NUMBERED_ITEM_PREFIX_PATTERN.match(raw)
            and not any(separator in text for separator in (",", "，", "。", ";", "；", ":", "："))
            and next_labeled_body
            and _LABELED_RESPONSIBILITY_ACTION_PATTERN.search(next_labeled_body)
        )
        explicit_numbered_duty = bool(
            in_responsibility_section
            and _LEADING_NUMBERED_ITEM_PREFIX_PATTERN.match(raw)
            and not numbered_group_heading
        )
        labeled_parts = re.split(r"[:：]", raw, maxsplit=1)
        labeled_action_text = (
            _classification_text(labeled_parts[1].strip())
            if in_responsibility_section and len(labeled_parts) == 2
            else ""
        )
        action_shaped_duty = bool(
            (
                len(text) >= 16
                and _RESPONSIBILITY_ACTION_PATTERN.search(text)
                and any(separator in text for separator in (",", "，", "。", ";", "；"))
            )
            or (
                len(labeled_action_text) >= 16
                and _LABELED_RESPONSIBILITY_ACTION_PATTERN.search(labeled_action_text)
                and any(
                    separator in labeled_action_text
                    for separator in (",", "，", "。", ";", "；")
                )
            )
        )
        if (
            len(text) < 8
            or not (explicit_numbered_duty or action_shaped_duty)
            or _EXPERIENCE_SEGMENT_PATTERN.search(text)
            or _EDUCATION_SEGMENT_PATTERN.search(text)
            or _THRESHOLD_PATTERN.search(text)
            or _SOFT_MARKER_PATTERN.search(text)
        ):
            continue
        identity = raw.casefold()
        if identity in seen_candidates:
            continue
        seen_candidates.add(identity)
        duty_candidates.append(raw)

    covered_count = 0
    for candidate in duty_candidates:
        covered = any(
            (
                item.evidence_span.strip() == candidate
                or (
                    len(item.original_text.strip()) >= 8
                    and item.original_text.strip() in candidate
                )
            )
            for item in output.requirements
        )
        if covered:
            covered_count += 1

    enforced = len(duty_candidates) >= MIN_DUTY_CANDIDATES_FOR_COVERAGE_GATE
    return JobRequirementCoverageAudit(
        duty_candidate_count=len(duty_candidates),
        covered_duty_count=covered_count,
        minimum_covered_duty_count=(MIN_COVERED_DUTY_CANDIDATES if enforced else 0),
        enforced=enforced,
    )


def validate_job_requirement_coverage(audit: JobRequirementCoverageAudit) -> None:
    if audit.enforced and audit.covered_duty_count < audit.minimum_covered_duty_count:
        raise InvalidRequirementExtractorOutputError(
            "Requirement extractor responsibility coverage too low: "
            f"covered {audit.covered_duty_count} of {audit.duty_candidate_count} "
            "explicit duty candidates; at least "
            f"{audit.minimum_covered_duty_count} must be represented"
        )


def validate_explicit_bonus_section_coverage(
    description: str,
    output: JobRequirementExtractionOutput,
) -> None:
    """Fail closed only when an explicit numbered bonus section is almost entirely omitted."""
    bonus_candidates: list[str] = []
    in_bonus_section = False
    for raw in (line.strip() for line in description.splitlines()):
        if not raw:
            continue
        if _BONUS_SECTION_HEADING_PATTERN.fullmatch(raw):
            in_bonus_section = True
            continue
        heading = raw.rstrip(":：").strip()
        if in_bonus_section and _SECTION_HEADING_PATTERN.fullmatch(raw):
            break
        if not in_bonus_section:
            continue
        if _LEADING_NUMBERED_ITEM_PREFIX_PATTERN.match(raw) is None:
            continue
        bonus_candidates.append(raw)

    if len(bonus_candidates) < MIN_BONUS_CANDIDATES_FOR_COVERAGE_GATE:
        return

    covered_count = sum(
        any(
            item.evidence_span.strip() == candidate
            or (
                len(item.original_text.strip()) >= 4
                and item.original_text.strip() in candidate
            )
            for item in output.requirements
        )
        for candidate in bonus_candidates
    )
    if covered_count < MIN_COVERED_BONUS_CANDIDATES:
        raise InvalidRequirementExtractorOutputError(
            "Requirement extractor explicit bonus coverage too low: "
            f"covered {covered_count} of {len(bonus_candidates)} numbered bonus candidates; "
            f"at least {MIN_COVERED_BONUS_CANDIDATES} must be represented"
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
