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
    if requirement.importance is RequirementImportance.MUST_HAVE:
        return _result(
            requirement,
            status=RequirementFitStatus.MISSING,
            reason="这是岗位明确的硬技能要求，但当前已确认技能和经历中没有对应证据。",
        )
    return _result(
        requirement,
        status=RequirementFitStatus.CONDITIONAL,
        reason="当前没有对应的已确认技能证据，但这不是岗位硬门槛，不因此直接淘汰。",
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
        return _unknown_or_missing(requirement, "当前资料没有足够结构化信息证明这条经验要求。")

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
    return _unknown_or_missing(
        requirement,
        "这是专项经验要求；当前已确认经历里没有足够证据，且不能用总工作年限代替专项年限。",
    )


def _evaluate_education(
    profile: ProfileDetail,
    requirement: JobRequirementDetail,
) -> RequirementEligibilityResult:
    required_degree = _required_degree(requirement.original_text)
    if required_degree is None:
        return _unknown_or_missing(requirement, "当前资料不足以可靠判断这条学历/专业要求。")

    education = [item for item in profile.evidence if item.type.value == "education"]
    best_rank = 0
    matching_ids: list[str] = []
    for item in education:
        rank = max((_DEGREE_RANK.get(name, 0) for name in _DEGREE_RANK if name in item.summary), default=0)
        if rank > best_rank:
            best_rank = rank
        if rank >= _DEGREE_RANK[required_degree]:
            matching_ids.append(item.id)
    if matching_ids:
        if "专业" in requirement.original_text and "优先" in requirement.original_text:
            return _result(
                requirement,
                status=RequirementFitStatus.CONDITIONAL,
                evidence_ids=tuple(matching_ids),
                reason="已确认学历层级满足，但这条要求还包含专业偏好，当前切片不做语义猜测。",
            )
        return _result(
            requirement,
            status=RequirementFitStatus.MATCHED,
            evidence_ids=tuple(matching_ids),
            reason=f"已确认教育经历满足“{required_degree}及以上”的学历层级要求。",
        )
    return _unknown_or_missing(requirement, f"当前已确认教育经历没有“{required_degree}及以上”的直接证据。")


def _unknown_or_missing(
    requirement: JobRequirementDetail,
    reason: str,
) -> RequirementEligibilityResult:
    return _result(
        requirement,
        status=(
            RequirementFitStatus.MISSING
            if requirement.importance is RequirementImportance.MUST_HAVE
            else RequirementFitStatus.CONDITIONAL
        ),
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


def _required_degree(text: str) -> str | None:
    for name in ("博士", "硕士", "本科", "大专", "专科"):
        if name in text:
            return name
    return None
