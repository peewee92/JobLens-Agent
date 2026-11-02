"""Deterministic, evidence-grounded Eligibility evaluation."""
from __future__ import annotations

import re

from app.application.career_context.models import ProfileDetail, SkillDetail
from app.application.eligibility.models import (
    EligibilityDecision,
    JobEligibilityResult,
    RequirementEligibilityResult,
    RequirementFitStatus,
)
from app.application.job_requirements.models import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
)
from app.domain.job_requirements import RequirementImportance, RequirementType

_YEAR_REQUIREMENT = re.compile(
    r"(?P<years>\d+(?:\.\d+)?)\s*年(?:及以上|以上)?(?P<topic>[^。；;，,]{0,40}?)经验"
)
_GENERIC_EXPERIENCE_TOPICS = {"", "工作", "相关工作", "从业", "相关"}
_DEGREE_RANK = {"大专": 1, "专科": 1, "本科": 2, "硕士": 3, "博士": 4}
_EDUCATION_MAJOR_MARKERS = (
    "计算机",
    "人工智能",
    "软件工程",
    "汽车工程",
    "电子信息",
    "通信",
    "数学",
    "统计",
    "自动化",
    "信息安全",
    "网络工程",
    "数据科学",
)
_EDUCATION_SCHOOL_QUALIFIERS = (
    "知名高校",
    "重点高校",
    "重点大学",
    "985",
    "211",
    "双一流",
    "名校",
)

# 「至少满足一项」这类条件组：整体是一道门，不能拆成互不相干的加分项。
# 刻意不收「任一」——「熟悉任一现代框架」是单个技能要求，不是条件组。
_ALTERNATIVE_GROUP_MARKERS = (
    "至少满足一项",
    "至少满足其一",
    "至少满足其中一项",
    "满足其中一项",
    "满足其一",
    "其中之一",
    "任意一种",
    "任意一项",
    "以下之一",
    "任选其一",
    "择一",
    "at least one of",
    "one of the following",
)
_ALT_SPLIT = re.compile(r"[\n；;]+")
_ALT_STRIP = re.compile(r"^\s*(?:[-*·•]|\d+[.、)]|[（(]\d+[)）])\s*")
_ALT_HEADER_HINT = re.compile(r"^(背景|要求|以下|以下任意|以下至少)")
# 备选项与证据的二元组重合度：>=0.5 认为命中，0.15~0.5 算部分沾边，更低算没命中。
# 阈值刻意保守：宁可判「未决」，也不把沾边的关键词当成满足（不编造证据）。
_ALT_MATCH_RATIO = 0.5
_ALT_PARTIAL_RATIO = 0.15


def _alternative_group_marker(text: str) -> str | None:
    lowered = (text or "").casefold()
    for marker in _ALTERNATIVE_GROUP_MARKERS:
        if marker in lowered:
            return marker
    return None


def _split_alternatives(text: str) -> tuple[str, ...]:
    """把「至少满足一项」组切成备选项。

    只按换行和分号切。中文顿号/逗号经常出现在单个备选项内部
    （例如“独立开发者，或有 AI Side Project、AI 创业经历”），不能用来切。
    """
    segments: list[str] = []
    for raw in _ALT_SPLIT.split(text or ""):
        segment = _ALT_STRIP.sub("", raw).strip()
        if len(segment) < 4:
            continue
        if _alternative_group_marker(segment) and len(segment) < 40:
            continue  # 组头，不是备选项
        if _ALT_HEADER_HINT.match(segment) and "：" in segment:
            continue
        segments.append(segment)
    return tuple(segments)


def _keyword_hits(profile: ProfileDetail, alternative: str) -> tuple[float, tuple[str, ...]]:
    """备选项与已确认证据的字符二元组重合度。

    中文句子没有空格，按空白分词会退化成整句比较，所以用二元组：
    既能在「换一种说法但说的是同一件事」时命中，也不至于像关键词那样轻易误判。
    只用于把「三项全无 / 部分沾边 / 明显命中」区分开，不作为满足的证明。
    """
    target = _bigrams(alternative)
    if not target:
        return 0.0, ()
    profile_grams: set[str] = set()
    for item in profile.evidence:
        profile_grams |= _bigrams(item.summary or "")
    for skill in profile.skills:
        profile_grams |= _bigrams(skill.name or "")
    if not profile_grams:
        return 0.0, ()
    ratio = len(target & profile_grams) / len(target)
    evidence_ids = tuple(
        item.id for item in profile.evidence if _bigrams(item.summary or "") & target
    )
    return ratio, evidence_ids


def _bigrams(text: str) -> set[str]:
    """中文取字符二元组，英文/数字取整词。

    英文若也取二元组，会产出 ct/ec/ro 这类噪声片段，
    让「React」和「project」互相命中，把不相关的备选项算成沾边。
    """
    grams: set[str] = set()
    for run in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", (text or "").casefold()):
        if run[0].isascii():
            if len(run) >= 2:
                grams.add(run)
            continue
        if len(run) == 1:
            grams.add(run)
        else:
            grams |= {run[index : index + 2] for index in range(len(run) - 1)}
    return grams


def _evaluate_alternative_group(
    profile: ProfileDetail,
    requirement: JobRequirementDetail,
) -> RequirementEligibilityResult | None:
    """条件组整体判定：命中任意一项即满足；都不命中要写明「哪几项都不满足」。"""
    marker = _alternative_group_marker(requirement.original_text)
    if marker is None:
        return None
    alternatives = _split_alternatives(requirement.original_text)
    if len(alternatives) < 2:
        return None  # 只有一句，不是条件组，交回通用判定

    confirmed: list[tuple[str, tuple[str, ...]]] = []
    partial: list[str] = []
    for alternative in alternatives:
        exact = _exact_evidence_matches(profile, alternative)
        if exact:
            confirmed.append((alternative, exact))
            continue
        ratio, evidence_ids = _keyword_hits(profile, alternative)
        if ratio >= _ALT_MATCH_RATIO:
            confirmed.append((alternative, evidence_ids))
        elif ratio >= _ALT_PARTIAL_RATIO:
            partial.append(alternative)

    if confirmed:
        alternative, evidence_ids = confirmed[0]
        return _result(
            requirement,
            status=RequirementFitStatus.MATCHED,
            evidence_ids=evidence_ids,
            reason=f"这是「{marker}」的条件组，已确认经历命中其中一项：{alternative}",
        )

    listed = "；".join(alternatives)
    if partial:
        return _result(
            requirement,
            status=RequirementFitStatus.CONDITIONAL,
            reason=(
                f"这是「{marker}」的条件组，已确认证据只是部分沾边，还不能算满足："
                f"{'；'.join(partial)}。需要补充能明确证明「{listed}」其中一项的真实经历。"
            ),
        )
    return _result(
        requirement,
        status=RequirementFitStatus.CONDITIONAL,
        reason=(
            f"这是「{marker}」的条件组，已确认证据没有命中其中任何一项：{listed}。"
            "补齐其中任意一项的真实证据即可满足，不需要三项都补齐。"
        ),
    )



def evaluate_eligibility(
    *,
    profile: ProfileDetail,
    extraction: JobRequirementExtractionDetail,
) -> JobEligibilityResult:
    results = tuple(
        _evaluate_requirement(profile=profile, requirement=requirement)
        for requirement in extraction.requirements
    )
    missing_must_have = any(
        item.importance is RequirementImportance.MUST_HAVE
        and item.status is RequirementFitStatus.MISSING
        for item in results
    )
    conditional_must_have = any(
        item.importance is RequirementImportance.MUST_HAVE
        and item.status is RequirementFitStatus.CONDITIONAL
        for item in results
    )
    if missing_must_have:
        eligibility = EligibilityDecision.BLOCKED
    elif conditional_must_have:
        eligibility = EligibilityDecision.CONDITIONAL
    else:
        eligibility = EligibilityDecision.ELIGIBLE

    return JobEligibilityResult(
        job_id=extraction.job_id,
        profile_id=profile.id,
        profile_version=profile.version,
        extraction_id=extraction.extraction_id,
        eligibility=eligibility,
        requirements=results,
        matched_count=sum(item.status is RequirementFitStatus.MATCHED for item in results),
        conditional_count=sum(
            item.status is RequirementFitStatus.CONDITIONAL for item in results
        ),
        missing_count=sum(item.status is RequirementFitStatus.MISSING for item in results),
    )


def _evaluate_requirement(
    *,
    profile: ProfileDetail,
    requirement: JobRequirementDetail,
) -> RequirementEligibilityResult:
    # 条件组先判：整体是一道门，命中任意一项即可满足。
    group_result = _evaluate_alternative_group(profile, requirement)
    if group_result is not None:
        return group_result

    if requirement.type is RequirementType.SKILL:
        return _evaluate_skill(profile, requirement)
    if requirement.type is RequirementType.EXPERIENCE:
        return _evaluate_experience(profile, requirement)
    if requirement.type is RequirementType.EDUCATION:
        return _evaluate_education(profile, requirement)

    capability_match = _skill_match(profile, requirement.normalized_capability)
    if capability_match is not None:
        return _result(
            requirement,
            status=RequirementFitStatus.MATCHED,
            evidence_ids=capability_match.evidence_ids,
            reason="已确认职业背景中有直接对应的能力证据。",
        )

    exact_evidence_ids = _exact_evidence_matches(profile, requirement.original_text)
    if exact_evidence_ids:
        return _result(
            requirement,
            status=RequirementFitStatus.MATCHED,
            evidence_ids=exact_evidence_ids,
            reason="已确认经历中存在与这条要求直接一致的事实。",
        )

    return _result(
        requirement,
        status=RequirementFitStatus.CONDITIONAL,
        reason="当前结构化职业背景不足以可靠判断这条要求，暂不猜测满足或缺失。",
    )


def _evaluate_skill(
    profile: ProfileDetail,
    requirement: JobRequirementDetail,
) -> RequirementEligibilityResult:
    skill = _skill_match(profile, requirement.normalized_capability)
    if skill is not None:
        return _result(
            requirement,
            status=RequirementFitStatus.MATCHED,
            evidence_ids=skill.evidence_ids,
            reason=f"已确认技能中存在“{skill.name}”，并能追溯到真实经历。",
        )
    return _result(
        requirement,
        status=RequirementFitStatus.CONDITIONAL,
        reason="当前没有对应的已确认技能证据，不能据此认定你不会该技能；请补充真实证据或进一步核实。",
    )


def _evaluate_experience(
    profile: ProfileDetail,
    requirement: JobRequirementDetail,
) -> RequirementEligibilityResult:
    match = _YEAR_REQUIREMENT.search(requirement.original_text)
    if match is None:
        exact_evidence_ids = _exact_evidence_matches(profile, requirement.original_text)
        if exact_evidence_ids:
            return _result(
                requirement,
                status=RequirementFitStatus.MATCHED,
                evidence_ids=exact_evidence_ids,
                reason="已确认经历中存在与这条经验要求直接一致的事实。",
            )
        return _result(
            requirement,
            status=RequirementFitStatus.CONDITIONAL,
            reason=(
                "这条经验要求不包含可确定性核验的年限，当前结构化事实不足以直接判定缺失；"
                "保留给后续基于 Evidence 的语义匹配判断。"
            ),
        )

    required_years = float(match.group("years"))
    topic = match.group("topic").strip().replace("的", "")
    if topic in _GENERIC_EXPERIENCE_TOPICS:
        if profile.years_of_experience is None:
            return _result(
                requirement,
                status=RequirementFitStatus.CONDITIONAL,
                reason="岗位要求了总工作年限，但你的已确认职业背景尚未提供可用的总年限。",
            )
        if profile.years_of_experience >= required_years:
            return _result(
                requirement,
                status=RequirementFitStatus.MATCHED,
                profile_fact_refs=("yearsOfExperience",),
                reason=(
                    f"已确认总工作年限为 {profile.years_of_experience:g} 年，"
                    f"达到岗位要求的 {required_years:g} 年。"
                ),
            )
        return _result(
            requirement,
            status=(
                RequirementFitStatus.MISSING
                if requirement.importance is RequirementImportance.MUST_HAVE
                else RequirementFitStatus.CONDITIONAL
            ),
            profile_fact_refs=("yearsOfExperience",),
            reason=(
                f"已确认总工作年限为 {profile.years_of_experience:g} 年，"
                f"低于岗位要求的 {required_years:g} 年。"
            ),
        )

    topic_evidence_ids = _topic_evidence_matches(profile, topic)
    if topic_evidence_ids:
        return _result(
            requirement,
            status=RequirementFitStatus.CONDITIONAL,
            evidence_ids=topic_evidence_ids,
            reason=(
                "已确认经历里出现了相关专项经验，但当前 Profile 没有记录该专项的可验证年限，"
                "不能用总工作年限代替。"
            ),
        )
    return _unknown(
        requirement,
        "这是专项经验要求；当前已确认经历里没有足够证据，且不能用总工作年限代替专项年限。",
    )


def _evaluate_education(
    profile: ProfileDetail,
    requirement: JobRequirementDetail,
) -> RequirementEligibilityResult:
    required_degree = _required_degree(requirement.original_text)
    if required_degree is None:
        return _unknown(requirement, "当前资料不足以可靠判断这条学历/专业要求。")

    education = [item for item in profile.evidence if item.type.value == "education"]
    degree_matching_ids: list[str] = []
    fully_matching_ids: list[str] = []
    for item in education:
        rank = max(
            (_DEGREE_RANK.get(name, 0) for name in _DEGREE_RANK if name in item.summary),
            default=0,
        )
        if rank < _DEGREE_RANK[required_degree]:
            continue
        degree_matching_ids.append(item.id)
        if _education_qualifiers_supported(requirement.original_text, item.summary):
            fully_matching_ids.append(item.id)

    if fully_matching_ids:
        return _result(
            requirement,
            status=RequirementFitStatus.MATCHED,
            evidence_ids=tuple(fully_matching_ids),
            reason=f"已确认教育经历满足“{required_degree}及以上”及岗位明确的教育限定。",
        )
    if degree_matching_ids:
        return _result(
            requirement,
            status=RequirementFitStatus.CONDITIONAL,
            evidence_ids=tuple(degree_matching_ids),
            reason=(
                f"已确认学历层级达到“{required_degree}及以上”，但岗位还包含专业或院校限定，"
                "当前教育证据没有直接证明该限定。"
            ),
        )
    return _unknown(requirement, f"当前已确认教育经历没有“{required_degree}及以上”的直接证据。")


def _unknown(
    requirement: JobRequirementDetail,
    reason: str,
) -> RequirementEligibilityResult:
    return _result(
        requirement,
        status=RequirementFitStatus.CONDITIONAL,
        reason=reason,
    )


def _result(
    requirement: JobRequirementDetail,
    *,
    status: RequirementFitStatus,
    reason: str,
    evidence_ids: tuple[str, ...] = (),
    profile_fact_refs: tuple[str, ...] = (),
) -> RequirementEligibilityResult:
    return RequirementEligibilityResult(
        requirement_id=requirement.id,
        requirement_index=requirement.requirement_index,
        type=requirement.type,
        importance=requirement.importance,
        original_text=requirement.original_text,
        normalized_capability=requirement.normalized_capability,
        status=status,
        evidence_ids=evidence_ids,
        profile_fact_refs=profile_fact_refs,
        reason=reason,
    )


def _skill_match(profile: ProfileDetail, capability: str | None) -> SkillDetail | None:
    if not capability:
        return None
    target = _normalize_label(capability)
    return next(
        (skill for skill in profile.skills if _normalize_label(skill.name) == target),
        None,
    )


def _normalize_label(value: str) -> str:
    return re.sub(r"[\s._/\\-]+", "", value).casefold()


def _exact_evidence_matches(profile: ProfileDetail, text: str) -> tuple[str, ...]:
    needle = text.strip()
    if not needle:
        return ()
    return tuple(item.id for item in profile.evidence if needle in item.summary)


def _topic_evidence_matches(profile: ProfileDetail, topic: str) -> tuple[str, ...]:
    normalized_topic = _normalize_label(topic)
    if len(normalized_topic) < 2:
        return ()
    return tuple(
        item.id
        for item in profile.evidence
        if normalized_topic in _normalize_label(item.summary)
    )


def _education_qualifiers_supported(requirement_text: str, evidence_summary: str) -> bool:
    if "专业" in requirement_text:
        required_major_markers = tuple(
            marker for marker in _EDUCATION_MAJOR_MARKERS if marker in requirement_text
        )
        if not required_major_markers or not any(
            marker in evidence_summary for marker in required_major_markers
        ):
            return False

    required_school_qualifiers = tuple(
        marker for marker in _EDUCATION_SCHOOL_QUALIFIERS if marker in requirement_text
    )
    if required_school_qualifiers and not all(
        marker in evidence_summary for marker in required_school_qualifiers
    ):
        return False
    return True


def _required_degree(text: str) -> str | None:
    for name in ("博士", "硕士", "本科", "大专", "专科"):
        if name in text:
            return name
    return None
