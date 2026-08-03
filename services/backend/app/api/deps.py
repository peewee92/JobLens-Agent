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
from app.application.ports import (
    AbstractCareerContextQueryRepository,
    AbstractCareerContextUnitOfWork,
    AbstractJobImportQueryRepository,
    AbstractJobQueryRepository,
    AbstractProfileExtractor,
    AbstractResumeDocumentParser,
    AbstractTraceUnitOfWork,
    AbstractUnitOfWork,
)
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.document_parsers import ResumeDocumentParser
from app.llm import build_profile_extractor
from app.repositories import (
    SqlAlchemyCareerContextQueryRepository,
    SqlAlchemyCareerContextUnitOfWork,
    SqlAlchemyJobImportQueryRepository,
    SqlAlchemyJobQueryRepository,
    SqlAlchemyTraceUnitOfWork,
    SqlAlchemyUnitOfWork,
)
from app.workflows import (
    ProposeProfileFromDocumentWorkflow,
    ProposeProfileFromResumeWorkflow,
)

UnitOfWorkFactory = Callable[[], AbstractUnitOfWork]
CareerContextUnitOfWorkFactory = Callable[[], AbstractCareerContextUnitOfWork]
TraceUnitOfWorkFactory = Callable[[], AbstractTraceUnitOfWork]


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
