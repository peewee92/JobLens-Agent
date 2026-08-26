"""HTTP contract for immutable UserFeedback collection."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.api.v1.schemas.common import CamelCaseModel
from app.application.user_feedback import (
    CreateUserFeedbackResult,
    LatestUserFeedbackResult,
    ListUserFeedbackResult,
)
from app.application.user_feedback_eval import UserFeedbackMatchEvalQueryResult
from app.domain.user_feedback import (
    FeedbackDecision,
    FeedbackReason,
    StoredUserFeedback,
    UserFeedbackDraft,
)


class CreateUserFeedbackRequest(CamelCaseModel):
    match_report_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    decision: FeedbackDecision
    reasons: list[FeedbackReason] = Field(default_factory=list)
    note: str | None = None

    @model_validator(mode="after")
    def validate_domain_rules(self) -> "CreateUserFeedbackRequest":
        UserFeedbackDraft.create(
            match_report_id=self.match_report_id,
            job_id=self.job_id,
            decision=self.decision,
            reasons=tuple(self.reasons),
            note=self.note,
        )
        return self


class UserFeedbackRecordResponse(CamelCaseModel):
    feedback_id: str
    match_report_id: str
    job_id: str
    decision: str
    reasons: list[str]
    note: str | None
    created_at: datetime

    @classmethod
    def from_stored(cls, stored: StoredUserFeedback) -> "UserFeedbackRecordResponse":
        return cls(
            feedback_id=stored.id,
            match_report_id=stored.feedback.match_report_id,
            job_id=stored.feedback.job_id,
            decision=stored.feedback.decision.value,
            reasons=[reason.value for reason in stored.feedback.reasons],
            note=stored.feedback.note,
            created_at=stored.created_at,
        )


class LatestUserFeedbackResponse(CamelCaseModel):
    feedback: list[UserFeedbackRecordResponse]
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_result(cls, result: LatestUserFeedbackResult) -> "LatestUserFeedbackResponse":
        return cls(
            feedback=[UserFeedbackRecordResponse.from_stored(item) for item in result.latest_by_match_report],
            db_writes=result.db_writes,
            provider_calls=result.provider_calls,
            trace_runs_created=result.trace_runs_created,
        )


class UserFeedbackHistoryResponse(CamelCaseModel):
    feedback: list[UserFeedbackRecordResponse]
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_result(cls, result: ListUserFeedbackResult) -> "UserFeedbackHistoryResponse":
        return cls(
            feedback=[UserFeedbackRecordResponse.from_stored(item) for item in result.feedback],
            db_writes=result.db_writes,
            provider_calls=result.provider_calls,
            trace_runs_created=result.trace_runs_created,
        )


class UserFeedbackMatchEvalResponse(CamelCaseModel):
    total_feedback_records: int
    latest_feedback_count: int
    evaluated_match_reports: int
    missing_match_report_ids: list[str]
    decision_counts: dict[str, int]
    recommendation_decision_counts: dict[str, dict[str, int]]
    rejection_reason_counts: dict[str, int]
    quality_gate_applied: bool
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_result(
        cls,
        result: UserFeedbackMatchEvalQueryResult,
    ) -> "UserFeedbackMatchEvalResponse":
        observed = result.eval
        return cls(
            total_feedback_records=observed.total_feedback_records,
            latest_feedback_count=observed.latest_feedback_count,
            evaluated_match_reports=observed.evaluated_match_reports,
            missing_match_report_ids=list(observed.missing_match_report_ids),
            decision_counts=observed.decision_counts,
            recommendation_decision_counts=observed.recommendation_decision_counts,
            rejection_reason_counts=observed.rejection_reason_counts,
            quality_gate_applied=observed.quality_gate_applied,
            db_writes=result.db_writes,
            provider_calls=result.provider_calls,
            trace_runs_created=result.trace_runs_created,
        )


class UserFeedbackResponse(CamelCaseModel):
    feedback_id: str
    match_report_id: str
    job_id: str
    decision: str
    reasons: list[str]
    note: str | None
    created_at: datetime
    db_writes: int
    provider_calls: int
    trace_runs_created: int

    @classmethod
    def from_result(cls, result: CreateUserFeedbackResult) -> "UserFeedbackResponse":
        stored = result.feedback
        return cls(
            feedback_id=stored.id,
            match_report_id=stored.feedback.match_report_id,
            job_id=stored.feedback.job_id,
            decision=stored.feedback.decision.value,
            reasons=[reason.value for reason in stored.feedback.reasons],
            note=stored.feedback.note,
            created_at=stored.created_at,
            db_writes=result.db_writes,
            provider_calls=result.provider_calls,
            trace_runs_created=result.trace_runs_created,
        )
