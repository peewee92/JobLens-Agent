"""Run the Profile Extraction dataset against the configured provider."""
from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.evals import load_profile_eval_cases, run_profile_eval
from app.llm import build_profile_extractor
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows import ProposeProfileFromResumeWorkflow

DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "profile-extraction"
    / "profile-extraction-v1.jsonl"
)


def main() -> int:
    settings = get_settings()
    workflow = ProposeProfileFromResumeWorkflow(
        build_profile_extractor(settings),
        lambda: SqlAlchemyTraceUnitOfWork(SessionLocal),
    )
    report = run_profile_eval(workflow, load_profile_eval_cases(DATASET))
    print(
        f"Profile Eval provider={settings.profile_extractor_provider} "
        f"passed={report.passed}/{report.total} rate={report.pass_rate:.2%}"
    )
    for failure in report.failures:
        print(f"- {failure.case_id}: {failure.reason}")
    return 0 if not report.failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
