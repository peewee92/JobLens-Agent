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
    AbstractUnitOfWork,
)
from app.db.session import SessionLocal
from app.repositories import (
    SqlAlchemyCareerContextQueryRepository,
    SqlAlchemyCareerContextUnitOfWork,
    SqlAlchemyJobImportQueryRepository,
    SqlAlchemyJobQueryRepository,
    SqlAlchemyUnitOfWork,
)

UnitOfWorkFactory = Callable[[], AbstractUnitOfWork]
CareerContextUnitOfWorkFactory = Callable[[], AbstractCareerContextUnitOfWork]


def get_uow_factory() -> UnitOfWorkFactory:
    """Provide a factory; the application use case opens the transaction scope.

    FastAPI owns dependency construction, but the use case owns the exact
    commit/rollback boundary through ``with uow_factory() as uow``.
    """

    return lambda: SqlAlchemyUnitOfWork(SessionLocal)


def get_career_context_uow_factory() -> CareerContextUnitOfWorkFactory:
    return lambda: SqlAlchemyCareerContextUnitOfWork(SessionLocal)


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
