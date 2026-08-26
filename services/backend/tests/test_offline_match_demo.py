"""Offline MVP value-loop demo from fixture semantic match to persisted Top-N ranking."""
from __future__ import annotations

from pathlib import Path

from scripts.run_offline_match_demo import run_demo


def test_offline_demo_persists_fixture_match_reports_and_returns_top_five(tmp_path: Path) -> None:
    result = run_demo(database_path=tmp_path / "offline-match-demo.db", top_n=5)

    assert result["mode"] == "offline_fixture"
    assert result["externalProviderCalls"] == 0
    assert result["persistedMatchReports"] >= 5
    assert len(result["topJobs"]) == 5
    assert result["topJobs"][0]["rank"] == 1
    assert result["topJobs"][0]["reason"]
    assert result["topJobs"][0]["evidenceLinks"]
    assert all(item["evidenceLinks"] for item in result["topJobs"])
