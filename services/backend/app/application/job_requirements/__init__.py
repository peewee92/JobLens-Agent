"""Stable Job Requirement application models and errors."""
from app.application.job_requirements.errors import (
    InvalidRequirementExtractorOutputError,
    JobDescriptionNotExtractableError,
    JobRequirementExtractionExecutionError,
    JobRequirementExtractionNotFoundError,
    RequirementExtractorFailedError,
    RequirementExtractorUnavailableError,
)
from app.application.job_requirements.models import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
    JobRequirementExtractionOutput,
    JobRequirementExtractionProposal,
    JobRequirementExtractionWrite,
    JobRequirementExtractorResult,
    JobRequirementWrite,
    ProposedJobRequirement,
)

__all__ = [
    "InvalidRequirementExtractorOutputError",
    "JobDescriptionNotExtractableError",
    "JobRequirementDetail",
    "JobRequirementExtractionDetail",
    "JobRequirementExtractionExecutionError",
    "JobRequirementExtractionNotFoundError",
    "JobRequirementExtractionOutput",
    "JobRequirementExtractionProposal",
    "JobRequirementExtractionWrite",
    "JobRequirementExtractorResult",
    "JobRequirementWrite",
    "ProposedJobRequirement",
    "RequirementExtractorFailedError",
    "RequirementExtractorUnavailableError",
]
