"""Pure-Python composition root shared by the MCP process and its tests."""
from __future__ import annotations

from sqlalchemy import inspect

from app.agent.context import CareerAgentContextBuilder
from app.agent.tool_registry import CareerAgentToolRegistry
from app.application.career_context.release import GetCareerContextReleaseReadinessUseCase
from app.application.create_target_cohort import (
    CreateFeedbackTargetCohortUseCase,
    CreateManualTargetCohortUseCase,
    CreateTargetCohortUseCase,
)
from app.application.job_preparation.bundle import BuildJobPreparationBundleUseCase
from app.application.job_preparation.readiness import GetJobPreparationReadinessUseCase
from app.application.match_inputs.readiness import GetMatchInputReadinessUseCase
from app.application.match_ranking import BatchRankMatchReportsUseCase
from app.application.target_cohort_gap_query import BuildSelectedFeedbackTargetCohortGapDetailsUseCase
from app.application.target_cohort_requirement_aggregation import AggregateTargetCohortRequirementsUseCase
from app.application.user_feedback_target_cohort import UserFeedbackTargetCohortSourceUseCase
from app.db.session import SessionLocal, engine
from app.mcp.adapter import JobLensMcpAdapter
from app.repositories import (
    SqlAlchemyCareerContextQueryRepository,
    SqlAlchemyJobQueryRepository,
    SqlAlchemyJobRequirementQueryRepository,
    SqlAlchemyMatchReportQueryRepository,
    SqlAlchemyRequirementReviewQueryRepository,
)
from app.repositories.sqlalchemy_job_requirement_release_repository import (
    SqlAlchemyJobRequirementReleaseQueryRepository,
)
from app.repositories.sqlalchemy_user_feedback_repository import SqlAlchemyUserFeedbackQueryRepository
from app.repositories.sqlalchemy_user_feedback_schema import inspect_user_feedback_persistence_readiness
from app.application.job_requirements.release import GetJobRequirementReleaseReadinessUseCase


def build_mcp_adapter() -> JobLensMcpAdapter:
    """Build the local adapter without FastAPI dependency injection objects."""
    career_context = SqlAlchemyCareerContextQueryRepository(SessionLocal)
    jobs = SqlAlchemyJobQueryRepository(SessionLocal)
    requirements = SqlAlchemyJobRequirementQueryRepository(SessionLocal)
    reports = SqlAlchemyMatchReportQueryRepository(SessionLocal)
    ranking = BatchRankMatchReportsUseCase(
        report_repository=reports,
        career_context_repository=career_context,
        job_repository=jobs,
        requirement_repository=requirements,
        persistence_ready=lambda: inspect(engine).has_table("match_reports"),
    )
    requirement_release = GetJobRequirementReleaseReadinessUseCase(
        jobs=jobs,
        requirements=requirements,
        reviews=SqlAlchemyRequirementReviewQueryRepository(SessionLocal),
        traces=SqlAlchemyJobRequirementReleaseQueryRepository(SessionLocal),
    )
    feedback_source = UserFeedbackTargetCohortSourceUseCase(
        feedback_repository=SqlAlchemyUserFeedbackQueryRepository(SessionLocal),
        persistence_readiness=lambda: inspect_user_feedback_persistence_readiness(engine),
    )
    target_cohort_gaps = BuildSelectedFeedbackTargetCohortGapDetailsUseCase(
        cohort_creator=CreateTargetCohortUseCase(
            feedback=CreateFeedbackTargetCohortUseCase(source=feedback_source),
            manual=CreateManualTargetCohortUseCase(jobs=jobs),
        ),
        requirement_aggregator=AggregateTargetCohortRequirementsUseCase(
            release_gate=requirement_release,
            requirements=requirements,
        ),
        profiles=career_context,
    )
    match_inputs = GetMatchInputReadinessUseCase(
        career_context=GetCareerContextReleaseReadinessUseCase(career_context),
        job_requirements=requirement_release,
    )
    job_preparation = BuildJobPreparationBundleUseCase(
        readiness=GetJobPreparationReadinessUseCase(match_inputs=match_inputs),
        profiles=career_context,
        requirements=requirements,
    )
    context_builder = CareerAgentContextBuilder(
        career_context=career_context,
        jobs=jobs,
        release_readiness=GetCareerContextReleaseReadinessUseCase(career_context),
    )
    return JobLensMcpAdapter(
        context_builder=context_builder,
        tool_registry=CareerAgentToolRegistry(
            ranking=ranking,
            target_cohort_gaps=target_cohort_gaps,
            job_preparation=job_preparation,
        ),
    )
