"""Print the small set of engineering metrics used to track JobLens MVP progress."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from fastapi.testclient import TestClient

from app.evals.mvp_progress import RealMvpLoopProgress, build_mvp_progress_summary
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


def main() -> int:
    args = _arguments()
    summary = build_mvp_progress_summary(
        evaluate_mvp_quality_status(),
        real_loop=_load_real_loop_progress(),
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
            f"nextPriority={summary.next_priority}"
        )
    return 0 if summary.mvp_gate_passed and summary.top_n_available else 1


if __name__ == "__main__":
    raise SystemExit(main())
