"""HTTP contracts for resume-to-Profile proposals."""
from __future__ import annotations

from pydantic import ConfigDict, Field

from app.api.v1.schemas.common import CamelCaseModel
from app.application.profile_extraction import ProfileExtractionProposal
from app.domain.career_context import EvidenceType, SkillLevel


class ProfileExtractionRequest(CamelCaseModel):
    model_config = ConfigDict(
        alias_generator=CamelCaseModel.model_config["alias_generator"],
        populate_by_name=True,
        extra="forbid",
    )

    resume_text: str


class ProposedEvidenceResponse(CamelCaseModel):
    key: str
    type: EvidenceType
    summary: str
    source: str
    evidence_span: str


class ProposedSkillResponse(CamelCaseModel):
    name: str
    level: SkillLevel
    evidence_keys: list[str]


class ProfileSourceRecovery(CamelCaseModel):
    omitted_evidence_count: int = Field(gt=0)
    omitted_skill_count: int = Field(ge=0)


class ProfileExtractionProposalResponse(CamelCaseModel):
    run_id: str
    extractor_version: str
    model: str
    prompt_version: str
    headline: str
    years_of_experience: float | None
    evidence: list[ProposedEvidenceResponse]
    skills: list[ProposedSkillResponse]
    warnings: list[str]
    source_recovery: ProfileSourceRecovery | None = Field(default=None, exclude_if=lambda value: value is None)

    @classmethod
    def from_proposal(
        cls, proposal: ProfileExtractionProposal
    ) -> "ProfileExtractionProposalResponse":
        return cls(
            run_id=proposal.run_id,
            extractor_version=proposal.extractor_version,
            model=proposal.model,
            prompt_version=proposal.prompt_version,
            headline=proposal.headline,
            years_of_experience=proposal.years_of_experience,
            evidence=[
                ProposedEvidenceResponse(
                    key=item.key,
                    type=item.type,
                    summary=item.summary,
                    source=item.source,
                    evidence_span=item.evidence_span,
                )
                for item in proposal.evidence
            ],
            skills=[
                ProposedSkillResponse(
                    name=item.name,
                    level=item.level,
                    evidence_keys=list(item.evidence_keys),
                )
                for item in proposal.skills
            ],
            warnings=list(proposal.warnings),
            source_recovery=ProfileSourceRecovery(
                omitted_evidence_count=proposal.omitted_evidence_count,
                omitted_skill_count=proposal.omitted_skill_count,
            ) if proposal.omitted_evidence_count else None,
        )
