"""HTTP contract for immutable UserFeedback collection."""
from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from app.api.v1.schemas.common import CamelCaseModel
from app.application.user_feedback import CreateUserFeedbackResult
from app.domain.user_feedback import FeedbackDecision, FeedbackReason, UserFeedbackDraft


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
