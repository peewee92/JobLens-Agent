"""MVP progress summary tests."""
from __future__ import annotations

from dataclasses import replace

from app.evals.mvp_progress import build_mvp_progress_summary
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
    assert summary.next_priority == "stage_5_version_bump_timebox"


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
