"""FastAPI dependency providers (Dependency Injection)."""
from collections.abc import Callable
from pathlib import Path

from fastapi import Depends
from sqlalchemy import inspect

from app.application.career_context.release import (
    GetCareerContextReleaseReadinessUseCase,
)
from app.application.career_context.use_cases import (
    GetProfileUseCase,
    GetSearchIntentUseCase,
    SaveProfileUseCase,
    SaveSearchIntentUseCase,
)
from app.application.eligibility import EvaluateJobEligibilityUseCase
from app.application.evidence_retrieval import RetrieveJobEvidenceUseCase
from app.application.job_import_queries.use_cases import GetJobImportDetailUseCase
from app.application.job_imports import ImportJobsUseCase
from app.application.job_queries.use_cases import GetJobUseCase, ListJobsUseCase
from app.application.job_requirements.release import (
    GetJobRequirementReleaseReadinessUseCase,
)
from app.application.job_requirements.use_cases import (
    ExtractJobRequirementsUseCase,
    GetJobRequirementExtractionUseCase,
    GetLatestJobRequirementsUseCase,
)
from app.application.match_inputs.readiness import GetMatchInputReadinessUseCase
from app.application.match_report import BuildJobMatchReportUseCase
from app.application.match_review import GetMatchReviewReadinessUseCase
from app.application.semantic_match.use_case import RunJobSemanticMatchUseCase
from app.application.profile_evals.use_cases import (
    GetAcceptedProfileEvalBaselineUseCase,
    GetProfileEvalRunUseCase,
    ListProfileEvalRunsUseCase,
    ReviewProfileEvalRunUseCase,
)
from app.application.requirement_acceptance.readiness_dashboard import (
    GetRequirementAcceptanceReadinessDashboardUseCase,
)
from app.application.requirement_acceptance.run_use_cases import (
    GetRequirementAcceptanceRunUseCase,
    ListRequirementAcceptanceRunsUseCase,
    ReviewRequirementAcceptanceCanaryUseCase,
)
from app.application.requirement_evals.use_cases import (
    GetAcceptedRequirementEvalBaselineUseCase,
    GetRequirementEvalRunUseCase,
    ListRequirementEvalRunsUseCase,
    ReviewRequirementEvalRunUseCase,
)
from app.application.requirement_reviews.use_cases import (
    CreateRequirementReviewBatchUseCase,
    FinalizeRequirementReviewBatchUseCase,
    GetAcceptedRequirementReviewBaselineUseCase,
    GetRequirementReviewBatchUseCase,
    ListRequirementReviewBatchesUseCase,
    ListRequirementReviewCandidatesUseCase,
    ReviewRequirementBatchCaseUseCase,
)
from app.application.ports.job_requirement_release_repository import (
    AbstractJobRequirementReleaseQueryRepository,
)
from app.application.ports.semantic_matcher import AbstractSemanticMatcher
from app.application.ports import (
    AbstractCareerContextQueryRepository,
    AbstractCareerContextUnitOfWork,
    AbstractJobImportQueryRepository,
    AbstractJobQueryRepository,
    AbstractJobRequirementExtractor,
    AbstractJobRequirementQueryRepository,
    AbstractJobRequirementUnitOfWork,
    AbstractProfileEvalQueryRepository,
    AbstractProfileEvalReviewUnitOfWork,
    AbstractProfileExtractor,
    AbstractRequirementAcceptanceRunQueryRepository,
    AbstractRequirementAcceptanceRunUnitOfWork,
    AbstractRequirementEvalQueryRepository,
    AbstractRequirementEvalReviewUnitOfWork,
    AbstractRequirementReviewQueryRepository,
    AbstractRequirementReviewUnitOfWork,
    AbstractResumeDocumentParser,
    AbstractTraceUnitOfWork,
    AbstractUnitOfWork,
)
from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.document_parsers import ResumeDocumentParser
from app.llm import (
    build_job_requirement_extractor,
    build_profile_extractor,
    build_semantic_matcher,
)
from app.repositories.sqlalchemy_job_requirement_release_repository import (
    SqlAlchemyJobRequirementReleaseQueryRepository,
)
from app.repositories import (
    SqlAlchemyCareerContextQueryRepository,
    SqlAlchemyCareerContextUnitOfWork,
    SqlAlchemyJobImportQueryRepository,
    SqlAlchemyJobQueryRepository,
    SqlAlchemyJobRequirementQueryRepository,
    SqlAlchemyJobRequirementUnitOfWork,
    SqlAlchemyMatchReportUnitOfWork,
    SqlAlchemyProfileEvalQueryRepository,
    SqlAlchemyProfileEvalReviewUnitOfWork,
    SqlAlchemyRequirementAcceptanceRunQueryRepository,
    SqlAlchemyRequirementAcceptanceRunUnitOfWork,
    SqlAlchemyRequirementEvalQueryRepository,
    SqlAlchemyRequirementEvalReviewUnitOfWork,
    SqlAlchemyRequirementReviewQueryRepository,
    SqlAlchemyRequirementReviewUnitOfWork,
    SqlAlchemyTraceUnitOfWork,
    SqlAlchemyUnitOfWork,
)
from app.workflows import (
    ExtractJobRequirementsWorkflow,
    ProposeProfileFromDocumentWorkflow,
    ProposeProfileFromResumeWorkflow,
    SemanticMatchWorkflow,
)
from app.workflows.job_requirement_extraction import EXTRACTOR_VERSION, PROMPT_VERSION

UnitOfWorkFactory = Callable[[], AbstractUnitOfWork]
CareerContextUnitOfWorkFactory = Callable[[], AbstractCareerContextUnitOfWork]
TraceUnitOfWorkFactory = Callable[[], AbstractTraceUnitOfWork]
ProfileEvalReviewUnitOfWorkFactory = Callable[[], AbstractProfileEvalReviewUnitOfWork]
RequirementEvalReviewUnitOfWorkFactory = Callable[
    [], AbstractRequirementEvalReviewUnitOfWork
]
RequirementReviewUnitOfWorkFactory = Callable[
    [], AbstractRequirementReviewUnitOfWork
]
JobRequirementUnitOfWorkFactory = Callable[[], AbstractJobRequirementUnitOfWork]
RequirementAcceptanceRunUnitOfWorkFactory = Callable[
    [], AbstractRequirementAcceptanceRunUnitOfWork
]


def get_uow_factory() -> UnitOfWorkFactory:
    """Provide a factory; the application use case opens the transaction scope.

    FastAPI owns dependency construction, but the use case owns the exact
    commit/rollback boundary through ``with uow_factory() as uow``.
    """

    return lambda: SqlAlchemyUnitOfWork(SessionLocal)


def get_career_context_uow_factory() -> CareerContextUnitOfWorkFactory:
    return lambda: SqlAlchemyCareerContextUnitOfWork(SessionLocal)


def get_trace_uow_factory() -> TraceUnitOfWorkFactory:
    return lambda: SqlAlchemyTraceUnitOfWork(SessionLocal)


def get_profile_extractor() -> AbstractProfileExtractor:
    return build_profile_extractor(get_settings())


def get_profile_extraction_workflow(
    extractor: AbstractProfileExtractor = Depends(get_profile_extractor),
    trace_uow_factory: TraceUnitOfWorkFactory = Depends(get_trace_uow_factory),
) -> ProposeProfileFromResumeWorkflow:
    return ProposeProfileFromResumeWorkflow(extractor, trace_uow_factory)


def get_resume_document_parser() -> AbstractResumeDocumentParser:
    return ResumeDocumentParser()


def get_profile_document_workflow(
    parser: AbstractResumeDocumentParser = Depends(get_resume_document_parser),
    profile_workflow: ProposeProfileFromResumeWorkflow = Depends(
        get_profile_extraction_workflow
    ),
) -> ProposeProfileFromDocumentWorkflow:
    return ProposeProfileFromDocumentWorkflow(parser, profile_workflow)


def get_job_requirement_extractor() -> AbstractJobRequirementExtractor:
    return build_job_requirement_extractor(get_settings())


def get_job_requirement_workflow(
    extractor: AbstractJobRequirementExtractor = Depends(
        get_job_requirement_extractor
    ),
    trace_uow_factory: TraceUnitOfWorkFactory = Depends(get_trace_uow_factory),
) -> ExtractJobRequirementsWorkflow:
    return ExtractJobRequirementsWorkflow(extractor, trace_uow_factory)


def get_semantic_matcher() -> AbstractSemanticMatcher:
    return build_semantic_matcher(get_settings())


def get_semantic_match_workflow(
    matcher: AbstractSemanticMatcher = Depends(get_semantic_matcher),
    trace_uow_factory: TraceUnitOfWorkFactory = Depends(get_trace_uow_factory),
) -> SemanticMatchWorkflow:
    return SemanticMatchWorkflow(
        matcher=matcher,
        trace_uow_factory=trace_uow_factory,
    )


def get_job_requirement_query_repository() -> AbstractJobRequirementQueryRepository:
    return SqlAlchemyJobRequirementQueryRepository(SessionLocal)


def get_job_requirement_uow_factory() -> JobRequirementUnitOfWorkFactory:
    return lambda: SqlAlchemyJobRequirementUnitOfWork(SessionLocal)


def get_profile_eval_query_repository() -> AbstractProfileEvalQueryRepository:
    return SqlAlchemyProfileEvalQueryRepository(SessionLocal)


def get_profile_eval_review_uow_factory() -> ProfileEvalReviewUnitOfWorkFactory:
    return lambda: SqlAlchemyProfileEvalReviewUnitOfWork(SessionLocal)


def get_list_profile_eval_runs_use_case(
    repository: AbstractProfileEvalQueryRepository = Depends(
        get_profile_eval_query_repository
    ),
) -> ListProfileEvalRunsUseCase:
    return ListProfileEvalRunsUseCase(repository)


def get_get_profile_eval_run_use_case(
    repository: AbstractProfileEvalQueryRepository = Depends(
        get_profile_eval_query_repository
    ),
) -> GetProfileEvalRunUseCase:
    return GetProfileEvalRunUseCase(repository)


def get_review_profile_eval_run_use_case(
    repository: AbstractProfileEvalQueryRepository = Depends(
        get_profile_eval_query_repository
    ),
    uow_factory: ProfileEvalReviewUnitOfWorkFactory = Depends(
        get_profile_eval_review_uow_factory
    ),
) -> ReviewProfileEvalRunUseCase:
    return ReviewProfileEvalRunUseCase(repository, uow_factory)


def get_accepted_profile_eval_baseline_use_case(
    repository: AbstractProfileEvalQueryRepository = Depends(
        get_profile_eval_query_repository
    ),
) -> GetAcceptedProfileEvalBaselineUseCase:
    return GetAcceptedProfileEvalBaselineUseCase(repository)


def get_requirement_eval_query_repository() -> AbstractRequirementEvalQueryRepository:
    return SqlAlchemyRequirementEvalQueryRepository(SessionLocal)


def get_requirement_eval_review_uow_factory() -> RequirementEvalReviewUnitOfWorkFactory:
    return lambda: SqlAlchemyRequirementEvalReviewUnitOfWork(SessionLocal)


def get_list_requirement_eval_runs_use_case(
    repository: AbstractRequirementEvalQueryRepository = Depends(
        get_requirement_eval_query_repository
    ),
) -> ListRequirementEvalRunsUseCase:
    return ListRequirementEvalRunsUseCase(repository)


def get_get_requirement_eval_run_use_case(
    repository: AbstractRequirementEvalQueryRepository = Depends(
        get_requirement_eval_query_repository
    ),
) -> GetRequirementEvalRunUseCase:
    return GetRequirementEvalRunUseCase(repository)


def get_review_requirement_eval_run_use_case(
    repository: AbstractRequirementEvalQueryRepository = Depends(
        get_requirement_eval_query_repository
    ),
    uow_factory: RequirementEvalReviewUnitOfWorkFactory = Depends(
        get_requirement_eval_review_uow_factory
    ),
) -> ReviewRequirementEvalRunUseCase:
    return ReviewRequirementEvalRunUseCase(repository, uow_factory)


def get_accepted_requirement_eval_baseline_use_case(
    repository: AbstractRequirementEvalQueryRepository = Depends(
        get_requirement_eval_query_repository
    ),
) -> GetAcceptedRequirementEvalBaselineUseCase:
    return GetAcceptedRequirementEvalBaselineUseCase(repository)


def get_requirement_acceptance_run_query_repository() -> (
    AbstractRequirementAcceptanceRunQueryRepository
):
    return SqlAlchemyRequirementAcceptanceRunQueryRepository(SessionLocal)


def get_requirement_acceptance_readiness_dashboard_use_case(
    repository: AbstractRequirementAcceptanceRunQueryRepository = Depends(
        get_requirement_acceptance_run_query_repository
    ),
) -> GetRequirementAcceptanceReadinessDashboardUseCase:
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    project_root = backend_root.parents[1]
    private_root = (
        Path(settings.requirement_acceptance_private_root).expanduser().resolve()
        if settings.requirement_acceptance_private_root
        else project_root / "data" / "private" / "requirement-acceptance"
    )
    return GetRequirementAcceptanceReadinessDashboardUseCase(
        runs=repository,
        private_root=private_root,
        backend_root=backend_root,
        database_url=settings.database_url,
        provider=settings.requirement_extractor_provider,
        model=settings.requirement_extractor_model,
        api_key_configured=bool(settings.openai_api_key),
        extractor_version=EXTRACTOR_VERSION,
        prompt_version=PROMPT_VERSION,
        web_base_url=settings.web_base_url,
    )


def get_list_requirement_acceptance_runs_use_case(
    repository: AbstractRequirementAcceptanceRunQueryRepository = Depends(
        get_requirement_acceptance_run_query_repository
    ),
) -> ListRequirementAcceptanceRunsUseCase:
    return ListRequirementAcceptanceRunsUseCase(repository)


def get_requirement_acceptance_run_use_case(
    repository: AbstractRequirementAcceptanceRunQueryRepository = Depends(
        get_requirement_acceptance_run_query_repository
    ),
) -> GetRequirementAcceptanceRunUseCase:
    return GetRequirementAcceptanceRunUseCase(repository)


def get_requirement_acceptance_run_uow_factory() -> (
    RequirementAcceptanceRunUnitOfWorkFactory
):
    return lambda: SqlAlchemyRequirementAcceptanceRunUnitOfWork(SessionLocal)


def get_review_requirement_acceptance_canary_use_case(
    repository: AbstractRequirementAcceptanceRunQueryRepository = Depends(
        get_requirement_acceptance_run_query_repository
    ),
    uow_factory: RequirementAcceptanceRunUnitOfWorkFactory = Depends(
        get_requirement_acceptance_run_uow_factory
    ),
) -> ReviewRequirementAcceptanceCanaryUseCase:
    return ReviewRequirementAcceptanceCanaryUseCase(repository, uow_factory)


def get_requirement_review_query_repository() -> AbstractRequirementReviewQueryRepository:
    return SqlAlchemyRequirementReviewQueryRepository(SessionLocal)


def get_requirement_review_uow_factory() -> RequirementReviewUnitOfWorkFactory:
    return lambda: SqlAlchemyRequirementReviewUnitOfWork(SessionLocal)


def get_list_requirement_review_candidates_use_case(
    repository: AbstractRequirementReviewQueryRepository = Depends(
        get_requirement_review_query_repository
    ),
) -> ListRequirementReviewCandidatesUseCase:
    return ListRequirementReviewCandidatesUseCase(repository)


def get_create_requirement_review_batch_use_case(
    repository: AbstractRequirementReviewQueryRepository = Depends(
        get_requirement_review_query_repository
    ),
    uow_factory: RequirementReviewUnitOfWorkFactory = Depends(
        get_requirement_review_uow_factory
    ),
) -> CreateRequirementReviewBatchUseCase:
    return CreateRequirementReviewBatchUseCase(repository, uow_factory)


def get_list_requirement_review_batches_use_case(
    repository: AbstractRequirementReviewQueryRepository = Depends(
        get_requirement_review_query_repository
    ),
) -> ListRequirementReviewBatchesUseCase:
    return ListRequirementReviewBatchesUseCase(repository)


def get_get_requirement_review_batch_use_case(
    repository: AbstractRequirementReviewQueryRepository = Depends(
        get_requirement_review_query_repository
    ),
) -> GetRequirementReviewBatchUseCase:
    return GetRequirementReviewBatchUseCase(repository)


def get_review_requirement_batch_case_use_case(
    repository: AbstractRequirementReviewQueryRepository = Depends(
        get_requirement_review_query_repository
    ),
    uow_factory: RequirementReviewUnitOfWorkFactory = Depends(
        get_requirement_review_uow_factory
    ),
) -> ReviewRequirementBatchCaseUseCase:
    return ReviewRequirementBatchCaseUseCase(repository, uow_factory)


def get_finalize_requirement_review_batch_use_case(
    repository: AbstractRequirementReviewQueryRepository = Depends(
        get_requirement_review_query_repository
    ),
    uow_factory: RequirementReviewUnitOfWorkFactory = Depends(
        get_requirement_review_uow_factory
    ),
) -> FinalizeRequirementReviewBatchUseCase:
    return FinalizeRequirementReviewBatchUseCase(repository, uow_factory)


def get_accepted_requirement_review_baseline_use_case(
    repository: AbstractRequirementReviewQueryRepository = Depends(
        get_requirement_review_query_repository
    ),
) -> GetAcceptedRequirementReviewBaselineUseCase:
    return GetAcceptedRequirementReviewBaselineUseCase(repository)


def get_career_context_query_repository() -> AbstractCareerContextQueryRepository:
    return SqlAlchemyCareerContextQueryRepository(SessionLocal)


def get_get_profile_use_case(
    repository: AbstractCareerContextQueryRepository = Depends(
        get_career_context_query_repository
    ),
) -> GetProfileUseCase:
    return GetProfileUseCase(repository)


def get_career_context_release_readiness_use_case(
    repository: AbstractCareerContextQueryRepository = Depends(
        get_career_context_query_repository
    ),
) -> GetCareerContextReleaseReadinessUseCase:
    return GetCareerContextReleaseReadinessUseCase(repository)


def get_save_profile_use_case(
    uow_factory: CareerContextUnitOfWorkFactory = Depends(
        get_career_context_uow_factory
    ),
) -> SaveProfileUseCase:
    return SaveProfileUseCase(uow_factory)


def get_get_search_intent_use_case(
    repository: AbstractCareerContextQueryRepository = Depends(
        get_career_context_query_repository
    ),
) -> GetSearchIntentUseCase:
    return GetSearchIntentUseCase(repository)


def get_save_search_intent_use_case(
    uow_factory: CareerContextUnitOfWorkFactory = Depends(
        get_career_context_uow_factory
    ),
) -> SaveSearchIntentUseCase:
    return SaveSearchIntentUseCase(uow_factory)


def get_job_import_query_repository() -> AbstractJobImportQueryRepository:
    """Provide the read-only Job Import audit repository."""

    return SqlAlchemyJobImportQueryRepository(SessionLocal)


def get_job_import_detail_use_case(
    repository: AbstractJobImportQueryRepository = Depends(
        get_job_import_query_repository
    ),
) -> GetJobImportDetailUseCase:
    return GetJobImportDetailUseCase(repository)


def get_job_query_repository() -> AbstractJobQueryRepository:
    """Provide the read-only Job Pool repository."""

    return SqlAlchemyJobQueryRepository(SessionLocal)


def get_extract_job_requirements_use_case(
    jobs: AbstractJobQueryRepository = Depends(get_job_query_repository),
    workflow: ExtractJobRequirementsWorkflow = Depends(
        get_job_requirement_workflow
    ),
    uow_factory: JobRequirementUnitOfWorkFactory = Depends(
        get_job_requirement_uow_factory
    ),
    repository: AbstractJobRequirementQueryRepository = Depends(
        get_job_requirement_query_repository
    ),
) -> ExtractJobRequirementsUseCase:
    return ExtractJobRequirementsUseCase(
        jobs=jobs,
        workflow=workflow,
        uow_factory=uow_factory,
        query_repository=repository,
        provider=get_settings().requirement_extractor_provider,
    )


def get_job_requirement_release_query_repository() -> (
    AbstractJobRequirementReleaseQueryRepository
):
    return SqlAlchemyJobRequirementReleaseQueryRepository(SessionLocal)


def get_job_requirement_release_readiness_use_case(
    jobs: AbstractJobQueryRepository = Depends(get_job_query_repository),
    requirements: AbstractJobRequirementQueryRepository = Depends(
        get_job_requirement_query_repository
    ),
    reviews: AbstractRequirementReviewQueryRepository = Depends(
        get_requirement_review_query_repository
    ),
    traces: AbstractJobRequirementReleaseQueryRepository = Depends(
        get_job_requirement_release_query_repository
    ),
) -> GetJobRequirementReleaseReadinessUseCase:
    return GetJobRequirementReleaseReadinessUseCase(
        jobs=jobs,
        requirements=requirements,
        reviews=reviews,
        traces=traces,
    )


def get_match_input_readiness_use_case(
    career_context: GetCareerContextReleaseReadinessUseCase = Depends(
        get_career_context_release_readiness_use_case
    ),
    job_requirements: GetJobRequirementReleaseReadinessUseCase = Depends(
        get_job_requirement_release_readiness_use_case
    ),
) -> GetMatchInputReadinessUseCase:
    return GetMatchInputReadinessUseCase(
        career_context=career_context,
        job_requirements=job_requirements,
    )


def get_job_eligibility_use_case(
    readiness: GetMatchInputReadinessUseCase = Depends(
        get_match_input_readiness_use_case
    ),
    profiles: AbstractCareerContextQueryRepository = Depends(
        get_career_context_query_repository
    ),
    requirements: AbstractJobRequirementQueryRepository = Depends(
        get_job_requirement_query_repository
    ),
) -> EvaluateJobEligibilityUseCase:
    return EvaluateJobEligibilityUseCase(
        readiness=readiness,
        profiles=profiles,
        requirements=requirements,
    )


def get_job_evidence_retrieval_use_case(
    readiness: GetMatchInputReadinessUseCase = Depends(
        get_match_input_readiness_use_case
    ),
    profiles: AbstractCareerContextQueryRepository = Depends(
        get_career_context_query_repository
    ),
    requirements: AbstractJobRequirementQueryRepository = Depends(
        get_job_requirement_query_repository
    ),
) -> RetrieveJobEvidenceUseCase:
    return RetrieveJobEvidenceUseCase(
        readiness=readiness,
        profiles=profiles,
        requirements=requirements,
    )


def get_semantic_match_use_case(
    eligibility: EvaluateJobEligibilityUseCase = Depends(get_job_eligibility_use_case),
    evidence: RetrieveJobEvidenceUseCase = Depends(
        get_job_evidence_retrieval_use_case
    ),
    workflow: SemanticMatchWorkflow = Depends(get_semantic_match_workflow),
) -> RunJobSemanticMatchUseCase:
    return RunJobSemanticMatchUseCase(
        eligibility=eligibility,
        evidence=evidence,
        workflow=workflow,
    )


def get_match_report_use_case(
    semantic_match: RunJobSemanticMatchUseCase = Depends(get_semantic_match_use_case),
) -> BuildJobMatchReportUseCase:
    return BuildJobMatchReportUseCase(
        semantic_match,
        persistence_ready=lambda: inspect(engine).has_table("match_reports"),
        uow_factory=lambda: SqlAlchemyMatchReportUnitOfWork(SessionLocal),
    )


def get_latest_job_requirements_use_case(
    jobs: AbstractJobQueryRepository = Depends(get_job_query_repository),
    repository: AbstractJobRequirementQueryRepository = Depends(
        get_job_requirement_query_repository
    ),
) -> GetLatestJobRequirementsUseCase:
    return GetLatestJobRequirementsUseCase(jobs=jobs, repository=repository)


def get_job_requirement_extraction_use_case(
    jobs: AbstractJobQueryRepository = Depends(get_job_query_repository),
    repository: AbstractJobRequirementQueryRepository = Depends(
        get_job_requirement_query_repository
    ),
) -> GetJobRequirementExtractionUseCase:
    return GetJobRequirementExtractionUseCase(jobs=jobs, repository=repository)


def get_list_jobs_use_case(
    repository: AbstractJobQueryRepository = Depends(get_job_query_repository),
) -> ListJobsUseCase:
    return ListJobsUseCase(repository)


def get_match_review_readiness_use_case(
    jobs: ListJobsUseCase = Depends(get_list_jobs_use_case),
    match_inputs: GetMatchInputReadinessUseCase = Depends(
        get_match_input_readiness_use_case
    ),
) -> GetMatchReviewReadinessUseCase:
    return GetMatchReviewReadinessUseCase(
        jobs=jobs,
        match_inputs=match_inputs,
        persistence_ready=lambda: inspect(engine).has_table("match_reports"),
    )


def get_get_job_use_case(
    repository: AbstractJobQueryRepository = Depends(get_job_query_repository),
) -> GetJobUseCase:
    return GetJobUseCase(repository)


def get_import_jobs_use_case(
    uow_factory: UnitOfWorkFactory = Depends(get_uow_factory),
) -> ImportJobsUseCase:
    """Assemble the HTTP adapter around the stable application use case."""

    return ImportJobsUseCase(uow_factory)
