"""Synthetic contract eval for the first Semantic Match LLM pipeline."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.ports.semantic_matcher import AbstractSemanticMatcher
from app.application.semantic_match import (
    SemanticMatchAssessmentOutput,
    SemanticMatchOutput,
    SemanticMatcherResult,
    SemanticMatchVerdict,
)
from app.evals.semantic_match import load_semantic_match_eval_cases, run_semantic_match_eval
from app.llm.semantic_matchers import FixtureSemanticMatcher
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows.semantic_match import SemanticMatchWorkflow

DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "semantic-match"
    / "semantic-match-v1.jsonl"
)
QUALITY_DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "semantic-match"
    / "semantic-match-quality-v1.jsonl"
)
CALIBRATION_DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "semantic-match"
    / "semantic-match-calibration-v2-canary.jsonl"
)
BLIND_HOLDOUT_DATASET = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "evals"
    / "semantic-match"
    / "semantic-match-blind-holdout-v1.jsonl"
)


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'semantic-match-eval.db'}")
    from app.db.base import Base

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_fixture_semantic_match_eval_covers_partial_non_override_contract(
    session_factory: sessionmaker[Session],
) -> None:
    cases = load_semantic_match_eval_cases(DATASET)
    report = run_semantic_match_eval(
        cases=cases,
        workflow=SemanticMatchWorkflow(
            matcher=FixtureSemanticMatcher(),
            trace_uow_factory=lambda: SqlAlchemyTraceUnitOfWork(session_factory),
        ),
    )

    assert report.total == 3
    assert report.passed == 3
    assert report.failed == 0
    assert all(item.passed for item in report.cases)
    mcp = next(item for item in report.cases if item.case_id == "mcp-related-blocked")
    assert mcp.expected_eligibility == "blocked"
    assert mcp.actual_eligibility == "blocked"
    assert mcp.expected_verdict == "partial"
    assert mcp.actual_verdict == "partial"
    assert report.verdict_accuracy == 1.0
    assert report.evidence_accuracy == 1.0
    assert report.workflow_success_rate == 1.0
    assert report.trace_coverage == 1.0
    assert report.confusion_matrix["partial"]["partial"] == 1
    assert mcp.trace_run_id is not None
    assert mcp.actual_evidence_ids == ("ev_tools",)
    assert mcp.actual_reason


def test_fixture_quality_eval_produces_reviewable_metrics_without_threshold_gate(
    session_factory: sessionmaker[Session],
) -> None:
    cases = load_semantic_match_eval_cases(QUALITY_DATASET)
    report = run_semantic_match_eval(
        cases=cases,
        workflow=SemanticMatchWorkflow(
            matcher=FixtureSemanticMatcher(),
            trace_uow_factory=lambda: SqlAlchemyTraceUnitOfWork(session_factory),
        ),
    )

    assert report.total == 10
    assert report.passed == 10
    assert report.failed == 0
    assert report.errors == 0
    assert report.verdict_accuracy == 1.0
    assert report.evidence_accuracy == 1.0
    assert report.workflow_success_rate == 1.0
    assert report.trace_coverage == 1.0
    assert report.provider_expected_cases == 8
    assert report.traced_provider_cases == 8
    assert report.confusion_matrix["matched"]["matched"] == 4
    assert report.confusion_matrix["partial"]["partial"] == 4
    assert report.confusion_matrix["not_matched"]["not_matched"] == 2
    assert not hasattr(report, "gate_passed")


class _UnderMatchingMatcher(AbstractSemanticMatcher):
    @property
    def model_name(self) -> str:
        return "under-matching"

    def match(self, requirements):
        return SemanticMatcherResult(
            output=SemanticMatchOutput(
                assessments=tuple(
                    SemanticMatchAssessmentOutput(
                        requirement_id=item.requirement_id,
                        verdict=SemanticMatchVerdict.NOT_MATCHED,
                        evidence_ids=(),
                        reason="Conservative synthetic mismatch for eval metric testing.",
                    )
                    for item in requirements
                )
            ),
            model=self.model_name,
        )


def test_blind_holdout_dataset_is_balanced_provider_bound_and_calibration_distinct() -> None:
    from app.llm.semantic_matchers import _SYSTEM_PROMPT

    holdout = load_semantic_match_eval_cases(BLIND_HOLDOUT_DATASET)
    calibration = load_semantic_match_eval_cases(CALIBRATION_DATASET)

    assert len(holdout) == 10
    verdict_counts = {
        verdict: sum(case.expected_verdict == verdict for case in holdout)
        for verdict in ("matched", "partial", "not_matched")
    }
    assert verdict_counts == {"matched": 3, "partial": 4, "not_matched": 3}
    assert all(case.provider_expected for case in holdout)
    assert all(case.evidence.requirements[0].candidates for case in holdout)

    for case in holdout:
        candidate_ids = {
            candidate.evidence_id
            for candidate in case.evidence.requirements[0].candidates
        }
        if case.expected_verdict == "not_matched":
            assert case.expected_evidence_ids == ()
        else:
            assert case.expected_evidence_ids
            assert set(case.expected_evidence_ids) <= candidate_ids

    calibration_ids = {case.id for case in calibration}
    assert calibration_ids.isdisjoint(case.id for case in holdout)

    calibration_pairs = {
        (
            case.eligibility.requirements[0].original_text,
            tuple(
                candidate.summary
                for candidate in case.evidence.requirements[0].candidates
            ),
        )
        for case in calibration
    }
    holdout_pairs = {
        (
            case.eligibility.requirements[0].original_text,
            tuple(
                candidate.summary
                for candidate in case.evidence.requirements[0].candidates
            ),
        )
        for case in holdout
    }
    assert calibration_pairs.isdisjoint(holdout_pairs)

    for requirement_text, candidate_summaries in holdout_pairs:
        assert requirement_text not in _SYSTEM_PROMPT
        assert all(summary not in _SYSTEM_PROMPT for summary in candidate_summaries)


def test_quality_eval_surfaces_model_mismatch_without_automatic_release_gate(
    session_factory: sessionmaker[Session],
) -> None:
    case = load_semantic_match_eval_cases(QUALITY_DATASET)[:1]
    report = run_semantic_match_eval(
        cases=case,
        workflow=SemanticMatchWorkflow(
            matcher=_UnderMatchingMatcher(),
            trace_uow_factory=lambda: SqlAlchemyTraceUnitOfWork(session_factory),
        ),
    )

    assert report.total == 1
    assert report.passed == 0
    assert report.failed == 1
    assert report.errors == 0
    assert report.verdict_accuracy == 0.0
    assert report.evidence_accuracy == 0.0
    assert report.workflow_success_rate == 1.0
    assert report.trace_coverage == 1.0
    assert report.confusion_matrix["partial"]["not_matched"] == 1
    assert not hasattr(report, "gate_passed")
