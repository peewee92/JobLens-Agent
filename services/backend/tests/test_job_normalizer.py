from copy import deepcopy
import json
from pathlib import Path

from app.application.job_imports.adapter import adapt_collector_report
from app.application.job_imports.normalizer import normalize_adapted_report
from app.domain.jobs import RemoteConfidence, RemoteStatus


SAMPLE_REPORT = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "samples"
    / "collector-report-minimal.json"
)


def load_sample_report() -> dict:
    return json.loads(SAMPLE_REPORT.read_text(encoding="utf-8"))


def test_normalize_report_produces_version_agnostic_job_input() -> None:
    payload = load_sample_report()
    payload["jobs"][0].update(
        {
            "title": "  AI   应用开发工程师  ",
            "company": "  示例公司 ",
            "skills": ["Python", " python ", "RAG", ""],
            "url": "http://m.zhipin.com/job_detail/Example-ID.html?ka=search",
            "remoteStatus": "confirmed",
            "remoteConfidence": "medium",
            "collectorOnlyField": "preserve me",
        }
    )

    normalized_report = normalize_adapted_report(adapt_collector_report(payload))
    job = normalized_report.jobs[0]

    assert normalized_report.received == 1
    assert normalized_report.issues == ()
    assert job.title == "AI 应用开发工程师"
    assert job.company == "示例公司"
    assert job.skills == ("Python", "RAG")
    assert job.source == "boss"
    assert job.source_job_id == "Example-ID"
    assert job.normalized_source_url == (
        "https://www.zhipin.com/job_detail/Example-ID.html"
    )
    assert job.canonical_key == "v1:boss:id:Example-ID"
    assert job.remote_status is RemoteStatus.CONFIRMED
    assert job.remote_confidence is RemoteConfidence.MEDIUM
    assert job.source_raw["collectorOnlyField"] == "preserve me"
    assert job.collected_at.utcoffset().total_seconds() == 0


def test_missing_remote_status_does_not_treat_false_marker_as_rejected() -> None:
    payload = load_sample_report()
    payload["jobs"][0].pop("remoteStatus", None)
    payload["jobs"][0].pop("remoteConfidence", None)
    payload["jobs"][0]["remoteMatched"] = False

    report = normalize_adapted_report(adapt_collector_report(payload))
    job = report.jobs[0]

    assert job.remote_status is RemoteStatus.UNKNOWN
    assert job.remote_confidence is RemoteConfidence.LOW


def test_source_id_mismatch_becomes_normalization_issue() -> None:
    payload = load_sample_report()
    payload["jobs"][0]["sourceJobId"] = "different-id"

    report = normalize_adapted_report(adapt_collector_report(payload))

    assert report.jobs == ()
    assert len(report.issues) == 1
    assert report.issues[0].code == "source_identity_mismatch"


def test_invalid_salary_range_becomes_non_fatal_normalization_issue() -> None:
    payload = load_sample_report()
    payload["jobs"][0]["salaryMinK"] = 30
    payload["jobs"][0]["salaryMaxK"] = 15

    report = normalize_adapted_report(adapt_collector_report(payload))

    assert report.jobs == ()
    assert report.received == 1
    assert len(report.issues) == 1
    assert report.issues[0].stage == "normalizer"
    assert report.issues[0].code == "invalid_salary_range"
    assert report.issues[0].raw is not None


def test_adapter_and_normalizer_issues_are_accumulated() -> None:
    payload = load_sample_report()

    missing_company = deepcopy(payload["jobs"][0])
    missing_company.pop("company")

    invalid_host = deepcopy(payload["jobs"][0])
    invalid_host["url"] = "https://example.com/job_detail/abc.html"

    payload["jobs"] = [payload["jobs"][0], missing_company, invalid_host]

    report = normalize_adapted_report(adapt_collector_report(payload))

    assert len(report.jobs) == 1
    assert report.received == 3
    assert {(issue.stage, issue.code) for issue in report.issues} == {
        ("adapter", "invalid_job_payload"),
        ("normalizer", "invalid_source_url"),
    }
