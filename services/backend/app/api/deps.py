"""FastAPI dependency providers (Dependency Injection)."""
from collections.abc import Callable

from fastapi import Depends

from app.application.career_context.use_cases import (
    GetProfileUseCase,
    GetSearchIntentUseCase,
    SaveProfileUseCase,
    SaveSearchIntentUseCase,
)
from app.application.job_import_queries.use_cases import GetJobImportDetailUseCase
from app.application.job_imports import ImportJobsUseCase
from app.application.job_queries.use_cases import GetJobUseCase, ListJobsUseCase
from app.application.job_requirements.use_cases import (
    ExtractJobRequirementsUseCase,
    GetJobRequirementExtractionUseCase,
    GetLatestJobRequirementsUseCase,
)
from app.application.profile_evals.use_cases import (
    GetAcceptedProfileEvalBaselineUseCase,
    GetProfileEvalRunUseCase,
    ListProfileEvalRunsUseCase,
    ReviewProfileEvalRunUseCase,
)
from app.application.requirement_evals.use_cases import (
    GetAcceptedRequirementEvalBaselineUseCase,
    GetRequirementEvalRunUseCase,
    ListRequirementEvalRunsUseCase,
    ReviewRequirementEvalRunUseCase,
)
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
    AbstractRequirementEvalQueryRepository,
    AbstractRequirementEvalReviewUnitOfWork,
    AbstractResumeDocumentParser,
    AbstractTraceUnitOfWork,
    AbstractUnitOfWork,
)
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.document_parsers import ResumeDocumentParser
from app.llm import build_job_requirement_extractor, build_profile_extractor
from app.repositories import (
    SqlAlchemyCareerContextQueryRepository,
    SqlAlchemyCareerContextUnitOfWork,
    SqlAlchemyJobImportQueryRepository,
    SqlAlchemyJobQueryRepository,
    SqlAlchemyJobRequirementQueryRepository,
    SqlAlchemyJobRequirementUnitOfWork,
    SqlAlchemyProfileEvalQueryRepository,
    SqlAlchemyProfileEvalReviewUnitOfWork,
    SqlAlchemyRequirementEvalQueryRepository,
    SqlAlchemyRequirementEvalReviewUnitOfWork,
    SqlAlchemyTraceUnitOfWork,
    SqlAlchemyUnitOfWork,
)
from app.workflows import (
    ExtractJobRequirementsWorkflow,
    ProposeProfileFromDocumentWorkflow,
    ProposeProfileFromResumeWorkflow,
)

UnitOfWorkFactory = Callable[[], AbstractUnitOfWork]
CareerContextUnitOfWorkFactory = Callable[[], AbstractCareerContextUnitOfWork]
TraceUnitOfWorkFactory = Callable[[], AbstractTraceUnitOfWork]
ProfileEvalReviewUnitOfWorkFactory = Callable[[], AbstractProfileEvalReviewUnitOfWork]
RequirementEvalReviewUnitOfWorkFactory = Callable[
    [], AbstractRequirementEvalReviewUnitOfWork
]
JobRequirementUnitOfWorkFactory = Callable[[], AbstractJobRequirementUnitOfWork]


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


def get_career_context_query_repository() -> AbstractCareerContextQueryRepository:
    return SqlAlchemyCareerContextQueryRepository(SessionLocal)


def get_get_profile_use_case(
    repository: AbstractCareerContextQueryRepository = Depends(
        get_career_context_query_repository
    ),
) -> GetProfileUseCase:
    return GetProfileUseCase(repository)


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


def get_get_job_use_case(
    repository: AbstractJobQueryRepository = Depends(get_job_query_repository),
) -> GetJobUseCase:
    return GetJobUseCase(repository)


def get_import_jobs_use_case(
    uow_factory: UnitOfWorkFactory = Depends(get_uow_factory),
) -> ImportJobsUseCase:
    """Assemble the HTTP adapter around the stable application use case."""

    return ImportJobsUseCase(uow_factory)
