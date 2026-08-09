"""SQLAlchemy persistence for immutable MatchReport snapshots."""
from __future__ import annotations

from collections.abc import Callable
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.eligibility import EligibilityDecision, RequirementFitStatus
from app.application.match_report import (
    MatchEvidenceLink,
    MatchRecommendation,
    MatchReport,
    MatchReportInsight,
    MatchReportRequirementResult,
    StoredMatchReport,
)
from app.application.ports.match_report_repository import (
    AbstractMatchReportQueryRepository,
    AbstractMatchReportRepository,
)
from app.application.semantic_match import SemanticMatchVerdict
from app.db.models import MatchReportORM
from app.domain.job_requirements import RequirementImportance, RequirementType

SessionFactory = Callable[[], Session]


class SqlAlchemyMatchReportRepository(AbstractMatchReportRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, report: MatchReport) -> StoredMatchReport:
        record = MatchReportORM(
            job_id=report.job_id,
            profile_id=report.profile_id,
            profile_version=report.profile_version,
            extraction_id=report.extraction_id,
            eligibility=report.eligibility.value,
            recommendation=report.recommendation.value,
            matcher_version=report.matcher_version,
            prompt_version=report.prompt_version,
            model=report.model,
            trace_run_id=report.trace_run_id,
            snapshot=_snapshot(report),
        )
        self._session.add(record)
        self._session.flush()
        self._session.refresh(record)
        return _stored(record)


class SqlAlchemyMatchReportQueryRepository(AbstractMatchReportQueryRepository):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get(self, report_id: str) -> StoredMatchReport | None:
        with self._session_factory() as session:
            record = session.get(MatchReportORM, report_id)
            return _stored(record) if record is not None else None

    def list_for_job(self, job_id: str) -> tuple[StoredMatchReport, ...]:
        with self._session_factory() as session:
            records = session.scalars(
                select(MatchReportORM)
                .where(MatchReportORM.job_id == job_id)
                .order_by(MatchReportORM.created_at.desc(), MatchReportORM.id.desc())
            ).all()
            return tuple(_stored(record) for record in records)


def _snapshot(report: MatchReport) -> dict:
    return {
        "summary": report.summary,
        "strengths": [_insight(item) for item in report.strengths],
        "risks": [_insight(item) for item in report.risks],
        "requirementResults": [
            {
                "requirementId": item.requirement_id,
                "requirementIndex": item.requirement_index,
                "type": item.type.value,
                "importance": item.importance.value,
                "originalText": item.original_text,
                "normalizedCapability": item.normalized_capability,
                "eligibilityStatus": item.eligibility_status.value,
                "semanticVerdict": item.semantic_verdict.value,
                "evidenceIds": list(item.evidence_ids),
                "profileFactRefs": list(item.profile_fact_refs),
                "reason": item.reason,
            }
            for item in report.requirement_results
        ],
        "matchedRequirementIds": list(report.matched_requirement_ids),
        "partialRequirementIds": list(report.partial_requirement_ids),
        "missingRequirementIds": list(report.missing_requirement_ids),
        "evidenceLinks": [
            {"requirementId": item.requirement_id, "evidenceIds": list(item.evidence_ids)}
            for item in report.evidence_links
        ],
        "dbWrites": report.db_writes,
        "providerCalls": report.provider_calls,
        "traceRunsCreated": report.trace_runs_created,
    }


def _insight(item: MatchReportInsight) -> dict:
    return {
        "requirementId": item.requirement_id,
        "requirementText": item.requirement_text,
        "reason": item.reason,
        "evidenceIds": list(item.evidence_ids),
    }


def _stored(record: MatchReportORM) -> StoredMatchReport:
    payload = record.snapshot
    report = MatchReport(
        job_id=record.job_id,
        profile_id=record.profile_id,
        profile_version=record.profile_version,
        extraction_id=record.extraction_id,
        eligibility=EligibilityDecision(record.eligibility),
        recommendation=MatchRecommendation(record.recommendation),
        summary=str(payload["summary"]),
        strengths=tuple(_restore_insight(item) for item in payload["strengths"]),
        risks=tuple(_restore_insight(item) for item in payload["risks"]),
        requirement_results=tuple(
            MatchReportRequirementResult(
                requirement_id=str(item["requirementId"]),
                requirement_index=int(item["requirementIndex"]),
                type=RequirementType(str(item["type"])),
                importance=RequirementImportance(str(item["importance"])),
                original_text=str(item["originalText"]),
                normalized_capability=(
                    str(item["normalizedCapability"])
                    if item["normalizedCapability"] is not None
                    else None
                ),
                eligibility_status=RequirementFitStatus(str(item["eligibilityStatus"])),
                semantic_verdict=SemanticMatchVerdict(str(item["semanticVerdict"])),
                evidence_ids=tuple(str(value) for value in item["evidenceIds"]),
                profile_fact_refs=tuple(str(value) for value in item["profileFactRefs"]),
                reason=str(item["reason"]),
            )
            for item in payload["requirementResults"]
        ),
        matched_requirement_ids=tuple(str(value) for value in payload["matchedRequirementIds"]),
        partial_requirement_ids=tuple(str(value) for value in payload["partialRequirementIds"]),
        missing_requirement_ids=tuple(str(value) for value in payload["missingRequirementIds"]),
        evidence_links=tuple(
            MatchEvidenceLink(
                requirement_id=str(item["requirementId"]),
                evidence_ids=tuple(str(value) for value in item["evidenceIds"]),
            )
            for item in payload["evidenceLinks"]
        ),
        matcher_version=record.matcher_version,
        prompt_version=record.prompt_version,
        model=record.model,
        trace_run_id=record.trace_run_id,
        db_writes=int(payload.get("dbWrites", 0)),
        provider_calls=int(payload.get("providerCalls", 0)),
        trace_runs_created=int(payload.get("traceRunsCreated", 0)),
    )
    created_at = (
        record.created_at.replace(tzinfo=timezone.utc)
        if record.created_at.tzinfo is None
        else record.created_at.astimezone(timezone.utc)
    )
    return StoredMatchReport(id=record.id, report=report, created_at=created_at)


def _restore_insight(item: dict) -> MatchReportInsight:
    return MatchReportInsight(
        requirement_id=str(item["requirementId"]),
        requirement_text=str(item["requirementText"]),
        reason=str(item["reason"]),
        evidence_ids=tuple(str(value) for value in item["evidenceIds"]),
    )
