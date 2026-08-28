"""Deterministic Growth Loop comparison tests for immutable MatchReport history."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.application.eligibility import EligibilityDecision
from app.application.match_improvement import GetMatchImprovementUseCase
from app.application.match_report import MatchRecommendation, MatchReport, StoredMatchReport
from app.application.ports.job_requirement_repository import AbstractJobRequirementQueryRepository
from app.application.ports.match_report_repository import AbstractMatchReportQueryRepository


def _stored(
    report_id: str,
    *,
    profile_version: int,
    missing: tuple[str, ...],
    recommendation: MatchRecommendation,
    extraction_id: str = "reqrun_1",
    created_offset: int = 0,
) -> StoredMatchReport:
    return StoredMatchReport(
        id=report_id,
        report=MatchReport(
            job_id="job_1",
            profile_id="profile_1",
            profile_version=profile_version,
            extraction_id=extraction_id,
            eligibility=(
                EligibilityDecision.BLOCKED
                if recommendation is MatchRecommendation.BLOCKED
                else EligibilityDecision.ELIGIBLE
            ),
            recommendation=recommendation,
            summary="fixture",
            strengths=(),
            risks=(),
            requirement_results=(),
            matched_requirement_ids=(),
            partial_requirement_ids=(),
            missing_requirement_ids=missing,
            evidence_links=(),
            matcher_version="matcher-v1",
            prompt_version="prompt-v1",
            model="fixture",
            trace_run_id=None,
        ),
        created_at=datetime(2026, 8, 28, tzinfo=UTC) + timedelta(seconds=created_offset),
    )


class _RequirementRepository(AbstractJobRequirementQueryRepository):
    def get_latest(self, job_id: str):
        return None

    def get_extraction(self, *, job_id: str, extraction_id: str):
        if extraction_id != "reqrun_1":
            return None
        return SimpleNamespace(
            requirements=(
                SimpleNamespace(id="req_1", original_text="本科及以上学历"),
                SimpleNamespace(id="req_2", original_text="熟悉 Python"),
                SimpleNamespace(id="req_3", original_text="3 年以上相关经验"),
            )
        )


class _Repository(AbstractMatchReportQueryRepository):
    def __init__(self, items: tuple[StoredMatchReport, ...]) -> None:
        self.items = items

    def get(self, report_id: str) -> StoredMatchReport | None:
        return next((item for item in self.items if item.id == report_id), None)

    def list_for_job(self, job_id: str) -> tuple[StoredMatchReport, ...]:
        return tuple(item for item in self.items if item.report.job_id == job_id)

    def list_latest_for_jobs(self, job_ids: tuple[str, ...]) -> tuple[StoredMatchReport, ...]:
        return ()


def test_match_improvement_reports_resolved_blockers_between_comparable_snapshots() -> None:
    current = _stored(
        "report_current",
        profile_version=3,
        missing=("req_3",),
        recommendation=MatchRecommendation.STRETCH,
        created_offset=2,
    )
    previous = _stored(
        "report_previous",
        profile_version=2,
        missing=("req_1", "req_2", "req_3"),
        recommendation=MatchRecommendation.BLOCKED,
        created_offset=1,
    )
    unrelated_extraction = _stored(
        "report_old_extraction",
        profile_version=1,
        missing=("req_old",),
        recommendation=MatchRecommendation.BLOCKED,
        extraction_id="reqrun_old",
    )
    use_case = GetMatchImprovementUseCase(
        _Repository((current, previous, unrelated_extraction)),
        _RequirementRepository(),
    )

    result = use_case.execute(job_id="job_1", current_report_id="report_current")

    assert result.comparable is True
    assert result.previous_report_id == "report_previous"
    assert result.previous_recommendation is MatchRecommendation.BLOCKED
    assert result.current_recommendation is MatchRecommendation.STRETCH
    assert result.previous_missing_requirement_count == 3
    assert result.current_missing_requirement_count == 1
    assert result.resolved_requirement_ids == ("req_1", "req_2")
    assert [item.original_text for item in result.resolved_requirements] == ["本科及以上学历", "熟悉 Python"]
    assert result.newly_missing_requirement_ids == ()
    assert result.newly_missing_requirements == ()
    assert result.db_writes == result.provider_calls == result.trace_runs_created == 0


def test_match_improvement_resolves_newly_missing_requirement_text_from_same_extraction() -> None:
    current = _stored(
        "report_current",
        profile_version=3,
        missing=("req_2", "req_3"),
        recommendation=MatchRecommendation.BLOCKED,
        created_offset=2,
    )
    previous = _stored(
        "report_previous",
        profile_version=2,
        missing=("req_1", "req_3"),
        recommendation=MatchRecommendation.BLOCKED,
        created_offset=1,
    )

    result = GetMatchImprovementUseCase(
        _Repository((current, previous)),
        _RequirementRepository(),
    ).execute(job_id="job_1", current_report_id="report_current")

    assert result.resolved_requirement_ids == ("req_1",)
    assert [item.original_text for item in result.resolved_requirements] == ["本科及以上学历"]
    assert result.newly_missing_requirement_ids == ("req_2",)
    assert [item.original_text for item in result.newly_missing_requirements] == ["熟悉 Python"]


def test_match_improvement_ignores_same_profile_version_reruns() -> None:
    current = _stored(
        "report_current",
        profile_version=3,
        missing=("req_3",),
        recommendation=MatchRecommendation.STRETCH,
        created_offset=2,
    )
    same_version = _stored(
        "report_same_version",
        profile_version=3,
        missing=("req_1", "req_3"),
        recommendation=MatchRecommendation.BLOCKED,
        created_offset=1,
    )

    result = GetMatchImprovementUseCase(
        _Repository((current, same_version)),
        _RequirementRepository(),
    ).execute(job_id="job_1", current_report_id="report_current")

    assert result.comparable is False
    assert result.previous_report_id is None
    assert result.previous_profile_version is None
    assert result.current_profile_version == 3


def test_match_improvement_does_not_compare_across_requirement_extractions() -> None:
    current = _stored(
        "report_current",
        profile_version=2,
        missing=("req_new",),
        recommendation=MatchRecommendation.BLOCKED,
        extraction_id="reqrun_new",
    )
    old = _stored(
        "report_old",
        profile_version=1,
        missing=("req_old",),
        recommendation=MatchRecommendation.BLOCKED,
        extraction_id="reqrun_old",
    )

    result = GetMatchImprovementUseCase(_Repository((current, old)), _RequirementRepository()).execute(
        job_id="job_1",
        current_report_id="report_current",
    )

    assert result.comparable is False
    assert result.previous_report_id is None
    assert result.resolved_requirement_ids == ()
    assert result.newly_missing_requirement_ids == ()
    assert result.resolved_requirements == ()
    assert result.newly_missing_requirements == ()
