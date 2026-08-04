"""HTTP schemas for controlled Requirement acceptance execution runs."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from app.api.v1.schemas.common import CamelCaseModel
from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessBlockerScope,
    RequirementAcceptanceReadinessNextAction,
)
from app.application.requirement_acceptance.readiness_dashboard import (
    RequirementAcceptanceDatasetState,
    RequirementAcceptanceReadinessDashboard,
)
from app.application.requirement_acceptance.runs import (
    RequirementAcceptanceCanaryDecision,
    RequirementAcceptanceCanaryReviewDetail,
    RequirementAcceptanceRunCaseDetail,
    RequirementAcceptanceRunCaseStatus,
    RequirementAcceptanceRunDetail,
    RequirementAcceptanceRunPage,
    RequirementAcceptanceRunStatus,
    RequirementAcceptanceRunSummary,
)


class RequirementAcceptanceReadinessBlockerResponse(CamelCaseModel):
    scope: RequirementAcceptanceReadinessBlockerScope
    code: str
    message: str


class RequirementAcceptanceReadinessResponse(CamelCaseModel):
    dataset_state: RequirementAcceptanceDatasetState
    dataset_candidate_count: int
    dataset_file_name: str | None
    dataset_fingerprint: str | None
    source_version: str | None
    selected_count: int
    provider: str
    model: str
    api_key_configured: bool
    reviewer: str
    title: str
    requested_max_new_extractions: int | None
    database_reachable: bool
    database_revision: str | None
    migration_head: str
    workflow_ready: bool
    provider_execution_allowed: bool
    ready_for_next_action: bool
    next_action: RequirementAcceptanceReadinessNextAction
    run_id: str | None
    run_status: str | None
    attempted_calls: int
    canary_decision: RequirementAcceptanceCanaryDecision | None
    batch_id: str | None
    workbench_url: str | None
    manual_review_url: str | None
    blockers: list[RequirementAcceptanceReadinessBlockerResponse]
    db_writes: int = 0
    provider_calls: int = 0

    @classmethod
    def from_dashboard(
        cls,
        dashboard: RequirementAcceptanceReadinessDashboard,
    ) -> "RequirementAcceptanceReadinessResponse":
        readiness = dashboard.readiness
        return cls(
            dataset_state=dashboard.dataset_state,
            dataset_candidate_count=dashboard.dataset_candidate_count,
            dataset_file_name=dashboard.dataset_file_name,
            dataset_fingerprint=readiness.dataset_fingerprint,
            source_version=readiness.source_version,
            selected_count=readiness.selected_count,
            provider=readiness.provider,
            model=readiness.model,
            api_key_configured=readiness.api_key_configured,
            reviewer=readiness.reviewer,
            title=readiness.title,
            requested_max_new_extractions=(
                readiness.requested_max_new_extractions
            ),
            database_reachable=readiness.database_reachable,
            database_revision=readiness.database_revision,
            migration_head=readiness.migration_head,
            workflow_ready=readiness.workflow_ready,
            provider_execution_allowed=readiness.provider_execution_allowed,
            ready_for_next_action=readiness.ready_for_next_action,
            next_action=readiness.next_action,
            run_id=readiness.run_id,
            run_status=readiness.run_status,
            attempted_calls=readiness.attempted_calls,
            canary_decision=readiness.canary_decision,
            batch_id=readiness.batch_id,
            workbench_url=readiness.workbench_url,
            manual_review_url=readiness.manual_review_url,
            blockers=[
                RequirementAcceptanceReadinessBlockerResponse(
                    scope=item.scope,
                    code=item.code,
                    message=item.message,
                )
                for item in readiness.blockers
            ],
        )


class RequirementAcceptanceCanaryReviewRequest(CamelCaseModel):
    reviewer: str
    decision: RequirementAcceptanceCanaryDecision
    notes: str


class RequirementAcceptanceCanaryReviewResponse(CamelCaseModel):
    id: str
    run_id: str
    reviewer: str
    decision: RequirementAcceptanceCanaryDecision
    notes: str
    reviewed_case_ids: list[str]
    reviewed_extraction_ids: list[str]
    reviewed_trace_run_ids: list[str]
    reviewed_at: datetime

    @classmethod
    def from_detail(
        cls,
        detail: RequirementAcceptanceCanaryReviewDetail,
    ) -> "RequirementAcceptanceCanaryReviewResponse":
        return cls(
            id=detail.id,
            run_id=detail.run_id,
            reviewer=detail.reviewer,
            decision=detail.decision,
            notes=detail.notes,
            reviewed_case_ids=list(detail.reviewed_case_ids),
            reviewed_extraction_ids=list(detail.reviewed_extraction_ids),
            reviewed_trace_run_ids=list(detail.reviewed_trace_run_ids),
            reviewed_at=detail.reviewed_at,
        )


class RequirementAcceptanceRunCaseResponse(CamelCaseModel):
    id: str
    case_index: int
    source_url: str
    title: str
    company: str
    description_hash: str
    description_snapshot: str | None
    current_description_hash: str
    description_is_current: bool
    is_canary_evidence: bool
    job_id: str
    status: RequirementAcceptanceRunCaseStatus
    attempt_count: int
    extraction_id: str | None
    trace_run_id: str | None
    trace_capability: str | None
    trace_model: str | None
    trace_prompt_version: str | None
    trace_latency_ms: int | None
    trace_input_tokens: int | None
    trace_output_tokens: int | None
    trace_error: str | None
    trace_created_at: datetime | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_detail(
        cls,
        detail: RequirementAcceptanceRunCaseDetail,
        *,
        is_canary_evidence: bool,
    ) -> "RequirementAcceptanceRunCaseResponse":
        payload = asdict(detail)
        payload["description_snapshot"] = (
            detail.description_snapshot if is_canary_evidence else None
        )
        return cls(
            **payload,
            is_canary_evidence=is_canary_evidence,
        )


class RequirementAcceptanceRunDetailResponse(CamelCaseModel):
    id: str
    dataset_fingerprint: str
    source_version: str
    dataset_generated_at: str | None
    title: str
    reviewer: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    first_import_id: str
    last_import_id: str
    batch_id: str | None
    status: RequirementAcceptanceRunStatus
    canary_review_required: bool
    canary_continue_allowed: bool
    canary_stop_allowed: bool
    canary_review_block_reason: str | None
    canary_review: RequirementAcceptanceCanaryReviewResponse | None
    pending_count: int
    reused_count: int
    extracted_count: int
    failed_count: int
    deferred_count: int
    attempted_calls: int
    completed_case_count: int
    created_at: datetime
    updated_at: datetime
    cases: list[RequirementAcceptanceRunCaseResponse]

    @classmethod
    def from_detail(
        cls,
        detail: RequirementAcceptanceRunDetail,
    ) -> "RequirementAcceptanceRunDetailResponse":
        canary_case_ids = (
            set(detail.canary_review.reviewed_case_ids)
            if detail.canary_review is not None
            else {case.id for case in detail.cases if case.was_attempted}
        )
        return cls(
            id=detail.id,
            dataset_fingerprint=detail.dataset_fingerprint,
            source_version=detail.source_version,
            dataset_generated_at=detail.dataset_generated_at,
            title=detail.title,
            reviewer=detail.reviewer,
            provider=detail.provider,
            model=detail.model,
            extractor_version=detail.extractor_version,
            prompt_version=detail.prompt_version,
            first_import_id=detail.first_import_id,
            last_import_id=detail.last_import_id,
            batch_id=detail.batch_id,
            status=detail.status,
            canary_review_required=detail.canary_review_required,
            canary_continue_allowed=detail.canary_continue_allowed,
            canary_stop_allowed=detail.canary_stop_allowed,
            canary_review_block_reason=detail.canary_review_block_reason,
            canary_review=(
                RequirementAcceptanceCanaryReviewResponse.from_detail(
                    detail.canary_review
                )
                if detail.canary_review is not None
                else None
            ),
            pending_count=detail.pending_count,
            reused_count=detail.reused_count,
            extracted_count=detail.extracted_count,
            failed_count=detail.failed_count,
            deferred_count=detail.deferred_count,
            attempted_calls=detail.attempted_calls,
            completed_case_count=detail.completed_case_count,
            created_at=detail.created_at,
            updated_at=detail.updated_at,
            cases=[
                RequirementAcceptanceRunCaseResponse.from_detail(
                    item,
                    is_canary_evidence=item.id in canary_case_ids,
                )
                for item in detail.cases
            ],
        )


class RequirementAcceptanceRunSummaryResponse(CamelCaseModel):
    id: str
    title: str
    reviewer: str
    provider: str
    model: str
    extractor_version: str
    prompt_version: str
    status: RequirementAcceptanceRunStatus
    attempted_calls: int
    completed_case_count: int
    failed_count: int
    deferred_count: int
    canary_review_required: bool
    canary_decision: RequirementAcceptanceCanaryDecision | None
    batch_id: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_summary(
        cls,
        summary: RequirementAcceptanceRunSummary,
    ) -> "RequirementAcceptanceRunSummaryResponse":
        return cls(**asdict(summary))


class RequirementAcceptanceRunPageResponse(CamelCaseModel):
    total: int
    limit: int
    offset: int
    items: list[RequirementAcceptanceRunSummaryResponse]

    @classmethod
    def from_page(
        cls,
        page: RequirementAcceptanceRunPage,
    ) -> "RequirementAcceptanceRunPageResponse":
        return cls(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            items=[
                RequirementAcceptanceRunSummaryResponse.from_summary(item)
                for item in page.items
            ],
        )
