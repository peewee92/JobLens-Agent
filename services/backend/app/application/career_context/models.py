"""Application commands and public read models for Profile and SearchIntent."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.career_context import EvidenceType, Seniority, SkillLevel


@dataclass(frozen=True, slots=True)
class EvidenceInput:
    key: str
    type: EvidenceType
    summary: str
    source: str


@dataclass(frozen=True, slots=True)
class SkillInput:
    name: str
    level: SkillLevel
    evidence_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SaveProfileCommand:
    expected_version: int
    headline: str
    years_of_experience: float | None
    evidence: tuple[EvidenceInput, ...]
    skills: tuple[SkillInput, ...]


@dataclass(frozen=True, slots=True)
class EvidenceDetail:
    id: str
    key: str
    type: EvidenceType
    summary: str
    source: str


@dataclass(frozen=True, slots=True)
class SkillDetail:
    id: str
    name: str
    level: SkillLevel
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfileDetail:
    id: str
    version: int
    headline: str
    years_of_experience: float | None
    evidence: tuple[EvidenceDetail, ...]
    skills: tuple[SkillDetail, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SaveSearchIntentCommand:
    expected_version: int
    target_roles: tuple[str, ...]
    cities: tuple[str, ...]
    remote_accepted: bool | None
    minimum_salary_k: float | None
    seniority: Seniority | None
    employment_types: tuple[str, ...]
    exclude_keywords: tuple[str, ...]
    hard_constraints: tuple[str, ...]
    soft_preferences: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchIntentDetail:
    id: str
    version: int
    target_roles: tuple[str, ...]
    cities: tuple[str, ...]
    remote_accepted: bool | None
    minimum_salary_k: float | None
    seniority: Seniority | None
    employment_types: tuple[str, ...]
    exclude_keywords: tuple[str, ...]
    hard_constraints: tuple[str, ...]
    soft_preferences: tuple[str, ...]
    created_at: datetime
