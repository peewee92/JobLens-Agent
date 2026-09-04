"""Print the small set of engineering metrics used to track JobLens MVP progress."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from fastapi.testclient import TestClient

from app.evals.mvp_progress import (
    RealMvpLoopProgress,
    RequirementReviewProgress,
    build_mvp_progress_summary,
)
from app.workflows.job_requirement_extraction import EXTRACTOR_VERSION
from app.evals.mvp_quality import evaluate_mvp_quality_status
from app.main import app


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _load_real_loop_progress() -> RealMvpLoopProgress | None:
    """Read the current real MVP loop through public read-only API policy."""
    try:
        with TestClient(app) as client:
            coverage_response = client.get("/api/v1/recommendation-coverage")
            coverage_response.raise_for_status()
            coverage = coverage_response.json()

            jobs_response = client.get("/api/v1/jobs", params={"limit": 50})
            jobs_response.raise_for_status()
            job_ids = [item["id"] for item in jobs_response.json()["items"]]

            report_ids: list[str] = []
            if job_ids:
                ranking_params = [("jobId", job_id) for job_id in job_ids]
                ranking_params.extend((("includeBlocked", "true"), ("topN", "50")))
                ranking_response = client.get("/api/v1/match-ranking", params=ranking_params)
                ranking_response.raise_for_status()
                report_ids = [item["reportId"] for item in ranking_response.json()["items"]]

            feedback_covered_reports = 0
            if report_ids:
                feedback_response = client.get(
                    "/api/v1/user-feedback/latest",
                    params=[("matchReportId", report_id) for report_id in report_ids],
                )
                feedback_response.raise_for_status()
                feedback_covered_reports = len(feedback_response.json()["feedback"])

            return RealMvpLoopProgress(
                total_jobs=int(coverage["totalJobCount"]),
                current_match_reports=int(coverage["currentReportCount"]),
                feedback_covered_reports=feedback_covered_reports,
                requirement_analysis_needed=int(coverage["requirementAnalysisNeededCount"]),
                match_ready_without_report=int(coverage["matchReadyWithoutReportCount"]),
            )
    except Exception:
        # Real-loop visibility is diagnostic. It must never turn a healthy offline MVP gate red.
        return None


def _load_requirement_review_progress() -> RequirementReviewProgress | None:
    """Read the newest current 20-case Requirement human-review gate."""
    try:
        with TestClient(app) as client:
            batches_response = client.get(
                "/api/v1/requirement-review-batches",
                params={"limit": 20, "offset": 0},
            )
            batches_response.raise_for_status()
            batches = batches_response.json()["items"]
            current = next(
                (
                    item
                    for item in batches
                    if int(item["sampleSize"]) == 20
                    and item["extractorVersion"] == EXTRACTOR_VERSION
                    and int(item["staleCaseCount"]) == 0
                    and item["provider"] != "fixture"
                ),
                None,
            )
            if current is None:
                return None

            detail_response = client.get(
                f"/api/v1/requirement-review-batches/{current['id']}"
            )
            detail_response.raise_for_status()
            detail = detail_response.json()
            summary = detail["summary"]
            return RequirementReviewProgress(
                sample_size=int(summary["sampleSize"]),
                reviewed_count=int(summary["reviewedCount"]),
                accepted_count=int(summary["acceptedCount"]),
                rejected_count=int(summary["rejectedCount"]),
                final_decision=summary["finalDecision"],
                match_release_eligible=bool(summary["matchReleaseEligible"]),
                issue_code_counts={
                    str(code): int(count)
                    for code, count in detail["issueCodeCounts"].items()
                },
                semantic_policy_version=summary.get("semanticPolicyVersion"),
            )
    except Exception:
        # Human-review visibility is diagnostic and must not turn the offline gate red.
        return None


def main() -> int:
    args = _arguments()
    summary = build_mvp_progress_summary(
        evaluate_mvp_quality_status(),
        real_loop=_load_real_loop_progress(),
        requirement_review=_load_requirement_review_progress(),
    )
    payload = asdict(summary)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            "MVP progress "
            f"gatePassed={summary.mvp_gate_passed} "
            f"offlineE2E={summary.offline_e2e_slices_completed}/{summary.offline_e2e_slices_total} "
            f"topN={summary.top_n_jobs if summary.top_n_available else 0}/5 "
            f"extractionFrozen={summary.extraction_frozen} "
            f"providerSmokeBlocking={summary.provider_smoke_blocking} "
            f"realMatchReports={summary.real_current_match_reports if summary.real_loop_data_available else 'unknown'}/"
            f"{summary.real_total_jobs if summary.real_loop_data_available else 'unknown'} "
            f"realFeedback={summary.real_feedback_covered_reports if summary.real_loop_data_available else 'unknown'}/"
            f"{summary.real_current_match_reports if summary.real_loop_data_available else 'unknown'} "
            f"requirementReview={summary.requirement_review_reviewed_count if summary.requirement_review_data_available else 'unknown'}/"
            f"{summary.requirement_review_sample_size if summary.requirement_review_data_available else 'unknown'} "
            f"requirementDecision={summary.requirement_review_final_decision or 'pending'} "
            f"nextPriority={summary.next_priority}"
        )
    return 0 if summary.mvp_gate_passed and summary.top_n_available else 1


if __name__ == "__main__":
    raise SystemExit(main())
