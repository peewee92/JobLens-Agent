"""Persistence contract tests for immutable MatchReport snapshots."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.eligibility import EligibilityDecision, RequirementFitStatus
from app.application.match_report import (
    MatchEvidenceLink,
    MatchRecommendation,
    MatchReport,
    MatchReportInsight,
    MatchReportRequirementResult,
)
from app.application.semantic_match import SemanticMatchVerdict
from app.db.base import Base
from app.db.models import MatchReportORM
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.repositories.sqlalchemy_match_report_repository import SqlAlchemyMatchReportQueryRepository
from app.repositories.sqlalchemy_match_report_unit_of_work import SqlAlchemyMatchReportUnitOfWork


def _report(job_id: str = "job_1", trace_run_id: str = "run_1") -> MatchReport:
    requirement = MatchReportRequirementResult(
        requirement_id="req_mcp",
        requirement_index=0,
        type=RequirementType.SKILL,
        importance=RequirementImportance.MUST_HAVE,
        original_text="熟悉 MCP 协议",
        normalized_capability="MCP",
        eligibility_status=RequirementFitStatus.MISSING,
        semantic_verdict=SemanticMatchVerdict.PARTIAL,
        evidence_ids=("ev_tools",),
        profile_fact_refs=("profile.skill.agent_tools",),
        reason="工具调用经历相关，但没有直接 MCP 证据。",
    )
    risk = MatchReportInsight(
        requirement_id="req_mcp",
        requirement_text="熟悉 MCP 协议",
        reason=requirement.reason,
        evidence_ids=("ev_tools",),
    )
    return MatchReport(
        job_id=job_id,
        profile_id="profile_1",
        profile_version=3,
        extraction_id="reqrun_1",
        eligibility=EligibilityDecision.BLOCKED,
        recommendation=MatchRecommendation.BLOCKED,
        summary="存在明确硬条件缺口，当前不建议优先投入。",
        strengths=(),
        risks=(risk,),
        requirement_results=(requirement,),
        matched_requirement_ids=(),
        partial_requirement_ids=("req_mcp",),
        missing_requirement_ids=("req_mcp",),
        evidence_links=(MatchEvidenceLink(requirement_id="req_mcp", evidence_ids=("ev_tools",)),),
        matcher_version="semantic-match-v1",
        prompt_version="semantic-match-v3",
        model="fixture-semantic-matcher",
        trace_run_id=trace_run_id,
        db_writes=0,
        provider_calls=1,
        trace_runs_created=1,
    )


def _factory(tmp_path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'match-report.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_match_report_repository_round_trips_frozen_evidence_and_model_identity(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        saved = uow.reports.add(_report())
        uow.commit()
    loaded = SqlAlchemyMatchReportQueryRepository(factory).get(saved.id)

    assert loaded is not None
    assert loaded.id == saved.id
    assert loaded.report == _report()
    assert loaded.report.requirement_results[0].evidence_ids == ("ev_tools",)
    assert loaded.report.requirement_results[0].profile_fact_refs == ("profile.skill.agent_tools",)
    assert loaded.report.trace_run_id == "run_1"
    assert loaded.report.matcher_version == "semantic-match-v1"
    assert loaded.report.prompt_version == "semantic-match-v3"


def test_match_report_repository_appends_history_instead_of_overwriting_same_job(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        first = uow.reports.add(_report(trace_run_id="run_1"))
        uow.commit()
    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        second = uow.reports.add(_report(trace_run_id="run_2"))
        uow.commit()

    assert first.id != second.id
    history = SqlAlchemyMatchReportQueryRepository(factory).list_for_job("job_1")
    assert tuple(item.id for item in history) == (second.id, first.id)
    assert tuple(item.report.trace_run_id for item in history) == ("run_2", "run_1")

    with factory() as session:
        assert len(session.scalars(select(MatchReportORM)).all()) == 2


def test_match_report_query_lists_latest_snapshot_per_requested_job_in_request_order(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        job_1_old = uow.reports.add(_report(job_id="job_1", trace_run_id="run_1_old"))
        uow.commit()
    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        job_2 = uow.reports.add(_report(job_id="job_2", trace_run_id="run_2"))
        uow.commit()
    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        job_1_new = uow.reports.add(_report(job_id="job_1", trace_run_id="run_1_new"))
        uow.commit()

    latest = SqlAlchemyMatchReportQueryRepository(factory).list_latest_for_jobs(
        ("job_2", "job_missing", "job_1", "job_2")
    )

    assert tuple(item.id for item in latest) == (job_2.id, job_1_new.id)
    assert tuple(item.report.trace_run_id for item in latest) == ("run_2", "run_1_new")
    assert job_1_old.id not in {item.id for item in latest}


def test_match_report_unit_of_work_rolls_back_uncommitted_snapshot(tmp_path: Path) -> None:
    factory = _factory(tmp_path)

    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        saved = uow.reports.add(_report())

    assert SqlAlchemyMatchReportQueryRepository(factory).get(saved.id) is None
    with factory() as session:
        assert session.scalars(select(MatchReportORM)).all() == []
