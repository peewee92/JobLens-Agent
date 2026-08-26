"""Offline MVP value-loop demo from fixture semantic match to persisted Top-N ranking."""
from __future__ import annotations

from pathlib import Path

from scripts.run_offline_match_demo import run_demo


def test_offline_demo_persists_twenty_fixture_match_reports_and_returns_stable_top_five(
    tmp_path: Path,
) -> None:
    result = run_demo(database_path=tmp_path / "offline-match-demo.db", top_n=5)

    assert result["mode"] == "offline_fixture"
    assert result["externalProviderCalls"] == 0
    assert result["persistedMatchReports"] == 20
    assert result["fixtureScenarios"] == {"blocked": 1, "withoutEvidence": 1}
    assert len(result["topJobs"]) == 5
    assert [item["jobId"] for item in result["topJobs"]] == [
        "fixture_job_01",
        "fixture_job_02",
        "fixture_job_03",
        "fixture_job_04",
        "fixture_job_05",
    ]
    assert result["topJobs"][0]["rank"] == 1
    assert result["topJobs"][0]["reason"]
    assert all(item["evidenceLinks"] for item in result["topJobs"])
    assert {item["jobId"] for item in result["topJobs"]}.isdisjoint(
        {"fixture_job_19", "fixture_job_20"}
    )
