"""Run a deterministic offline MatchReport -> Top-N demo using SQLite fixtures."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from app.evals.mvp_quality import run_offline_match_demo

# Backwards-compatible import used by existing tests and callers.
run_demo = run_offline_match_demo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.top_n < 1 or args.top_n > 50:
        parser.error("--top-n must be between 1 and 50")

    if args.database is None:
        with tempfile.TemporaryDirectory(prefix="joblens-offline-match-") as directory:
            result = run_demo(database_path=Path(directory) / "demo.db", top_n=args.top_n)
    else:
        result = run_demo(database_path=args.database, top_n=args.top_n)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Offline fixture Top {len(result['topJobs'])}: externalProviderCalls=0")
        for item in result["topJobs"]:
            print(f"{item['rank']}. {item['jobId']} — {item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
