"""Run Semantic Match quality eval without writing the JobLens business database."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.base import Base
from app.db.models import TraceSpanORM
from app.evals.semantic_match import (
    SemanticMatchEvalReport,
    load_semantic_match_eval_cases,
    run_semantic_match_eval,
)
from app.llm import build_semantic_matcher
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows.semantic_match import SemanticMatchWorkflow

DEFAULT_DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "semantic-match"
    / "semantic-match-quality-v1.jsonl"
)


def resolve_eval_mode(provider: str, *, confirm_live_cost: bool) -> str:
    normalized = provider.strip().casefold()
    if normalized == "fixture":
        return "fixture"
    if normalized == "openai":
        if not confirm_live_cost:
            raise ValueError(
                "Live Semantic Match Eval requires --confirm-live-cost before Provider calls."
            )
        return "live"
    raise ValueError(
        "Semantic Match Eval requires SEMANTIC_MATCH_PROVIDER=fixture or openai; "
        f"received {normalized!r}."
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument(
        "--max-cases",
        type=int,
        help="Bound the number of cases. Required for live Provider evals.",
    )
    parser.add_argument("--confirm-live-cost", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _report_payload(
    *,
    report: SemanticMatchEvalReport,
    dataset: Path,
    mode: str,
    provider: str,
    model: str,
    traces: list[TraceSpanORM],
) -> dict[str, object]:
    return {
        "dataset": str(dataset),
        "datasetVersion": dataset.stem,
        "mode": mode,
        "provider": provider,
        "model": model,
        "qualityGateApplied": False,
        "humanReviewRequired": mode == "live",
        "metrics": {
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "succeeded": report.succeeded,
            "errors": report.errors,
            "verdictAccuracy": report.verdict_accuracy,
            "evidenceAccuracy": report.evidence_accuracy,
            "workflowSuccessRate": report.workflow_success_rate,
            "traceCoverage": report.trace_coverage,
            "providerExpectedCases": report.provider_expected_cases,
            "tracedProviderCases": report.traced_provider_cases,
        },
        "confusionMatrix": report.confusion_matrix,
        "cases": [
            {
                "caseId": item.case_id,
                "passed": item.passed,
                "expectedEligibility": item.expected_eligibility,
                "actualEligibility": item.actual_eligibility,
                "expectedVerdict": item.expected_verdict,
                "actualVerdict": item.actual_verdict,
                "expectedEvidenceIds": list(item.expected_evidence_ids),
                "actualEvidenceIds": list(item.actual_evidence_ids),
                "actualReason": item.actual_reason,
                "providerExpected": item.provider_expected,
                "traceRunId": item.trace_run_id,
                "error": item.error,
            }
            for item in report.cases
        ],
        "traces": [
            {
                "runId": trace.id,
                "capability": trace.capability,
                "version": trace.version,
                "model": trace.model,
                "promptVersion": trace.prompt_version,
                "inputRefs": trace.input_refs,
                "output": trace.output,
                "latencyMs": trace.latency_ms,
                "inputTokens": trace.input_tokens,
                "outputTokens": trace.output_tokens,
                "error": trace.error,
            }
            for trace in traces
        ],
    }


def main() -> int:
    args = _arguments()
    settings = get_settings()
    provider = settings.semantic_match_provider.strip().casefold()
    try:
        mode = resolve_eval_mode(
            provider,
            confirm_live_cost=args.confirm_live_cost,
        )
    except ValueError as error:
        print(str(error))
        return 2

    if args.max_cases is not None and args.max_cases < 1:
        print("--max-cases must be at least 1.")
        return 2
    if mode == "live" and args.max_cases is None:
        print("Live Semantic Match Eval requires an explicit --max-cases bound.")
        return 2

    cases = load_semantic_match_eval_cases(args.dataset)
    if args.max_cases is not None:
        cases = cases[: args.max_cases]

    matcher = build_semantic_matcher(settings)
    with TemporaryDirectory(prefix="joblens-semantic-match-eval-") as temp_dir:
        engine = create_engine(
            f"sqlite+pysqlite:///{Path(temp_dir) / 'trace.db'}"
        )
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        workflow = SemanticMatchWorkflow(
            matcher=matcher,
            trace_uow_factory=lambda: SqlAlchemyTraceUnitOfWork(session_factory),
        )
        report = run_semantic_match_eval(cases=cases, workflow=workflow)
        with session_factory() as session:
            traces = list(
                session.scalars(
                    select(TraceSpanORM).order_by(TraceSpanORM.created_at, TraceSpanORM.id)
                ).all()
            )
        payload = _report_payload(
            report=report,
            dataset=args.dataset,
            mode=mode,
            provider=provider,
            model=matcher.model_name,
            traces=traces,
        )
        engine.dispose()

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        metrics = payload["metrics"]
        assert isinstance(metrics, dict)
        print(
            "Semantic Match Eval "
            f"mode={mode} provider={provider} model={matcher.model_name} "
            f"cases={metrics['total']} verdictAccuracy={metrics['verdictAccuracy']:.2%} "
            f"evidenceAccuracy={metrics['evidenceAccuracy']:.2%} "
            f"workflowSuccess={metrics['workflowSuccessRate']:.2%} "
            f"traceCoverage={metrics['traceCoverage']:.2%}"
        )
        print("No automatic quality threshold was applied; review live cases manually.")
        for item in report.cases:
            if not item.passed:
                print(
                    f"- {item.case_id}: expected={item.expected_verdict} "
                    f"actual={item.actual_verdict or 'error'} trace={item.trace_run_id or 'none'} "
                    f"error={item.error or 'none'}"
                )

    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
