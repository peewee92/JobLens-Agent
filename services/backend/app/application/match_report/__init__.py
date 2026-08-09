"""Phase 4 transient MatchReport public application API."""
from app.application.match_report.builder import build_match_report
from app.application.match_report.models import (
    MatchEvidenceLink,
    MatchRecommendation,
    MatchReport,
    MatchReportInsight,
    MatchReportRequirementResult,
    StoredMatchReport,
)
from app.application.match_report.policy import recommend_match
from app.application.match_report.use_case import (
    BuildJobMatchReportUseCase,
    MatchReportPersistenceNotReadyError,
)

__all__ = [
    "BuildJobMatchReportUseCase",
    "MatchEvidenceLink",
    "MatchRecommendation",
    "MatchReport",
    "MatchReportInsight",
    "MatchReportRequirementResult",
    "MatchReportPersistenceNotReadyError",
    "StoredMatchReport",
    "build_match_report",
    "recommend_match",
]
