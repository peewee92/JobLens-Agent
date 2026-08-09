from __future__ import annotations

from pydantic import BaseModel

from app.application.match_review import MatchReviewReadiness


class MatchReviewReadinessBlockerResponse(BaseModel):
    code: str
    message: str


class MatchReviewReadinessResponse(BaseModel):
    requiredJobCount: int
    availableJobCount: int
    inputReadyJobCount: int
    persistenceReady: bool
    readyForHumanReview: bool
    reviewableJobIds: list[str]
    blockers: list[MatchReviewReadinessBlockerResponse]
    dbWrites: int
    providerCalls: int
    traceRunsCreated: int

    @classmethod
    def from_detail(cls, detail: MatchReviewReadiness) -> "MatchReviewReadinessResponse":
        return cls(
            requiredJobCount=detail.required_job_count,
            availableJobCount=detail.available_job_count,
            inputReadyJobCount=detail.input_ready_job_count,
            persistenceReady=detail.persistence_ready,
            readyForHumanReview=detail.ready_for_human_review,
            reviewableJobIds=list(detail.reviewable_job_ids),
            blockers=[
                MatchReviewReadinessBlockerResponse(code=item.code, message=item.message)
                for item in detail.blockers
            ],
            dbWrites=detail.db_writes,
            providerCalls=detail.provider_calls,
            traceRunsCreated=detail.trace_runs_created,
        )
