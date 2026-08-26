"""Print the small set of engineering metrics used to track JobLens MVP progress."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json

from app.evals.mvp_progress import build_mvp_progress_summary
from app.evals.mvp_quality import evaluate_mvp_quality_status


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    summary = build_mvp_progress_summary(evaluate_mvp_quality_status())
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
            f"nextPriority={summary.next_priority}"
        )
    return 0 if summary.mvp_gate_passed and summary.top_n_available else 1


if __name__ == "__main__":
    raise SystemExit(main())
