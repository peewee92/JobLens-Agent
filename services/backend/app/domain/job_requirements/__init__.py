"""Job Requirement domain enums shared by contracts and persistence."""
from enum import StrEnum


class RequirementType(StrEnum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    RESPONSIBILITY = "responsibility"
    DOMAIN = "domain"
    CONSTRAINT = "constraint"


class RequirementImportance(StrEnum):
    MUST_HAVE = "must_have"
    PREFERRED = "preferred"
    BONUS = "bonus"


__all__ = ["RequirementImportance", "RequirementType"]
