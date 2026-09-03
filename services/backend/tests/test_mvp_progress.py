"""MVP progress summary tests."""
from __future__ import annotations

from dataclasses import replace

from app.evals.mvp_progress import RealMvpLoopProgress, build_mvp_progress_summary
from app.evals.mvp_quality import MvpQualityStatus


def _status() -> MvpQualityStatus:
    return MvpQualityStatus(
        gate_passed=True,
        replay_passed=True,
        replay_passed_cases=10,
        replay_total_cases=10,
        match_demo_passed=True,
        match_demo_persisted_reports=20,
        match_demo_top_jobs=5,
        match_demo_evidence_complete=True,
        provider_smoke_state="never_run",
        provider_smoke_ready=None,
        provider_smoke_blocking=False,
        provider_smoke_blocker=None,
        provider_smoke_checked_at=None,
        provider_smoke_plain_status_code=None,
        provider_smoke_structured_status_code=None,
        provider_calls=0,
    )


def test_mvp_progress_counts_only_demonstrable_offline_slice() -> None:
    summary = build_mvp_progress_summary(_status())

    assert summary.mvp_gate_passed is True
    assert summary.offline_e2e_slices_completed == 1
    assert summary.offline_e2e_slices_total == 1
    assert summary.top_n_available is True
    assert summary.top_n_jobs == 5
    assert summary.top_n_evidence_complete is True
    assert summary.extraction_frozen is True
    assert summary.provider_smoke_blocking is False
    assert summary.real_loop_data_available is False
    assert summary.real_total_jobs is None
    assert summary.real_current_match_reports is None
    assert summary.real_feedback_covered_reports is None
    assert summary.next_priority == "collect_real_match_reports_and_feedback"


def test_mvp_progress_does_not_count_broken_top_n_as_completed_slice() -> None:
    summary = build_mvp_progress_summary(
        replace(
            _status(),
            gate_passed=False,
            match_demo_passed=False,
            match_demo_top_jobs=4,
            match_demo_evidence_complete=False,
        )
    )

    assert summary.mvp_gate_passed is False
    assert summary.offline_e2e_slices_completed == 0
    assert summary.top_n_available is False
    assert summary.next_priority == "restore_offline_mvp_gate"


def test_mvp_progress_includes_real_value_loop_coverage_without_changing_offline_gate() -> None:
    summary = build_mvp_progress_summary(
        _status(),
        real_loop=RealMvpLoopProgress(
            total_jobs=20,
            current_match_reports=4,
            feedback_covered_reports=1,
            requirement_analysis_needed=16,
            match_ready_without_report=0,
        ),
    )

    assert summary.mvp_gate_passed is True
    assert summary.real_loop_data_available is True
    assert summary.real_total_jobs == 20
    assert summary.real_current_match_reports == 4
    assert summary.real_feedback_covered_reports == 1
    assert summary.real_requirement_analysis_needed == 16
    assert summary.real_match_ready_without_report == 0
    assert summary.real_match_report_coverage == 0.2
    assert summary.real_feedback_coverage == 0.25
    assert summary.next_priority == "complete_current_user_feedback"


def test_mvp_progress_expands_match_coverage_after_current_feedback_is_complete() -> None:
    summary = build_mvp_progress_summary(
        _status(),
        real_loop=RealMvpLoopProgress(
            total_jobs=20,
            current_match_reports=4,
            feedback_covered_reports=4,
            requirement_analysis_needed=16,
            match_ready_without_report=0,
        ),
    )

    assert summary.real_match_report_coverage == 0.2
    assert summary.real_feedback_coverage == 1.0
    assert summary.next_priority == "expand_real_match_report_coverage"


def test_mvp_progress_generates_ready_reports_before_more_requirement_analysis() -> None:
    summary = build_mvp_progress_summary(
        _status(),
        real_loop=RealMvpLoopProgress(
            total_jobs=20,
            current_match_reports=4,
            feedback_covered_reports=4,
            requirement_analysis_needed=12,
            match_ready_without_report=4,
        ),
    )

    assert summary.next_priority == "generate_ready_match_reports"


def test_mvp_progress_marks_real_loop_observed_only_when_reports_and_feedback_cover_jobs() -> None:
    summary = build_mvp_progress_summary(
        _status(),
        real_loop=RealMvpLoopProgress(
            total_jobs=4,
            current_match_reports=4,
            feedback_covered_reports=4,
            requirement_analysis_needed=0,
            match_ready_without_report=0,
        ),
    )

    assert summary.real_match_report_coverage == 1.0
    assert summary.real_feedback_coverage == 1.0
    assert summary.next_priority == "real_mvp_value_loop_observed"
