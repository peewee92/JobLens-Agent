"""Deterministic candidate Evidence retrieval for Phase 4 Match."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import replace
from app.application.evidence_retrieval.strategy import TECHNOLOGIES, RESPONSIBILITIES, MAX_CANDIDATES

from app.application.career_context.models import EvidenceDetail, ProfileDetail
from app.application.evidence_retrieval.models import (
    CandidateEvidence,
    EvidenceRelevanceTier,
    EvidenceRetrievalBasis,
    JobEvidenceRetrievalResult,
    RequirementEvidenceCandidates,
)
from app.application.job_requirements.models import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
)


_RELATED_CAPABILITY_HINTS: dict[str, tuple[str, ...]] = {
    "mcp": (
        "Function Calling",
        "Tool Calling",
        "工具调用",
        "工具集成",
        "工具接入",
    ),
}

_BASIS_PRIORITY = {
    EvidenceRetrievalBasis.EXACT_SKILL_LINK: 0,
    EvidenceRetrievalBasis.EXPLICIT_TEXT_OVERLAP: 1,
    EvidenceRetrievalBasis.RELATED_CAPABILITY_HINT: 2,
}


def retrieve_candidate_evidence(
    *,
    profile: ProfileDetail,
    extraction: JobRequirementExtractionDetail,
) -> JobEvidenceRetrievalResult:
    requirements = tuple(
        _retrieve_for_requirement(profile=profile, requirement=requirement)
        for requirement in extraction.requirements
    )
    return JobEvidenceRetrievalResult(
        job_id=extraction.job_id,
        profile_id=profile.id,
        profile_version=profile.version,
        extraction_id=extraction.extraction_id,
        requirements=requirements,
        candidate_count=sum(len(item.candidates) for item in requirements),
    )


def _retrieve_for_requirement(
    *,
    profile: ProfileDetail,
    requirement: JobRequirementDetail,
) -> RequirementEvidenceCandidates:
    evidence_by_id = {item.id: item for item in profile.evidence}
    candidates: dict[str, CandidateEvidence] = {}

    capability = requirement.normalized_capability.strip() if requirement.normalized_capability else ""
    normalized_capability = _normalize(capability)

    if normalized_capability and _specific_skill(capability):
        for skill in profile.skills:
            if _normalize(skill.name) != normalized_capability:
                continue
            for evidence_id in skill.evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    continue
                _keep_best(
                    candidates,
                    _candidate(
                        evidence,
                        relevance_tier=EvidenceRelevanceTier.DIRECT,
                        retrieval_basis=EvidenceRetrievalBasis.EXACT_SKILL_LINK,
                        matched_terms=(skill.name,),
                        reason=(
                            f"已确认技能“{skill.name}”直接关联到这段真实经历；"
                            "Retrieval 仅把它作为候选证据，不在此处判断岗位是否已满足。"
                        ),
                    ),
                )

        for evidence in profile.evidence:
            if _contains_explicit_term(evidence.summary, capability):
                _keep_best(
                    candidates,
                    _candidate(
                        evidence,
                        relevance_tier=EvidenceRelevanceTier.DIRECT,
                        retrieval_basis=EvidenceRetrievalBasis.EXPLICIT_TEXT_OVERLAP,
                        matched_terms=(capability,),
                        reason=(
                            f"这段已确认经历明确包含能力词“{capability}”；"
                            "它可作为后续 Match 的直接候选证据。"
                        ),
                    ),
                )

    normalized_original = _normalize(requirement.original_text)
    if normalized_original and _specific_skill(requirement.original_text):
        for evidence in profile.evidence:
            if _contains_explicit_term(evidence.summary, requirement.original_text):
                _keep_best(
                    candidates,
                    _candidate(
                        evidence,
                        relevance_tier=EvidenceRelevanceTier.DIRECT,
                        retrieval_basis=EvidenceRetrievalBasis.EXPLICIT_TEXT_OVERLAP,
                        matched_terms=(requirement.original_text,),
                        reason=(
                            "这段已确认经历包含与岗位要求一致的明确原文，"
                            "可作为后续 Match 的直接候选证据。"
                        ),
                    ),
                )

    related_terms = _RELATED_CAPABILITY_HINTS.get(normalized_capability, ())
    if related_terms:
        skill_terms_by_evidence: dict[str, set[str]] = defaultdict(set)
        for skill in profile.skills:
            matched_skill_terms = tuple(
                term for term in related_terms if _normalize(skill.name) == _normalize(term)
            )
            if not matched_skill_terms:
                continue
            for evidence_id in skill.evidence_ids:
                if evidence_id in evidence_by_id:
                    skill_terms_by_evidence[evidence_id].update(matched_skill_terms)

        for evidence in profile.evidence:
            matched_terms = set(skill_terms_by_evidence.get(evidence.id, set()))
            matched_terms.update(
                term
                for term in related_terms
                if _contains_explicit_term(evidence.summary, term)
            )
            if not matched_terms:
                continue
            _keep_best(
                candidates,
                _candidate(
                    evidence,
                    relevance_tier=EvidenceRelevanceTier.RELATED,
                    retrieval_basis=EvidenceRetrievalBasis.RELATED_CAPABILITY_HINT,
                    matched_terms=tuple(
                        term for term in related_terms if term in matched_terms
                    ),
                    reason=(
                        f"这段已确认经历包含与“{capability}”相关的能力线索，"
                        "只能作为相关候选，不能因此认定已经满足岗位要求。"
                    ),
                ),
            )

    # A long capability label or sentence need not occur verbatim in the profile.
    # Only explicit technical terms or concrete, shared responsibility groups qualify.
    requirement_text = f"{capability}\n{requirement.original_text}"
    technical_groups = list(TECHNOLOGIES) + [(skill.name,) for skill in profile.skills
        if _specific_skill(skill.name)]
    for evidence in profile.evidence:
        linked_skills = [skill.name for skill in profile.skills if evidence.id in skill.evidence_ids]
        evidence_text = "\n".join([evidence.summary, *linked_skills])
        terms = set()
        for aliases in technical_groups:
            if any(_contains_explicit_term(requirement_text, term) for term in aliases) and any(
                _contains_explicit_term(evidence_text, term) for term in aliases
            ):
                terms.add(aliases[0])
        if terms:
            _keep_best(candidates, _candidate(evidence,
                relevance_tier=EvidenceRelevanceTier.DIRECT,
                retrieval_basis=EvidenceRetrievalBasis.EXPLICIT_TEXT_OVERLAP,
                matched_terms=tuple(sorted(terms)),
                reason=f"明确技术词重合（{'、'.join(sorted(terms))}），仅作为待比较候选，不代表满足要求。"))
        related = []
        for group in RESPONSIBILITIES:
            requirement_hits = [term for term in group if _contains_explicit_term(requirement_text, term)]
            evidence_hits = [term for term in group if _contains_explicit_term(evidence_text, term)]
            if requirement_hits and evidence_hits:
                related.append(f"{requirement_hits[0]} ↔ {evidence_hits[0]}")
        if related:
            _keep_best(candidates, _candidate(evidence,
                relevance_tier=EvidenceRelevanceTier.RELATED,
                retrieval_basis=EvidenceRetrievalBasis.RELATED_CAPABILITY_HINT,
                matched_terms=tuple(related),
                reason=f"具体职责线索相关（{'、'.join(related)}），仅供语义核对，不能据此认定满足要求。"))

    ordered = tuple(
        sorted(
            candidates.values(),
            key=lambda item: (
                0 if item.relevance_tier is EvidenceRelevanceTier.DIRECT else 1,
                _BASIS_PRIORITY[item.retrieval_basis],
                -len(item.matched_terms),
                item.evidence_id,
            ),
        )[:MAX_CANDIDATES]
    )
    return RequirementEvidenceCandidates(
        requirement_id=requirement.id,
        requirement_index=requirement.requirement_index,
        type=requirement.type,
        importance=requirement.importance,
        original_text=requirement.original_text,
        normalized_capability=requirement.normalized_capability,
        candidates=ordered,
    )


def _candidate(
    evidence: EvidenceDetail,
    *,
    relevance_tier: EvidenceRelevanceTier,
    retrieval_basis: EvidenceRetrievalBasis,
    matched_terms: tuple[str, ...],
    reason: str,
) -> CandidateEvidence:
    return CandidateEvidence(
        evidence_id=evidence.id,
        evidence_key=evidence.key,
        evidence_type=evidence.type,
        summary=evidence.summary,
        source=evidence.source,
        relevance_tier=relevance_tier,
        retrieval_basis=retrieval_basis,
        matched_terms=matched_terms,
        reason=reason,
    )


def _keep_best(
    candidates: dict[str, CandidateEvidence],
    candidate: CandidateEvidence,
) -> None:
    current = candidates.get(candidate.evidence_id)
    if current is None:
        candidates[candidate.evidence_id] = candidate
        return
    best = candidate if _candidate_priority(candidate) < _candidate_priority(current) else current
    candidates[candidate.evidence_id] = replace(best,
        matched_terms=tuple(sorted(set(current.matched_terms + candidate.matched_terms))))


def _candidate_priority(candidate: CandidateEvidence) -> tuple[int, int]:
    return (
        0 if candidate.relevance_tier is EvidenceRelevanceTier.DIRECT else 1,
        _BASIS_PRIORITY[candidate.retrieval_basis],
    )


def _contains_explicit_term(text: str, term: str) -> bool:
    stripped = term.strip()
    if not stripped:
        return False
    if re.fullmatch(r"[A-Za-z0-9+#.\- ]+", stripped):
        words = [re.escape(item) for item in re.split(r"\s+", stripped) if item]
        phrase = r"[\s._/\\\-]+".join(words)
        return re.search(
            rf"(?<![A-Za-z0-9]){phrase}(?![A-Za-z0-9])",
            text,
            flags=re.IGNORECASE,
        ) is not None
    return _normalize(stripped) in _normalize(text)


def _normalize(value: str) -> str:
    return re.sub(r"[\s._/\\\-、，,。；;:：()（）]+", "", value).casefold()


def _specific_skill(name: str) -> bool:
    return name.strip().casefold() not in {
        "负责", "参与", "开发", "系统", "产品", "工作", "技术", "软件", "工程", "能力",
        "development", "system", "product", "software", "engineering",
    } and len(name.strip()) >= 2
