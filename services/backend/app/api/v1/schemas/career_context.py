"""HTTP contracts for manually confirmed Profile and SearchIntent."""
from __future__ import annotations

from datetime import datetime

from pydantic import ConfigDict, Field

from app.api.v1.schemas.common import CamelCaseModel
from app.application.career_context.models import (
    EvidenceInput,
    ProfileDetail,
    SaveProfileCommand,
    SaveSearchIntentCommand,
    SearchIntentDetail,
    SkillInput,
)
from app.application.career_context.release import (
    CareerContextReleaseBlockerCode,
    CareerContextReleaseReadiness,
)
from app.domain.career_context import EvidenceType, Seniority, SkillLevel


class CareerRequestModel(CamelCaseModel):
    model_config = ConfigDict(
        alias_generator=CamelCaseModel.model_config["alias_generator"],
        populate_by_name=True,
        extra="forbid",
    )


class ProfileEvidenceRequest(CareerRequestModel):
    key: str = Field(min_length=1, max_length=150)
    type: EvidenceType
    summary: str = Field(min_length=1, max_length=5000)
    source: str = Field(min_length=1, max_length=500)


class ProfileSkillRequest(CareerRequestModel):
    name: str = Field(min_length=1, max_length=200)
    level: SkillLevel
    evidence_keys: list[str] = Field(min_length=1)


class SaveProfileRequest(CareerRequestModel):
    expected_version: int = Field(ge=0)
    headline: str = Field(min_length=1, max_length=500)
    years_of_experience: float | None = Field(default=None, ge=0)
    evidence: list[ProfileEvidenceRequest] = Field(default_factory=list)
    skills: list[ProfileSkillRequest] = Field(default_factory=list)

    def to_command(self) -> SaveProfileCommand:
        return SaveProfileCommand(
            expected_version=self.expected_version,
            headline=self.headline,
            years_of_experience=self.years_of_experience,
            evidence=tuple(
                EvidenceInput(
                    key=item.key,
                    type=item.type,
                    summary=item.summary,
                    source=item.source,
                )
                for item in self.evidence
            ),
            skills=tuple(
                SkillInput(
                    name=item.name,
                    level=item.level,
                    evidence_keys=tuple(item.evidence_keys),
                )
                for item in self.skills
            ),
        )


class ProfileEvidenceResponse(CamelCaseModel):
    id: str
    key: str
    type: EvidenceType
    summary: str
    source: str


class ProfileSkillResponse(CamelCaseModel):
    id: str
    name: str
    level: SkillLevel
    evidence_ids: list[str]


class ProfileResponse(CamelCaseModel):
    id: str
    version: int
    headline: str
    years_of_experience: float | None
    evidence: list[ProfileEvidenceResponse]
    skills: list[ProfileSkillResponse]
    created_at: datetime

    @classmethod
    def from_detail(cls, detail: ProfileDetail) -> "ProfileResponse":
        return cls(
            id=detail.id,
            version=detail.version,
            headline=detail.headline,
            years_of_experience=detail.years_of_experience,
            evidence=[
                ProfileEvidenceResponse(
                    id=item.id,
                    key=item.key,
                    type=item.type,
                    summary=item.summary,
                    source=item.source,
                )
                for item in detail.evidence
            ],
            skills=[
                ProfileSkillResponse(
                    id=item.id,
                    name=item.name,
                    level=item.level,
                    evidence_ids=list(item.evidence_ids),
                )
                for item in detail.skills
            ],
            created_at=detail.created_at,
        )


class CareerContextReleaseBlockerResponse(CamelCaseModel):
    code: CareerContextReleaseBlockerCode
    message: str


class CareerContextReleaseReadinessResponse(CamelCaseModel):
    release_eligible: bool
    confirmation_boundary: str
    profile_id: str | None
    profile_version: int | None
    profile_created_at: datetime | None
    profile_evidence_count: int
    profile_skill_count: int
    search_intent_id: str | None
    search_intent_version: int | None
    search_intent_created_at: datetime | None
    search_intent_target_role_count: int
    blockers: list[CareerContextReleaseBlockerResponse]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0

    @classmethod
    def from_detail(
        cls,
        detail: CareerContextReleaseReadiness,
    ) -> "CareerContextReleaseReadinessResponse":
        return cls(
            release_eligible=detail.release_eligible,
            confirmation_boundary=detail.confirmation_boundary,
            profile_id=detail.profile_id,
            profile_version=detail.profile_version,
            profile_created_at=detail.profile_created_at,
            profile_evidence_count=detail.profile_evidence_count,
            profile_skill_count=detail.profile_skill_count,
            search_intent_id=detail.search_intent_id,
            search_intent_version=detail.search_intent_version,
            search_intent_created_at=detail.search_intent_created_at,
            search_intent_target_role_count=detail.search_intent_target_role_count,
            blockers=[
                CareerContextReleaseBlockerResponse(
                    code=item.code,
                    message=item.message,
                )
                for item in detail.blockers
            ],
        )


class SaveSearchIntentRequest(CareerRequestModel):
    expected_version: int = Field(ge=0)
    target_roles: list[str] = Field(min_length=1)
    cities: list[str] = Field(default_factory=list)
    remote_accepted: bool | None = None
    minimum_salary_k: float | None = Field(default=None, ge=0)
    seniority: Seniority | None = None
    employment_types: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)

    def to_command(self) -> SaveSearchIntentCommand:
        return SaveSearchIntentCommand(
            expected_version=self.expected_version,
            target_roles=tuple(self.target_roles),
            cities=tuple(self.cities),
            remote_accepted=self.remote_accepted,
            minimum_salary_k=self.minimum_salary_k,
            seniority=self.seniority,
            employment_types=tuple(self.employment_types),
            exclude_keywords=tuple(self.exclude_keywords),
            hard_constraints=tuple(self.hard_constraints),
            soft_preferences=tuple(self.soft_preferences),
        )


class SearchIntentResponse(CamelCaseModel):
    id: str
    version: int
    target_roles: list[str]
    cities: list[str]
    remote_accepted: bool | None
    minimum_salary_k: float | None
    seniority: Seniority | None
    employment_types: list[str]
    exclude_keywords: list[str]
    hard_constraints: list[str]
    soft_preferences: list[str]
    created_at: datetime

    @classmethod
    def from_detail(cls, detail: SearchIntentDetail) -> "SearchIntentResponse":
        return cls(
            id=detail.id,
            version=detail.version,
            target_roles=list(detail.target_roles),
            cities=list(detail.cities),
            remote_accepted=detail.remote_accepted,
            minimum_salary_k=detail.minimum_salary_k,
            seniority=detail.seniority,
            employment_types=list(detail.employment_types),
            exclude_keywords=list(detail.exclude_keywords),
            hard_constraints=list(detail.hard_constraints),
            soft_preferences=list(detail.soft_preferences),
            created_at=detail.created_at,
        )
