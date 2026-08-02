from copy import deepcopy
import json
from pathlib import Path

import pytest

from app.application.job_imports.adapter import adapt_collector_report
from app.application.job_imports.errors import (
    InvalidCollectorReportError,
    UnsupportedCollectorVersionError,
)


SAMPLE_REPORT = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "samples"
    / "collector-report-minimal.json"
)


def load_sample_report() -> dict:
    return json.loads(SAMPLE_REPORT.read_text(encoding="utf-8"))


def test_adapt_collector_v131_report_preserves_raw_source() -> None:
    payload = load_sample_report()
    payload["jobs"][0]["collectorOnlyField"] = {"nested": True}
    payload["candidates"] = [{"title": "diagnostic candidate"}]

    report = adapt_collector_report(payload)

    assert report.source_version == "1.3.1"
    assert report.received == 1
    assert len(report.jobs) == 1
    assert report.issues == ()
    assert report.jobs[0].job.title == "AI 应用开发工程师"
    assert report.jobs[0].source_raw["collectorOnlyField"] == {"nested": True}
    assert report.candidate_count == 1
    assert report.candidates_raw[0] == {"title": "diagnostic candidate"}


def test_adapter_rejects_unsupported_report_version() -> None:
    payload = load_sample_report()
    payload["version"] = "2.0.0"

    with pytest.raises(UnsupportedCollectorVersionError):
        adapt_collector_report(payload)


def test_adapter_rejects_invalid_report_envelope() -> None:
    payload = load_sample_report()
    del payload["generatedAt"]

    with pytest.raises(InvalidCollectorReportError, match="generatedAt"):
        adapt_collector_report(payload)


def test_adapter_keeps_valid_jobs_when_one_item_is_invalid() -> None:
    payload = load_sample_report()
    invalid_job = deepcopy(payload["jobs"][0])
    invalid_job.pop("company")
    payload["jobs"].append(invalid_job)
    payload["jobs"].append("not-an-object")

    report = adapt_collector_report(payload)

    assert report.received == 3
    assert len(report.jobs) == 1
    assert [issue.code for issue in report.issues] == [
        "invalid_job_payload",
        "invalid_job_type",
    ]
    assert report.issues[0].index == 1
    assert report.issues[0].raw is not None
