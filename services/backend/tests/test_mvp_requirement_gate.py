"""Tests for the default offline-first MVP Requirement quality gate."""
from __future__ import annotations

from dataclasses import dataclass

from scripts.check_mvp_requirement_gate import check_mvp_requirement_gate


@dataclass(frozen=True)
class _ReplayReport:
    gate_passed: bool
    passed_cases: int = 10
    total_cases: int = 10


@dataclass(frozen=True)
class _ProviderHealth:
    state: str
    ready_for_requirement_live_run: bool
    provider_calls: int
    blocker: str | None = None


def _match_demo(*, evidence_complete: bool = True) -> dict[str, object]:
    return {
        "externalProviderCalls": 0,
        "persistedMatchReports": 20,
        "topJobs": [
            {
                "jobId": f"fixture_job_{index:02d}",
                "evidenceLinks": ([{"requirementId": "req", "evidenceIds": ["ev"]}] if evidence_complete else []),
            }
            for index in range(1, 6)
        ],
    }


def test_mvp_gate_passes_from_offline_replay_and_match_demo_without_provider_smoke() -> None:
    result = check_mvp_requirement_gate(
        replay_runner=lambda: _ReplayReport(gate_passed=True),
        match_demo_runner=_match_demo,
        include_provider_smoke=False,
    )

    assert result.gate_passed is True
    assert result.replay_passed is True
    assert result.match_demo_passed is True
    assert result.match_demo_persisted_reports == 20
    assert result.match_demo_top_jobs == 5
    assert result.match_demo_evidence_complete is True
    assert result.provider_smoke_state == "not_requested"
    assert result.provider_smoke_blocking is False
    assert result.provider_calls == 0


def test_mvp_gate_provider_outage_is_visible_but_non_blocking() -> None:
    result = check_mvp_requirement_gate(
        replay_runner=lambda: _ReplayReport(gate_passed=True),
        match_demo_runner=_match_demo,
        include_provider_smoke=True,
        provider_smoke_runner=lambda: _ProviderHealth(
            state="unhealthy",
            ready_for_requirement_live_run=False,
            provider_calls=2,
            blocker="HTTP 503",
        ),
    )

    assert result.gate_passed is True
    assert result.replay_passed is True
    assert result.provider_smoke_state == "unhealthy"
    assert result.provider_smoke_blocking is False
    assert result.provider_smoke_ready is False
    assert result.provider_calls == 2
    assert result.provider_smoke_blocker == "HTTP 503"


def test_mvp_gate_fails_when_offline_replay_fails_even_if_provider_is_healthy() -> None:
    result = check_mvp_requirement_gate(
        replay_runner=lambda: _ReplayReport(
            gate_passed=False,
            passed_cases=9,
            total_cases=10,
        ),
        match_demo_runner=_match_demo,
        include_provider_smoke=True,
        provider_smoke_runner=lambda: _ProviderHealth(
            state="healthy",
            ready_for_requirement_live_run=True,
            provider_calls=2,
        ),
    )

    assert result.gate_passed is False
    assert result.replay_passed is False
    assert result.provider_smoke_state == "healthy"
    assert result.provider_smoke_ready is True
    assert result.provider_smoke_blocking is False


def test_mvp_gate_fails_when_offline_match_demo_has_missing_top_n_evidence() -> None:
    result = check_mvp_requirement_gate(
        replay_runner=lambda: _ReplayReport(gate_passed=True),
        match_demo_runner=lambda: _match_demo(evidence_complete=False),
        include_provider_smoke=False,
    )

    assert result.replay_passed is True
    assert result.match_demo_passed is False
    assert result.match_demo_evidence_complete is False
    assert result.gate_passed is False
