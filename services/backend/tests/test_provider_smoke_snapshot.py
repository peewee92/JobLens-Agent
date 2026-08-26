"""Persisted Provider smoke snapshot tests."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.evals.mvp_quality import evaluate_mvp_quality_status
from app.evals.provider_smoke import (
    ProviderSmokeSnapshot,
    load_provider_smoke_snapshot,
    save_provider_smoke_snapshot,
)


def test_provider_smoke_snapshot_round_trips_without_secrets(tmp_path: Path) -> None:
    path = tmp_path / "latest.json"
    snapshot = ProviderSmokeSnapshot(
        checked_at=datetime(2026, 8, 26, 1, 30, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
        state="unhealthy",
        provider="openai",
        model="deepseek-v4-flash",
        ready=False,
        blocker="plain_probe_failed",
        provider_calls=1,
        plain_status_code=503,
        structured_status_code=None,
    )

    save_provider_smoke_snapshot(snapshot, path=path)

    loaded = load_provider_smoke_snapshot(path=path)
    assert loaded == snapshot
    serialized = path.read_text(encoding="utf-8")
    assert "api_key" not in serialized.casefold()
    assert "authorization" not in serialized.casefold()


def test_missing_provider_smoke_snapshot_returns_none(tmp_path: Path) -> None:
    assert load_provider_smoke_snapshot(path=tmp_path / "missing.json") is None


def test_malformed_provider_smoke_snapshot_fails_soft(tmp_path: Path) -> None:
    path = tmp_path / "latest.json"
    path.write_text("not-json", encoding="utf-8")

    assert load_provider_smoke_snapshot(path=path) is None


def test_mvp_quality_reads_unhealthy_snapshot_without_blocking_offline_gate(tmp_path: Path) -> None:
    path = tmp_path / "latest.json"
    save_provider_smoke_snapshot(
        ProviderSmokeSnapshot(
            checked_at="2026-08-26T01:30:00Z",
            state="unhealthy",
            provider="openai",
            model="deepseek-v4-flash",
            ready=False,
            blocker="plain_probe_failed",
            provider_calls=1,
            plain_status_code=503,
            structured_status_code=None,
        ),
        path=path,
    )

    status = evaluate_mvp_quality_status(provider_smoke_snapshot_path=path)

    assert status.gate_passed is True
    assert status.provider_smoke_state == "unhealthy"
    assert status.provider_smoke_ready is False
    assert status.provider_smoke_blocking is False
    assert status.provider_smoke_checked_at == "2026-08-26T01:30:00Z"
    assert status.provider_smoke_plain_status_code == 503
    assert status.provider_smoke_structured_status_code is None
    assert status.provider_calls == 0


def test_mvp_quality_treats_missing_snapshot_as_never_run(tmp_path: Path) -> None:
    status = evaluate_mvp_quality_status(
        provider_smoke_snapshot_path=tmp_path / "missing.json"
    )

    assert status.gate_passed is True
    assert status.provider_smoke_state == "never_run"
    assert status.provider_smoke_ready is None
    assert status.provider_smoke_blocking is False
    assert status.provider_calls == 0
