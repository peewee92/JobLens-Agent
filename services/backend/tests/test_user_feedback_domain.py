"""Deterministic UserFeedback domain contract tests."""

import pytest

from app.domain.user_feedback import (
    FeedbackDecision,
    FeedbackReason,
    UserFeedbackDraft,
)


def test_feedback_draft_preserves_match_report_provenance_and_deduplicates_reasons() -> None:
    draft = UserFeedbackDraft.create(
        match_report_id="match_123",
        job_id="job_123",
        decision=FeedbackDecision.MAYBE,
        reasons=(FeedbackReason.SKILL_GAP, FeedbackReason.LOCATION, FeedbackReason.SKILL_GAP),
        note="  Need stronger backend evidence first.  ",
    )

    assert draft.match_report_id == "match_123"
    assert draft.job_id == "job_123"
    assert draft.decision is FeedbackDecision.MAYBE
    assert draft.reasons == (FeedbackReason.SKILL_GAP, FeedbackReason.LOCATION)
    assert draft.note == "Need stronger backend evidence first."


def test_rejected_feedback_requires_at_least_one_structured_reason() -> None:
    with pytest.raises(ValueError, match="rejected feedback requires at least one reason"):
        UserFeedbackDraft.create(
            match_report_id="match_123",
            job_id="job_123",
            decision=FeedbackDecision.REJECTED,
        )


def test_interested_feedback_can_be_recorded_without_a_reason() -> None:
    draft = UserFeedbackDraft.create(
        match_report_id="match_123",
        job_id="job_123",
        decision=FeedbackDecision.INTERESTED,
    )

    assert draft.reasons == ()
    assert draft.note is None


@pytest.mark.parametrize("field,value", [("match_report_id", " "), ("job_id", "")])
def test_feedback_requires_snapshot_and_job_identity(field: str, value: str) -> None:
    kwargs = {
        "match_report_id": "match_123",
        "job_id": "job_123",
        "decision": FeedbackDecision.INTERESTED,
    }
    kwargs[field] = value

    with pytest.raises(ValueError, match=field):
        UserFeedbackDraft.create(**kwargs)


def test_other_reason_requires_a_note() -> None:
    with pytest.raises(ValueError, match="other reason requires a note"):
        UserFeedbackDraft.create(
            match_report_id="match_123",
            job_id="job_123",
            decision=FeedbackDecision.MAYBE,
            reasons=(FeedbackReason.OTHER,),
        )
