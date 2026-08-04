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
from app.application.ports.job_requirement_extractor import (
    AbstractJobRequirementExtractor,
)
from app.application.ports.job_requirement_release_repository import (
    AbstractJobRequirementReleaseQueryRepository,
    JobRequirementTraceFact,
)
from app.application.ports.job_requirement_repository import (
    AbstractJobRequirementQueryRepository,
    AbstractJobRequirementRepository,
)
from app.application.ports.job_requirement_unit_of_work import (
    AbstractJobRequirementUnitOfWork,
)
from app.application.ports.profile_eval_repository import (
    AbstractProfileEvalQueryRepository,
    AbstractProfileEvalRepository,
)
from app.application.ports.requirement_acceptance_run_repository import (
    AbstractRequirementAcceptanceRunQueryRepository,
    AbstractRequirementAcceptanceRunRepository,
)
from app.application.ports.requirement_acceptance_run_unit_of_work import (
    AbstractRequirementAcceptanceRunUnitOfWork,
)
from app.application.ports.requirement_eval_repository import (
    AbstractRequirementEvalQueryRepository,
    AbstractRequirementEvalRepository,
)
from app.application.ports.requirement_eval_review_repository import (
    AbstractRequirementEvalReviewRepository,
)
from app.application.ports.requirement_eval_review_unit_of_work import (
    AbstractRequirementEvalReviewUnitOfWork,
)
from app.application.ports.requirement_eval_unit_of_work import (
    AbstractRequirementEvalUnitOfWork,
)
from app.application.ports.requirement_review_repository import (
    AbstractRequirementReviewQueryRepository,
    AbstractRequirementReviewRepository,
)
from app.application.ports.requirement_review_unit_of_work import (
    AbstractRequirementReviewUnitOfWork,
)
from app.application.ports.profile_eval_review_repository import (
    AbstractProfileEvalReviewRepository,
)
from app.application.ports.profile_eval_review_unit_of_work import (
    AbstractProfileEvalReviewUnitOfWork,
)
from app.application.ports.profile_eval_unit_of_work import AbstractProfileEvalUnitOfWork
from app.application.ports.profile_extractor import AbstractProfileExtractor
from app.application.ports.resume_document_parser import AbstractResumeDocumentParser
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
    "AbstractJobRequirementExtractor",
    "AbstractJobRequirementQueryRepository",
    "AbstractJobRequirementReleaseQueryRepository",
    "AbstractJobRequirementRepository",
    "AbstractJobRequirementUnitOfWork",
    "AbstractJobRepository",
    "AbstractProfileEvalQueryRepository",
    "AbstractProfileEvalRepository",
    "AbstractProfileEvalReviewRepository",
    "AbstractProfileEvalReviewUnitOfWork",
    "AbstractProfileEvalUnitOfWork",
    "AbstractProfileExtractor",
    "AbstractRequirementAcceptanceRunQueryRepository",
    "AbstractRequirementAcceptanceRunRepository",
    "AbstractRequirementAcceptanceRunUnitOfWork",
    "AbstractRequirementEvalQueryRepository",
    "AbstractRequirementEvalRepository",
    "AbstractRequirementEvalReviewRepository",
    "AbstractRequirementEvalReviewUnitOfWork",
    "AbstractRequirementEvalUnitOfWork",
    "AbstractRequirementReviewQueryRepository",
    "AbstractRequirementReviewRepository",
    "AbstractRequirementReviewUnitOfWork",
    "AbstractResumeDocumentParser",
    "AbstractTraceRepository",
    "AbstractTraceUnitOfWork",
    "AbstractUnitOfWork",
    "JobImportCandidateWrite",
    "JobRequirementTraceFact",
    "JobImportItemWrite",
    "JobImportWrite",
    "JobSourceRef",
    "RepositoryRecordNotFound",
]
