"""Career-context domain enums shared across backend layers."""
from enum import Enum


class EvidenceType(str, Enum):
    WORK = "work"
    PROJECT = "project"
    EDUCATION = "education"
    ACHIEVEMENT = "achievement"
    SELF_REPORT = "self_report"


class SkillLevel(str, Enum):
    STRONG = "strong"
    WORKING = "working"
    BASIC = "basic"
    UNKNOWN = "unknown"


class Seniority(str, Enum):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    LEAD = "lead"
    PRINCIPAL = "principal"
