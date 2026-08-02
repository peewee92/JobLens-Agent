"""FastAPI dependency providers (Dependency Injection)."""
from collections.abc import Callable

from fastapi import Depends

from app.application.job_imports import ImportJobsUseCase
from app.application.ports import AbstractUnitOfWork
from app.db.session import SessionLocal
from app.repositories import SqlAlchemyUnitOfWork

UnitOfWorkFactory = Callable[[], AbstractUnitOfWork]


def get_uow_factory() -> UnitOfWorkFactory:
    """Provide a factory; the application use case opens the transaction scope.

    FastAPI owns dependency construction, but the use case owns the exact
    commit/rollback boundary through ``with uow_factory() as uow``.
    """

    return lambda: SqlAlchemyUnitOfWork(SessionLocal)


def get_import_jobs_use_case(
    uow_factory: UnitOfWorkFactory = Depends(get_uow_factory),
) -> ImportJobsUseCase:
    """Assemble the HTTP adapter around the stable application use case."""

    return ImportJobsUseCase(uow_factory)
