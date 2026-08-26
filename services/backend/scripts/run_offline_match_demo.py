"""Run a deterministic offline MatchReport -> Top-N demo using SQLite fixtures."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

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
from app.llm.semantic_matchers import FixtureSemanticMatcher
from app.repositories.sqlalchemy_match_report_repository import SqlAlchemyMatchReportQueryRepository
from app.repositories.sqlalchemy_match_report_unit_of_work import SqlAlchemyMatchReportUnitOfWork


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


def run_demo(*, database_path: Path, top_n: int = 5) -> dict[str, object]:
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.top_n < 1 or args.top_n > 50:
        parser.error("--top-n must be between 1 and 50")

    if args.database is None:
        with tempfile.TemporaryDirectory(prefix="joblens-offline-match-") as directory:
            result = run_demo(database_path=Path(directory) / "demo.db", top_n=args.top_n)
    else:
        result = run_demo(database_path=args.database, top_n=args.top_n)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Offline fixture Top {len(result['topJobs'])}: externalProviderCalls=0")
        for item in result["topJobs"]:
            print(f"{item['rank']}. {item['jobId']} — {item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
