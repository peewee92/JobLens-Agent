"""Application orchestration for one persisted MatchReport snapshot."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Protocol

from app.application.match_report.builder import build_match_report
from app.application.match_report.models import MatchReport
from app.application.ports.match_report_unit_of_work import AbstractMatchReportUnitOfWork
from app.application.semantic_match import JobSemanticMatchResult


class SemanticMatchRunner(Protocol):
    def execute(self, job_id: str) -> JobSemanticMatchResult: ...


class MatchReportPersistenceNotReadyError(RuntimeError):
    """Raised before Provider work when the immutable report schema is unavailable."""


MatchReportUnitOfWorkFactory = Callable[[], AbstractMatchReportUnitOfWork]
PersistenceReadyCheck = Callable[[], bool]


class BuildJobMatchReportUseCase:
    """Run guarded Semantic Match once, then persist one immutable report snapshot."""

    def __init__(
        self,
        semantic_match: SemanticMatchRunner,
        *,
        persistence_ready: PersistenceReadyCheck | None = None,
        uow_factory: MatchReportUnitOfWorkFactory | None = None,
    ) -> None:
        self._semantic_match = semantic_match
        self._persistence_ready = persistence_ready
        self._uow_factory = uow_factory

    def execute(self, job_id: str) -> MatchReport:
        if self._persistence_ready is not None and not self._persistence_ready():
            raise MatchReportPersistenceNotReadyError(
                "MatchReport persistence schema is not ready; apply the approved database migration before generating reports."
            )

        report = build_match_report(self._semantic_match.execute(job_id))
        if self._uow_factory is None:
            return report

        persisted_report = replace(report, db_writes=1)
        with self._uow_factory() as uow:
            uow.reports.add(persisted_report)
            uow.commit()
        return persisted_report
