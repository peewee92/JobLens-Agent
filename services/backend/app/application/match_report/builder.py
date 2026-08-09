"""Build a traceable transient MatchReport from Semantic Match facts."""
from __future__ import annotations

from app.application.eligibility import RequirementFitStatus
from app.application.match_report.models import (
    MatchEvidenceLink,
    MatchReport,
    MatchReportInsight,
    MatchReportRequirementResult,
    MatchRecommendation,
)
from app.application.match_report.policy import recommend_match
from app.application.semantic_match import JobSemanticMatchResult, SemanticMatchVerdict
from app.domain.job_requirements import RequirementImportance


_SUMMARIES: dict[MatchRecommendation, str] = {
    MatchRecommendation.STRONG: "核心要求和主要优先项都有明确证据支撑，值得优先投递。",
    MatchRecommendation.GOOD: "硬条件已满足，整体值得投递，但仍有部分优先项需要补强。",
    MatchRecommendation.STRETCH: "没有确认的硬性淘汰项，但仍有关键条件需要确认，适合作为挑战岗位有选择地尝试。",
    MatchRecommendation.LOW: "没有明确硬性冲突，但当前证据对岗位核心偏好支撑较弱，不建议优先投入。",
    MatchRecommendation.BLOCKED: "存在明确硬条件缺口，当前不建议优先投入。",
}


def build_match_report(result: JobSemanticMatchResult) -> MatchReport:
    recommendation = recommend_match(result)
    requirement_results = tuple(
        MatchReportRequirementResult(
            requirement_id=item.requirement_id,
            requirement_index=item.requirement_index,
            type=item.type,
            importance=item.importance,
            original_text=item.original_text,
            normalized_capability=item.normalized_capability,
            eligibility_status=item.eligibility_status,
            semantic_verdict=item.verdict,
            evidence_ids=item.evidence_ids,
            profile_fact_refs=item.profile_fact_refs,
            reason=item.reason,
        )
        for item in result.assessments
    )
    matched_requirement_ids = tuple(
        item.requirement_id
        for item in result.assessments
        if (
            item.eligibility_status is not RequirementFitStatus.MISSING
            and item.verdict is SemanticMatchVerdict.MATCHED
        )
    )
    partial_requirement_ids = tuple(
        item.requirement_id
        for item in result.assessments
        if item.verdict is SemanticMatchVerdict.PARTIAL
    )
    missing_requirement_ids = tuple(
        item.requirement_id
        for item in result.assessments
        if item.eligibility_status is RequirementFitStatus.MISSING
    )
    evidence_links = tuple(
        MatchEvidenceLink(
            requirement_id=item.requirement_id,
            evidence_ids=item.evidence_ids,
        )
        for item in result.assessments
        if item.evidence_ids
    )
    strengths = tuple(
        MatchReportInsight(
            requirement_id=item.requirement_id,
            requirement_text=item.original_text,
            reason=item.reason,
            evidence_ids=item.evidence_ids,
        )
        for item in _sorted_insight_candidates(result)
        if (
            item.eligibility_status is not RequirementFitStatus.MISSING
            and item.verdict is SemanticMatchVerdict.MATCHED
        )
    )
    risks = tuple(
        MatchReportInsight(
            requirement_id=item.requirement_id,
            requirement_text=item.original_text,
            reason=item.reason,
            evidence_ids=item.evidence_ids,
        )
        for item in _sorted_insight_candidates(result)
        if (
            item.eligibility_status is RequirementFitStatus.MISSING
            or (
                item.importance is not RequirementImportance.BONUS
                and item.verdict
                in {SemanticMatchVerdict.PARTIAL, SemanticMatchVerdict.NOT_MATCHED}
            )
        )
    )
    return MatchReport(
        job_id=result.job_id,
        profile_id=result.profile_id,
        profile_version=result.profile_version,
        extraction_id=result.extraction_id,
        eligibility=result.eligibility,
        recommendation=recommendation,
        summary=_SUMMARIES[recommendation],
        strengths=strengths,
        risks=risks,
        requirement_results=requirement_results,
        matched_requirement_ids=matched_requirement_ids,
        partial_requirement_ids=partial_requirement_ids,
        missing_requirement_ids=missing_requirement_ids,
        evidence_links=evidence_links,
        matcher_version=result.matcher_version,
        prompt_version=result.prompt_version,
        model=result.model,
        trace_run_id=result.trace_run_id,
        db_writes=result.db_writes,
        provider_calls=result.provider_calls,
        trace_runs_created=result.trace_runs_created,
    )


def _sorted_insight_candidates(result: JobSemanticMatchResult):
    importance_order = {
        RequirementImportance.MUST_HAVE: 0,
        RequirementImportance.PREFERRED: 1,
        RequirementImportance.BONUS: 2,
    }
    return tuple(
        sorted(
            result.assessments,
            key=lambda item: (importance_order[item.importance], item.requirement_index),
        )
    )
