"""Application-owned ports implemented by infrastructure adapters."""

from app.application.ports.career_context_repository import (
    AbstractCareerContextQueryRepository,
    AbstractCareerContextRepository,
)
from app.application.ports.career_context_unit_of_work import (
    AbstractCareerContextUnitOfWork,
)
from app.application.ports.job_import_query_repository import (
    AbstractJobImportQueryRepository,
)
from app.application.ports.profile_extractor import AbstractProfileExtractor
from app.application.ports.trace_repository import AbstractTraceRepository
from app.application.ports.trace_unit_of_work import AbstractTraceUnitOfWork
from app.application.ports.job_query_repository import AbstractJobQueryRepository
from app.application.ports.job_repository import (
    AbstractJobRepository,
    JobImportCandidateWrite,
    JobImportItemWrite,
    JobImportWrite,
    JobSourceRef,
    RepositoryRecordNotFound,
)
from app.application.ports.unit_of_work import AbstractUnitOfWork

__all__ = [
    "AbstractCareerContextQueryRepository",
    "AbstractCareerContextRepository",
    "AbstractCareerContextUnitOfWork",
    "AbstractJobImportQueryRepository",
    "AbstractJobQueryRepository",
    "AbstractJobRepository",
    "AbstractProfileExtractor",
    "AbstractTraceRepository",
    "AbstractTraceUnitOfWork",
    "AbstractUnitOfWork",
    "JobImportCandidateWrite",
    "JobImportItemWrite",
    "JobImportWrite",
    "JobSourceRef",
    "RepositoryRecordNotFound",
]
