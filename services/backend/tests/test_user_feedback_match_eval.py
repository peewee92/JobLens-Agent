"""Deterministic UserFeedback-derived Match Eval baseline tests."""
from datetime import UTC, datetime, timedelta

from app.application.eligibility import EligibilityDecision
from app.application.match_report import MatchRecommendation, MatchReport, StoredMatchReport
from app.application.user_feedback_eval import build_user_feedback_match_eval
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
