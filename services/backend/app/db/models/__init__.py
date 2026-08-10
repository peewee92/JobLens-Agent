"""Import all ORM models so SQLAlchemy and Alembic can register metadata.

Alembic autogenerate only sees tables that have been imported onto Base.metadata.
Adding a model file without importing it here makes migrations silently miss it.
"""
from app.db.models.career_context import (
    ProfileEvidenceORM,
    ProfileSkillEvidenceORM,
    ProfileSkillORM,
    SearchIntentORM,
    UserProfileORM,
)
from app.db.models.job import JobORM
from app.db.models.job_import import JobImportORM
from app.db.models.job_import_candidate import JobImportCandidateORM
from app.db.models.job_import_item import JobImportItemORM
from app.db.models.job_requirement import (
    JobRequirementExtractionORM,
    JobRequirementORM,
)
from app.db.models.job_source import JobSourceORM
from app.db.models.match_report import MatchReportORM
from app.db.models.profile_eval import (
    ProfileEvalCaseResultORM,
    ProfileEvalReviewORM,
    ProfileEvalRunORM,
)
from app.db.models.requirement_acceptance_execution_lease import (
    RequirementAcceptanceExecutionLeaseORM,
)
from app.db.models.requirement_acceptance_run import (
    RequirementAcceptanceCanaryReviewORM,
    RequirementAcceptanceRunCaseORM,
    RequirementAcceptanceRunORM,
)
from app.db.models.requirement_eval import (
    RequirementEvalCaseResultORM,
    RequirementEvalReviewORM,
    RequirementEvalRunORM,
)
from app.db.models.requirement_review import (
    RequirementReviewBatchCaseORM,
    RequirementReviewBatchFinalDecisionORM,
    RequirementReviewBatchORM,
    RequirementReviewCaseReviewORM,
)
from app.db.models.trace_span import TraceSpanORM
from app.db.models.user_feedback import UserFeedbackORM

__all__ = [
    "JobORM",
    "ProfileEvidenceORM",
    "ProfileSkillEvidenceORM",
    "ProfileSkillORM",
    "SearchIntentORM",
    "UserProfileORM",
    "JobImportORM",
    "JobImportCandidateORM",
    "JobImportItemORM",
    "JobRequirementExtractionORM",
    "JobRequirementORM",
    "JobSourceORM",
    "MatchReportORM",
    "ProfileEvalCaseResultORM",
    "ProfileEvalReviewORM",
    "ProfileEvalRunORM",
    "RequirementAcceptanceCanaryReviewORM",
    "RequirementAcceptanceExecutionLeaseORM",
    "RequirementAcceptanceRunCaseORM",
    "RequirementAcceptanceRunORM",
    "RequirementEvalCaseResultORM",
    "RequirementEvalReviewORM",
    "RequirementEvalRunORM",
    "RequirementReviewBatchCaseORM",
    "RequirementReviewBatchFinalDecisionORM",
    "RequirementReviewBatchORM",
    "RequirementReviewCaseReviewORM",
    "TraceSpanORM",
    "UserFeedbackORM",
]
