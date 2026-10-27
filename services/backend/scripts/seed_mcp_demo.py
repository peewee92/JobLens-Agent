"""Create a disposable, fully synthetic SQLite database for the MCP demo.

The command constructs 20 synthetic Job/Requirement review cases because the
same Requirement release gate used by JobLens requires a complete 20-case human
review baseline. It never reads resumes, Collector exports, or Provider keys.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
from dataclasses import replace
from pathlib import Path

from sqlalchemy import create_engine
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
from app.db.models import (
    JobORM,
    JobRequirementExtractionORM,
    JobRequirementORM,
    JobSourceORM,
    MatchReportORM,
    ProfileEvidenceORM,
    ProfileSkillEvidenceORM,
    ProfileSkillORM,
    RequirementReviewBatchCaseORM,
    RequirementReviewBatchFinalDecisionORM,
    RequirementReviewBatchORM,
    RequirementReviewCaseReviewORM,
    SearchIntentORM,
    TraceSpanORM,
    UserProfileORM,
)
from app.domain.career_context import EvidenceType, SkillLevel
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.domain.jobs import RemoteConfidence, RemoteStatus
from app.repositories.sqlalchemy_match_report_repository import _snapshot, _stored
from app.repositories.sqlalchemy_career_context_repository import SqlAlchemyCareerContextQueryRepository
from app.repositories.sqlalchemy_job_query_repository import SqlAlchemyJobQueryRepository
from app.application.search_preferences import evaluate_search_preferences, preference_input_fingerprint

CASE_COUNT = 20
PROFILE_ID = "prof_mcp_demo"
EVIDENCE_ID = "ev_mcp_demo_python"
SKILL_ID = "skill_mcp_demo_python"
BATCH_ID = "reqreviewbatch_mcp_demo"
EXTRACTOR_VERSION = "synthetic-mcp-extractor-v1"
PROMPT_VERSION = "synthetic-mcp-prompt-v1"
MODEL = "synthetic-mcp-model"
SEMANTIC_POLICY_VERSION = "synthetic-mcp-semantics-v1"


def _requirement_payload(job_id: str, requirement_id: str) -> dict[str, object]:
    text = "Demonstrated Python backend and Agent workflow implementation experience."
    return {
        "type": "skill",
        "originalText": text,
        "normalizedCapability": "Python",
        "importance": "must_have",
        "evidenceSpan": text,
        "confidence": 1.0,
    }


def _add_synthetic_profile(session: Session) -> None:
    session.add_all(
        [
            UserProfileORM(
                id=PROFILE_ID,
                profile_key="default",
                version=1,
                headline="Synthetic AI application engineer demo profile",
                years_of_experience=5,
            ),
            ProfileEvidenceORM(
                id=EVIDENCE_ID,
                profile_id=PROFILE_ID,
                evidence_key="python-agent-project",
                type=EvidenceType.PROJECT,
                summary="Built a synthetic Python backend and Agent workflow demonstration.",
                source="synthetic MCP demo seed",
            ),
            ProfileSkillORM(
                id=SKILL_ID,
                profile_id=PROFILE_ID,
                name="Python",
                normalized_name="python",
                level=SkillLevel.STRONG,
            ),
            ProfileSkillEvidenceORM(skill_id=SKILL_ID, evidence_id=EVIDENCE_ID),
            SearchIntentORM(
                id="intent_mcp_demo",
                intent_key="default",
                version=1,
                target_roles=["Synthetic AI Engineer"],
                cities=["Synthetic City"],
                remote_accepted=True,
                minimum_salary_k=None,
                seniority=None,
                employment_types=[],
                exclude_keywords=[],
                hard_constraints=[],
                soft_preferences=["Synthetic City"],
            ),
        ]
    )


def _add_reviewed_jobs(session: Session) -> list[str]:
    job_ids: list[str] = []
    batch = RequirementReviewBatchORM(
        id=BATCH_ID,
        title="Synthetic MCP demo requirement review",
        reviewer="synthetic-demo-reviewer",
        provider="synthetic_demo",
        model=MODEL,
        extractor_version=EXTRACTOR_VERSION,
        prompt_version=PROMPT_VERSION,
        sample_size=CASE_COUNT,
    )
    session.add(batch)
    for index in range(1, CASE_COUNT + 1):
        job_id = f"job_mcp_demo_{index:02d}"
        extraction_id = f"reqrun_mcp_demo_{index:02d}"
        requirement_id = f"req_mcp_demo_{index:02d}"
        trace_id = f"run_mcp_demo_{index:02d}"
        case_id = f"reqreviewcase_mcp_demo_{index:02d}"
        description = "Demonstrated Python backend and Agent workflow implementation experience."
        input_hash = sha256(description.encode("utf-8")).hexdigest()
        payload = _requirement_payload(job_id, requirement_id)
        session.add_all(
            [
                JobORM(
                    id=job_id,
                    canonical_key=f"synthetic-mcp-demo:{index}",
                    canonical_key_version="v1",
                    title=f"Synthetic AI Engineer {index:02d}",
                    company="JobLens Synthetic Demo",
                    area="Synthetic City",
                    salary_min_k=20,
                    salary_max_k=30,
                    description=description,
                    skills=["Python", "Agent"],
                    remote_status=RemoteStatus.CONFIRMED,
                    remote_confidence=RemoteConfidence.HIGH,
                ),
                JobSourceORM(
                    id=f"src_mcp_demo_{index:02d}",
                    job_id=job_id,
                    source="synthetic_demo",
                    source_job_id=str(index),
                    source_url=f"https://example.invalid/mcp-demo/{index}",
                    normalized_source_url=f"https://example.invalid/mcp-demo/{index}",
                    source_version="synthetic-v1",
                    source_raw={"synthetic": True},
                ),
                TraceSpanORM(
                    id=trace_id,
                    capability="requirement_extraction",
                    version=EXTRACTOR_VERSION,
                    model=MODEL,
                    prompt_version=PROMPT_VERSION,
                    input_refs={"jobId": job_id, "descriptionSha256": input_hash},
                    output={"requirements": [payload], "semanticPolicyVersion": SEMANTIC_POLICY_VERSION},
                    latency_ms=0,
                    input_tokens=0,
                    output_tokens=0,
                    error=None,
                ),
                JobRequirementExtractionORM(
                    id=extraction_id,
                    job_id=job_id,
                    input_hash=input_hash,
                    description_characters=len(description),
                    extractor_version=EXTRACTOR_VERSION,
                    provider="synthetic_demo",
                    model=MODEL,
                    prompt_version=PROMPT_VERSION,
                    trace_run_id=trace_id,
                    requirement_count=1,
                ),
                JobRequirementORM(
                    id=requirement_id,
                    extraction_id=extraction_id,
                    job_id=job_id,
                    requirement_index=0,
                    type=RequirementType.SKILL,
                    original_text=description,
                    normalized_capability="Python",
                    importance=RequirementImportance.MUST_HAVE,
                    evidence_span=description,
                    confidence=1.0,
                    extractor_version=EXTRACTOR_VERSION,
                ),
                RequirementReviewBatchCaseORM(
                    id=case_id,
                    batch_id=BATCH_ID,
                    case_index=index - 1,
                    job_id=job_id,
                    extraction_id=extraction_id,
                ),
                RequirementReviewCaseReviewORM(
                    id=f"reqreview_mcp_demo_{index:02d}",
                    batch_case_id=case_id,
                    decision="accepted",
                    issue_codes=[],
                    notes="Synthetic demo fact reviewed and accepted.",
                ),
            ]
        )
        report = MatchReport(
            job_id=job_id,
            profile_id=PROFILE_ID,
            profile_version=1,
            extraction_id=extraction_id,
            eligibility=EligibilityDecision.ELIGIBLE,
            recommendation=MatchRecommendation.STRONG,
            summary="Synthetic demo: confirmed Python evidence supports the released requirement.",
            strengths=(
                MatchReportInsight(
                    requirement_id=requirement_id,
                    requirement_text=description,
                    reason="Confirmed synthetic profile evidence directly supports Python.",
                    evidence_ids=(EVIDENCE_ID,),
                ),
            ),
            risks=(),
            requirement_results=(
                MatchReportRequirementResult(
                    requirement_id=requirement_id,
                    requirement_index=0,
                    type=RequirementType.SKILL,
                    importance=RequirementImportance.MUST_HAVE,
                    original_text=description,
                    normalized_capability="Python",
                    eligibility_status=RequirementFitStatus.MATCHED,
                    semantic_verdict=SemanticMatchVerdict.MATCHED,
                    evidence_ids=(EVIDENCE_ID,),
                    profile_fact_refs=(f"profile.skill.{SKILL_ID}",),
                    reason="Confirmed synthetic evidence directly supports Python.",
                ),
            ),
            matched_requirement_ids=(requirement_id,),
            partial_requirement_ids=(),
            missing_requirement_ids=(),
            evidence_links=(MatchEvidenceLink(requirement_id, (EVIDENCE_ID,)),),
            matcher_version="synthetic-mcp-matcher-v1",
            prompt_version="not-applicable",
            model=None,
            trace_run_id=None,
        )
        session.add(
            MatchReportORM(
                id=f"match_mcp_demo_{index:02d}",
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
        )
        job_ids.append(job_id)
    session.add(
        RequirementReviewBatchFinalDecisionORM(
            id="reqbatchdecision_mcp_demo",
            batch_id=BATCH_ID,
            decision="accept_for_match",
            reviewer="synthetic-demo-reviewer",
            notes="Synthetic demo review baseline accepted for local MCP demonstration.",
            sample_size=CASE_COUNT,
            reviewed_count=CASE_COUNT,
            accepted_count=CASE_COUNT,
            rejected_count=0,
            stale_case_count=0,
            issue_code_counts={},
            evidence_fingerprint="a" * 64,
        )
    )
    return job_ids


def seed(database: Path) -> list[str]:
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    with factory.begin() as session:
        _add_synthetic_profile(session)
        job_ids = _add_reviewed_jobs(session)
    # Bind synthetic snapshots to the same versioned inputs required by live ranking.
    # This updates only this newly created disposable demo database.
    intent = SqlAlchemyCareerContextQueryRepository(factory).get_current_search_intent()
    jobs = SqlAlchemyJobQueryRepository(factory)
    with factory.begin() as session:
        for job_id in job_ids:
            record = session.get(MatchReportORM, f"match_mcp_demo_{job_id.rsplit('_', 1)[-1]}")
            job = jobs.get_job(job_id)
            report = replace(_stored(record).report, search_intent_id=intent.id,
                             search_intent_version=intent.version,
                             preference_checks=evaluate_search_preferences(intent, job),
                             preference_fingerprint=preference_input_fingerprint(intent, job))
            record.snapshot = _snapshot(report)
    engine.dispose()
    return job_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args()
    job_ids = seed(args.database)
    print("Synthetic MCP demo database created; no personal data or Provider calls were used.")
    print("\n".join(job_ids[:2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
