"""Application orchestration for one transient MatchReport."""
from __future__ import annotations

from typing import Protocol

from app.application.match_report.builder import build_match_report
from app.application.match_report.models import MatchReport
from app.application.semantic_match import JobSemanticMatchResult


class SemanticMatchRunner(Protocol):
    def execute(self, job_id: str) -> JobSemanticMatchResult: ...


class BuildJobMatchReportUseCase:
    """Run guarded Semantic Match once, then apply deterministic recommendation policy."""

    def __init__(self, semantic_match: SemanticMatchRunner) -> None:
        self._semantic_match = semantic_match

    def execute(self, job_id: str) -> MatchReport:
        return build_match_report(self._semantic_match.execute(job_id))
