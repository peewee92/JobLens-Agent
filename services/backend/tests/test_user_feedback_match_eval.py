"""Deterministic UserFeedback-derived Match Eval baseline tests."""
from datetime import UTC, datetime, timedelta

import pytest

from app.application.eligibility import EligibilityDecision
from app.application.match_report import MatchRecommendation, MatchReport, StoredMatchReport
from app.application.user_feedback_eval import (
    UserFeedbackMatchEvalQueryUseCase,
    build_user_feedback_match_eval,
)
from app.application.user_feedback import UserFeedbackPersistenceNotReadyError
from app.application.user_feedback_persistence import UserFeedbackPersistenceReadiness
from app.domain.user_feedback import FeedbackDecision, FeedbackReason, StoredUserFeedback, UserFeedbackDraft


NOW = datetime(2026, 8, 10, tzinfo=UTC)


def _report(report_id: str, recommendation: MatchRecommendation) -> StoredMatchReport:
    return StoredMatchReport(
        id=report_id,
        report=MatchReport(
            job_id=f"job_{report_id}",
            profile_id="profile_1",
            profile_version=1,
            extraction_id=f"reqrun_{report_id}",
            eligibility=(
                EligibilityDecision.BLOCKED
                if recommendation is MatchRecommendation.BLOCKED
                else EligibilityDecision.ELIGIBLE
            ),
            recommendation=recommendation,
            summary="Synthetic eval fixture.",
            strengths=(),
            risks=(),
            requirement_results=(),
            matched_requirement_ids=(),
            partial_requirement_ids=(),
            missing_requirement_ids=(),
            evidence_links=(),
            matcher_version="semantic-match-v1",
            prompt_version="semantic-match-v3",
            model="fixture",
            trace_run_id=None,
        ),
        created_at=NOW,
    )


def _feedback(
    feedback_id: str,
    report_id: str,
    decision: FeedbackDecision,
    *,
    reasons: tuple[FeedbackReason, ...] = (),
    created_at: datetime = NOW,
) -> StoredUserFeedback:
    return StoredUserFeedback(
        id=feedback_id,
        feedback=UserFeedbackDraft.create(
            match_report_id=report_id,
            job_id=f"job_{report_id}",
            decision=decision,
            reasons=reasons,
        ),
        created_at=created_at,
    )


def test_feedback_eval_uses_latest_feedback_per_match_report_and_reports_distribution() -> None:
    reports = (
        _report("strong", MatchRecommendation.STRONG),
        _report("good", MatchRecommendation.GOOD),
        _report("low", MatchRecommendation.LOW),
    )
    feedback = (
        _feedback("f1", "strong", FeedbackDecision.MAYBE, created_at=NOW),
        _feedback("f2", "strong", FeedbackDecision.INTERESTED, created_at=NOW + timedelta(minutes=1)),
        _feedback("f3", "good", FeedbackDecision.INTERESTED),
        _feedback(
            "f4",
            "low",
            FeedbackDecision.REJECTED,
            reasons=(FeedbackReason.SKILL_GAP, FeedbackReason.COMPENSATION),
        ),
    )

    result = build_user_feedback_match_eval(feedback=feedback, reports=reports)

    assert result.total_feedback_records == 4
    assert result.latest_feedback_count == 3
    assert result.evaluated_match_reports == 3
    assert result.missing_match_report_ids == ()
    assert result.decision_counts == {"interested": 2, "maybe": 0, "rejected": 1}
    assert result.recommendation_decision_counts["strong"] == {
        "interested": 1,
        "maybe": 0,
        "rejected": 0,
    }
    assert result.recommendation_decision_counts["low"]["rejected"] == 1
    assert result.rejection_reason_counts == {"skill_gap": 1, "compensation": 1}
    assert result.quality_gate_applied is False


class _FeedbackQueries:
    def __init__(self, items: tuple[StoredUserFeedback, ...]) -> None:
        self.items = items
        self.job_calls: list[str] = []

    def get(self, feedback_id: str):
        return None

    def list_for_match_report(self, match_report_id: str):
        return ()

    def list_for_job(self, job_id: str):
        self.job_calls.append(job_id)
        return self.items


class _ReportQueries:
    def __init__(self, items: tuple[StoredMatchReport, ...]) -> None:
        self.items = items
        self.job_calls: list[str] = []

    def get(self, report_id: str):
        return None

    def list_for_job(self, job_id: str):
        self.job_calls.append(job_id)
        return self.items

    def list_latest_for_jobs(self, job_ids: tuple[str, ...]):
        return ()


def _ready() -> UserFeedbackPersistenceReadiness:
    return UserFeedbackPersistenceReadiness(ready=True, blocker_codes=())


def test_feedback_eval_query_use_case_reads_one_job_without_side_effects() -> None:
    report = _report("good", MatchRecommendation.GOOD)
    feedback = _feedback("f1", "good", FeedbackDecision.INTERESTED)
    feedback_queries = _FeedbackQueries((feedback,))
    report_queries = _ReportQueries((report,))

    result = UserFeedbackMatchEvalQueryUseCase(
        feedback_repository=feedback_queries,
        report_repository=report_queries,
        persistence_readiness=_ready,
    ).execute(job_id=" job_good ")

    assert result.eval.evaluated_match_reports == 1
    assert result.eval.decision_counts["interested"] == 1
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0
    assert feedback_queries.job_calls == ["job_good"]
    assert report_queries.job_calls == ["job_good"]


def test_feedback_eval_query_use_case_fails_closed_before_reads_when_schema_missing() -> None:
    feedback_queries = _FeedbackQueries(())
    report_queries = _ReportQueries(())

    with pytest.raises(UserFeedbackPersistenceNotReadyError):
        UserFeedbackMatchEvalQueryUseCase(
            feedback_repository=feedback_queries,
            report_repository=report_queries,
            persistence_readiness=lambda: UserFeedbackPersistenceReadiness(
                ready=False,
                blocker_codes=("user_feedback_persistence_not_ready",),
            ),
        ).execute(job_id="job_1")

    assert feedback_queries.job_calls == []
    assert report_queries.job_calls == []


def test_feedback_eval_does_not_invent_ground_truth_for_missing_match_reports() -> None:
    feedback = (
        _feedback("f1", "missing", FeedbackDecision.INTERESTED),
        _feedback("f2", "known", FeedbackDecision.MAYBE),
    )

    result = build_user_feedback_match_eval(
        feedback=feedback,
        reports=(_report("known", MatchRecommendation.GOOD),),
    )

    assert result.latest_feedback_count == 2
    assert result.evaluated_match_reports == 1
    assert result.missing_match_report_ids == ("missing",)
    assert result.decision_counts == {"interested": 0, "maybe": 1, "rejected": 0}
    assert result.quality_gate_applied is False
