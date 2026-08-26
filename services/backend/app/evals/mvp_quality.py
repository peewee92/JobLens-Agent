"""Offline-first MVP quality gate shared by CLI and read-only Eval UI."""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.eligibility import EligibilityDecision, RequirementFitStatus
from app.application.evidence_retrieval import EvidenceRelevanceTier, EvidenceRetrievalBasis
from app.application.match_ranking import rank_match_reports
from app.application.match_report import MatchRecommendation
from app.application.match_report.builder import build_match_report
from app.application.semantic_match import (
    JobSemanticMatchResult,
    SemanticAssessmentSource,
    SemanticCandidateInput,
    SemanticMatchVerdict,
    SemanticRequirementAssessment,
    SemanticRequirementInput,
)
from app.db.base import Base
from app.domain.career_context import EvidenceType
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.evals.job_requirement_extraction import (
    load_job_requirement_eval_cases,
    run_job_requirement_eval,
)
from app.llm import FixtureJobRequirementExtractor
from app.llm.semantic_matchers import FixtureSemanticMatcher
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.repositories.sqlalchemy_match_report_repository import SqlAlchemyMatchReportQueryRepository
from app.repositories.sqlalchemy_match_report_unit_of_work import SqlAlchemyMatchReportUnitOfWork
from app.workflows import ExtractJobRequirementsWorkflow

REQUIREMENT_REPLAY_DATASET_VERSION = "requirement-extraction-v2"
REQUIREMENT_REPLAY_DATASET = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "evals"
    / "requirement-extraction"
    / f"{REQUIREMENT_REPLAY_DATASET_VERSION}.jsonl"
)


@dataclass(frozen=True, slots=True)
class MvpQualityStatus:
    gate_passed: bool
    replay_passed: bool
    replay_passed_cases: int
    replay_total_cases: int
    match_demo_passed: bool
    match_demo_persisted_reports: int
    match_demo_top_jobs: int
    match_demo_evidence_complete: bool
    provider_smoke_state: str = "not_requested"
    provider_smoke_ready: bool | None = None
    provider_smoke_blocking: bool = False
    provider_smoke_blocker: str | None = None
    provider_calls: int = 0


def run_offline_requirement_replay_gate(*, session_factory):
    """Evaluate the frozen Requirement fixture with zero live Provider calls."""
    workflow = ExtractJobRequirementsWorkflow(
        FixtureJobRequirementExtractor(),
        lambda: SqlAlchemyTraceUnitOfWork(session_factory),
    )
    return run_job_requirement_eval(
        workflow=workflow,
        cases=load_job_requirement_eval_cases(REQUIREMENT_REPLAY_DATASET),
        dataset_version=REQUIREMENT_REPLAY_DATASET_VERSION,
    )


def _build_fixture_report(
    job_index: int,
    *,
    eligibility: EligibilityDecision = EligibilityDecision.ELIGIBLE,
    has_evidence: bool = True,
):
    job_id = f"fixture_job_{job_index:02d}"
    requirement_id = f"fixture_req_{job_index:02d}"
    evidence_id = f"fixture_evidence_{job_index:02d}"
    candidate = SemanticCandidateInput(
        evidence_id=evidence_id,
        evidence_type=EvidenceType.PROJECT,
        summary=f"Confirmed project evidence for fixture job {job_index}.",
        relevance_tier=EvidenceRelevanceTier.DIRECT,
        retrieval_basis=EvidenceRetrievalBasis.EXACT_SKILL_LINK,
    )
    requirement = SemanticRequirementInput(
        requirement_id=requirement_id,
        requirement_index=0,
        type=RequirementType.SKILL,
        importance=RequirementImportance.MUST_HAVE,
        original_text=f"Must demonstrate fixture capability {job_index}",
        normalized_capability=f"FixtureCapability{job_index}",
        candidates=(candidate,) if has_evidence else (),
    )
    matcher = FixtureSemanticMatcher()
    if has_evidence:
        matched = matcher.match((requirement,)).output.assessments[0]
        assessment = SemanticRequirementAssessment(
            requirement_id=requirement.requirement_id,
            requirement_index=0,
            type=requirement.type,
            importance=requirement.importance,
            original_text=requirement.original_text,
            normalized_capability=requirement.normalized_capability,
            eligibility_status=RequirementFitStatus.MATCHED,
            verdict=matched.verdict,
            evidence_ids=matched.evidence_ids,
            profile_fact_refs=(f"profile.skill.fixture_{job_index}",),
            reason=matched.reason,
            source=SemanticAssessmentSource.PROVIDER,
        )
        matched_count = 1
        not_matched_count = 0
    else:
        assessment = SemanticRequirementAssessment(
            requirement_id=requirement.requirement_id,
            requirement_index=0,
            type=requirement.type,
            importance=requirement.importance,
            original_text=requirement.original_text,
            normalized_capability=requirement.normalized_capability,
            eligibility_status=RequirementFitStatus.CONDITIONAL,
            verdict=SemanticMatchVerdict.NOT_MATCHED,
            evidence_ids=(),
            profile_fact_refs=(),
            reason="No confirmed profile evidence is available for this fixture requirement.",
            source=SemanticAssessmentSource.DETERMINISTIC,
        )
        matched_count = 0
        not_matched_count = 1
    semantic_result = JobSemanticMatchResult(
        job_id=job_id,
        profile_id="fixture_profile",
        profile_version=1,
        extraction_id=f"fixture_extraction_{job_index:02d}",
        eligibility=eligibility,
        assessments=(assessment,),
        matched_count=matched_count,
        partial_count=0,
        not_matched_count=not_matched_count,
        matcher_version="semantic-match-v1",
        prompt_version="semantic-match-v3",
        model=matcher.model_name,
        trace_run_id=None,
        db_writes=0,
        provider_calls=0,
        trace_runs_created=0,
    )
    return build_match_report(semantic_result)


def run_offline_match_demo(*, database_path: Path, top_n: int = 5) -> dict[str, object]:
    """Persist deterministic fixture MatchReports and rank them without a Provider."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)

    reports = tuple(
        _build_fixture_report(index)
        if index <= 18
        else (
            _build_fixture_report(index, eligibility=EligibilityDecision.BLOCKED)
            if index == 19
            else _build_fixture_report(
                index,
                eligibility=EligibilityDecision.CONDITIONAL,
                has_evidence=False,
            )
        )
        for index in range(1, 21)
    )
    with SqlAlchemyMatchReportUnitOfWork(factory) as uow:
        for report in reports:
            uow.reports.add(report)
        uow.commit()

    repository = SqlAlchemyMatchReportQueryRepository(factory)
    stored = repository.list_latest_for_jobs(tuple(report.job_id for report in reports))
    ranked = rank_match_reports(stored)[:top_n]
    result = {
        "mode": "offline_fixture",
        "externalProviderCalls": 0,
        "persistedMatchReports": len(stored),
        "fixtureScenarios": {
            "blocked": sum(
                report.recommendation is MatchRecommendation.BLOCKED for report in reports
            ),
            "withoutEvidence": sum(not report.evidence_links for report in reports),
        },
        "topJobs": [
            {
                "rank": rank,
                "jobId": item.report.job_id,
                "recommendation": item.report.recommendation.value,
                "reason": item.report.summary,
                "evidenceLinks": [
                    {
                        "requirementId": link.requirement_id,
                        "evidenceIds": list(link.evidence_ids),
                    }
                    for link in item.report.evidence_links
                ],
            }
            for rank, item in enumerate(ranked, start=1)
        ],
    }
    engine.dispose()
    return result


def evaluate_mvp_quality_status() -> MvpQualityStatus:
    """Run the blocking MVP checks in isolated SQLite with zero Provider calls."""
    with tempfile.TemporaryDirectory(prefix="joblens-mvp-quality-") as directory:
        root = Path(directory)
        replay_engine = create_engine(f"sqlite+pysqlite:///{root / 'replay.db'}")
        Base.metadata.create_all(replay_engine)
        replay_factory = sessionmaker(
            bind=replay_engine,
            expire_on_commit=False,
            class_=Session,
        )
        try:
            replay = run_offline_requirement_replay_gate(session_factory=replay_factory)
        finally:
            replay_engine.dispose()

        match_demo = run_offline_match_demo(
            database_path=root / "match-demo.db",
            top_n=5,
        )

    replay_passed = bool(replay.gate_passed)
    persisted_reports = int(match_demo.get("persistedMatchReports", 0))
    top_jobs_raw: Any = match_demo.get("topJobs", ())
    top_jobs = tuple(top_jobs_raw) if isinstance(top_jobs_raw, (list, tuple)) else ()
    evidence_complete = bool(top_jobs) and all(
        isinstance(item, dict) and bool(item.get("evidenceLinks")) for item in top_jobs
    )
    match_demo_passed = (
        int(match_demo.get("externalProviderCalls", -1)) == 0
        and persisted_reports >= 20
        and len(top_jobs) == 5
        and evidence_complete
    )
    return MvpQualityStatus(
        gate_passed=replay_passed and match_demo_passed,
        replay_passed=replay_passed,
        replay_passed_cases=int(replay.passed_cases),
        replay_total_cases=int(replay.total_cases),
        match_demo_passed=match_demo_passed,
        match_demo_persisted_reports=persisted_reports,
        match_demo_top_jobs=len(top_jobs),
        match_demo_evidence_complete=evidence_complete,
    )
