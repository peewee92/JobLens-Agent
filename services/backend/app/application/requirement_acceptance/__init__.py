"""Real Requirement acceptance preparation with lazy orchestration exports."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.application.requirement_acceptance.errors import (
    InvalidRequirementAcceptanceCanaryReviewError,
    InvalidRequirementAcceptanceDatasetError,
    RequirementAcceptanceCanaryGateError,
    RequirementAcceptanceCanaryReviewAlreadyExistsError,
    RequirementAcceptanceExecutionLeaseLostError,
    RequirementAcceptanceExecutionLeaseUnavailableError,
    RequirementAcceptanceImportError,
    RequirementAcceptanceRunNotFoundError,
)
from app.application.requirement_acceptance.models import (
    RequirementAcceptanceCaseResult,
    RequirementAcceptanceCaseStatus,
    RequirementAcceptancePreparationResult,
)

if TYPE_CHECKING:
    from app.application.requirement_acceptance.controlled_resume_operator import (
        RequirementAcceptanceResumeOperatorBlocker,
        RequirementAcceptanceResumeOperatorError,
        RequirementAcceptanceResumeOperatorPlan,
        RequirementAcceptanceResumeOperatorState,
        evaluate_requirement_acceptance_resume_operator,
    )
    from app.application.requirement_acceptance.database_checkpoint import (
        DATABASE_CHECKPOINT_SCHEMA_VERSION,
        database_checkpoint_receipt_path,
        load_database_checkpoint_receipt,
        mark_database_checkpoint_already_at_head,
        mark_database_checkpoint_applied,
        mark_database_checkpoint_backup_verified,
        mark_database_checkpoint_failed,
        mark_database_checkpoint_migration_attempted,
        new_database_checkpoint_receipt,
        requirement_acceptance_database_checkpoint_id,
        validate_database_checkpoint_identity,
        verify_database_checkpoint_backup,
    )
    from app.application.requirement_acceptance.live_canary_operator import (
        RequirementAcceptanceCanaryOperatorBlocker,
        RequirementAcceptanceCanaryOperatorError,
        RequirementAcceptanceCanaryOperatorPlan,
        RequirementAcceptanceCanaryOperatorState,
        evaluate_requirement_acceptance_canary_operator,
    )
    from app.application.requirement_acceptance.local_bootstrap import (
        RequirementAcceptanceBootstrapError,
        RequirementAcceptanceBootstrapPlan,
        RequirementAcceptanceDatabaseBackupResult,
        RequirementAcceptanceDatasetStageResult,
        backup_sqlite_database,
        build_requirement_acceptance_bootstrap_plan,
        file_sha256,
        planned_backup_path,
        private_dataset_path,
        sqlite_database_path,
        sqlite_integrity_check,
        sqlite_revision,
        stage_private_dataset,
    )
    from app.application.requirement_acceptance.session_manifest import (
        SESSION_MANIFEST_SCHEMA_VERSION,
        build_requirement_acceptance_session_manifest,
        requirement_acceptance_session_id,
        write_requirement_acceptance_session_manifest,
    )
    from app.application.requirement_acceptance.readiness import (
        RequirementAcceptanceReadinessBlocker,
        RequirementAcceptanceReadinessBlockerScope,
        RequirementAcceptanceReadinessNextAction,
        RequirementAcceptanceReadinessResult,
        evaluate_requirement_acceptance_readiness,
    )
    from app.application.requirement_acceptance.run_use_cases import (
        GetRequirementAcceptanceRunUseCase,
        ListRequirementAcceptanceRunsUseCase,
        ReviewRequirementAcceptanceCanaryUseCase,
    )
    from app.application.requirement_acceptance.runs import (
        RequirementAcceptanceCanaryDecision,
        RequirementAcceptanceCanaryReviewDetail,
        RequirementAcceptancePreflight,
        RequirementAcceptanceRunCaseDetail,
        RequirementAcceptanceRunCaseStatus,
        RequirementAcceptanceRunDetail,
        RequirementAcceptanceRunPage,
        RequirementAcceptanceRunStatus,
        RequirementAcceptanceRunSummary,
    )
    from app.application.requirement_acceptance.use_case import (
        FORMAL_SAMPLE_SIZE,
        PrepareRequirementAcceptanceBatchUseCase,
        preflight_requirement_acceptance_dataset,
    )

_CONTROLLED_RESUME_OPERATOR_EXPORTS = {
    "RequirementAcceptanceResumeOperatorBlocker",
    "RequirementAcceptanceResumeOperatorError",
    "RequirementAcceptanceResumeOperatorPlan",
    "RequirementAcceptanceResumeOperatorState",
    "evaluate_requirement_acceptance_resume_operator",
}
_DATABASE_CHECKPOINT_EXPORTS = {
    "DATABASE_CHECKPOINT_SCHEMA_VERSION",
    "database_checkpoint_receipt_path",
    "load_database_checkpoint_receipt",
    "mark_database_checkpoint_already_at_head",
    "mark_database_checkpoint_applied",
    "mark_database_checkpoint_backup_verified",
    "mark_database_checkpoint_failed",
    "mark_database_checkpoint_migration_attempted",
    "new_database_checkpoint_receipt",
    "requirement_acceptance_database_checkpoint_id",
    "validate_database_checkpoint_identity",
    "verify_database_checkpoint_backup",
}
_LIVE_CANARY_OPERATOR_EXPORTS = {
    "RequirementAcceptanceCanaryOperatorBlocker",
    "RequirementAcceptanceCanaryOperatorError",
    "RequirementAcceptanceCanaryOperatorPlan",
    "RequirementAcceptanceCanaryOperatorState",
    "evaluate_requirement_acceptance_canary_operator",
}
_LOCAL_BOOTSTRAP_EXPORTS = {
    "RequirementAcceptanceBootstrapError",
    "RequirementAcceptanceBootstrapPlan",
    "RequirementAcceptanceDatabaseBackupResult",
    "RequirementAcceptanceDatasetStageResult",
    "backup_sqlite_database",
    "build_requirement_acceptance_bootstrap_plan",
    "file_sha256",
    "planned_backup_path",
    "private_dataset_path",
    "sqlite_database_path",
    "sqlite_integrity_check",
    "sqlite_revision",
    "stage_private_dataset",
}
_SESSION_MANIFEST_EXPORTS = {
    "SESSION_MANIFEST_SCHEMA_VERSION",
    "build_requirement_acceptance_session_manifest",
    "requirement_acceptance_session_id",
    "write_requirement_acceptance_session_manifest",
}
_READINESS_EXPORTS = {
    "RequirementAcceptanceReadinessBlocker",
    "RequirementAcceptanceReadinessBlockerScope",
    "RequirementAcceptanceReadinessNextAction",
    "RequirementAcceptanceReadinessResult",
    "evaluate_requirement_acceptance_readiness",
}
_RUN_USE_CASE_EXPORTS = {
    "GetRequirementAcceptanceRunUseCase",
    "ListRequirementAcceptanceRunsUseCase",
    "ReviewRequirementAcceptanceCanaryUseCase",
}
_RUN_EXPORTS = {
    "RequirementAcceptanceCanaryDecision",
    "RequirementAcceptanceCanaryReviewDetail",
    "RequirementAcceptancePreflight",
    "RequirementAcceptanceRunCaseDetail",
    "RequirementAcceptanceRunCaseStatus",
    "RequirementAcceptanceRunDetail",
    "RequirementAcceptanceRunPage",
    "RequirementAcceptanceRunStatus",
    "RequirementAcceptanceRunSummary",
}
_USE_CASE_EXPORTS = {
    "FORMAL_SAMPLE_SIZE",
    "PrepareRequirementAcceptanceBatchUseCase",
    "preflight_requirement_acceptance_dataset",
}


def __getattr__(name: str) -> Any:
    if name in _CONTROLLED_RESUME_OPERATOR_EXPORTS:
        from app.application.requirement_acceptance import controlled_resume_operator

        return getattr(controlled_resume_operator, name)
    if name in _LIVE_CANARY_OPERATOR_EXPORTS:
        from app.application.requirement_acceptance import live_canary_operator

        return getattr(live_canary_operator, name)
    if name in _DATABASE_CHECKPOINT_EXPORTS:
        from app.application.requirement_acceptance import database_checkpoint

        return getattr(database_checkpoint, name)
    if name in _LOCAL_BOOTSTRAP_EXPORTS:
        from app.application.requirement_acceptance import local_bootstrap

        return getattr(local_bootstrap, name)
    if name in _SESSION_MANIFEST_EXPORTS:
        from app.application.requirement_acceptance import session_manifest

        return getattr(session_manifest, name)
    if name in _READINESS_EXPORTS:
        from app.application.requirement_acceptance import readiness

        return getattr(readiness, name)
    if name in _RUN_USE_CASE_EXPORTS:
        from app.application.requirement_acceptance import run_use_cases

        return getattr(run_use_cases, name)
    if name in _RUN_EXPORTS:
        from app.application.requirement_acceptance import runs

        return getattr(runs, name)
    if name in _USE_CASE_EXPORTS:
        from app.application.requirement_acceptance import use_case

        return getattr(use_case, name)
    raise AttributeError(name)


__all__ = [
    "DATABASE_CHECKPOINT_SCHEMA_VERSION",
    "FORMAL_SAMPLE_SIZE",
    "GetRequirementAcceptanceRunUseCase",
    "InvalidRequirementAcceptanceCanaryReviewError",
    "InvalidRequirementAcceptanceDatasetError",
    "ListRequirementAcceptanceRunsUseCase",
    "PrepareRequirementAcceptanceBatchUseCase",
    "RequirementAcceptanceBootstrapError",
    "RequirementAcceptanceBootstrapPlan",
    "RequirementAcceptanceCanaryOperatorBlocker",
    "RequirementAcceptanceCanaryOperatorError",
    "RequirementAcceptanceCanaryOperatorPlan",
    "RequirementAcceptanceCanaryOperatorState",
    "RequirementAcceptanceCaseResult",
    "RequirementAcceptanceDatabaseBackupResult",
    "RequirementAcceptanceDatasetStageResult",
    "RequirementAcceptanceCanaryDecision",
    "RequirementAcceptanceCanaryGateError",
    "RequirementAcceptanceCanaryReviewAlreadyExistsError",
    "RequirementAcceptanceCanaryReviewDetail",
    "RequirementAcceptanceCaseStatus",
    "RequirementAcceptanceExecutionLeaseLostError",
    "RequirementAcceptanceExecutionLeaseUnavailableError",
    "RequirementAcceptanceImportError",
    "RequirementAcceptancePreflight",
    "RequirementAcceptanceReadinessBlocker",
    "RequirementAcceptanceReadinessBlockerScope",
    "RequirementAcceptanceReadinessNextAction",
    "RequirementAcceptanceReadinessResult",
    "RequirementAcceptanceResumeOperatorBlocker",
    "RequirementAcceptanceResumeOperatorError",
    "RequirementAcceptanceResumeOperatorPlan",
    "RequirementAcceptanceResumeOperatorState",
    "RequirementAcceptancePreparationResult",
    "RequirementAcceptanceRunCaseDetail",
    "RequirementAcceptanceRunCaseStatus",
    "RequirementAcceptanceRunDetail",
    "RequirementAcceptanceRunNotFoundError",
    "RequirementAcceptanceRunPage",
    "RequirementAcceptanceRunStatus",
    "RequirementAcceptanceRunSummary",
    "ReviewRequirementAcceptanceCanaryUseCase",
    "SESSION_MANIFEST_SCHEMA_VERSION",
    "backup_sqlite_database",
    "database_checkpoint_receipt_path",
    "build_requirement_acceptance_bootstrap_plan",
    "build_requirement_acceptance_session_manifest",
    "evaluate_requirement_acceptance_canary_operator",
    "evaluate_requirement_acceptance_readiness",
    "evaluate_requirement_acceptance_resume_operator",
    "file_sha256",
    "load_database_checkpoint_receipt",
    "mark_database_checkpoint_already_at_head",
    "mark_database_checkpoint_applied",
    "mark_database_checkpoint_backup_verified",
    "mark_database_checkpoint_failed",
    "mark_database_checkpoint_migration_attempted",
    "new_database_checkpoint_receipt",
    "planned_backup_path",
    "preflight_requirement_acceptance_dataset",
    "private_dataset_path",
    "requirement_acceptance_database_checkpoint_id",
    "requirement_acceptance_session_id",
    "sqlite_database_path",
    "sqlite_integrity_check",
    "sqlite_revision",
    "stage_private_dataset",
    "validate_database_checkpoint_identity",
    "verify_database_checkpoint_backup",
    "write_requirement_acceptance_session_manifest",
]
