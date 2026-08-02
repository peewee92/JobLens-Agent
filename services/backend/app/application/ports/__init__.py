"""Application-owned ports implemented by infrastructure adapters."""

from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.application.ports.job_repository import (
    AbstractJobRepository,
    JobImportItemWrite,
    JobImportWrite,
    JobSourceRef,
    RepositoryRecordNotFound,
)
from app.application.ports.unit_of_work import AbstractUnitOfWork

__all__ = [
    "AbstractJobQueryRepository",
    "AbstractJobRepository",
    "AbstractUnitOfWork",
    "JobImportItemWrite",
    "JobImportWrite",
    "JobSourceRef",
    "RepositoryRecordNotFound",
]
