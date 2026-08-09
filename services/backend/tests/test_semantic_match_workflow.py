"""Semantic Match workflow tests for non-overriding evidence judgments."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.eligibility import (
    EligibilityDecision,
    JobEligibilityResult,
    RequirementEligibilityResult,
    RequirementFitStatus,
)
from app.application.evidence_retrieval import (
    CandidateEvidence,
    EvidenceRelevanceTier,
    EvidenceRetrievalBasis,
    JobEvidenceRetrievalResult,
    RequirementEvidenceCandidates,
)
from app.application.ports.semantic_matcher import AbstractSemanticMatcher
from app.application.semantic_match import (
    InvalidSemanticMatcherOutputError,
    SemanticMatchAssessmentOutput,
    SemanticMatchOutput,
    SemanticMatcherResult,
    SemanticMatchVerdict,
)
from app.db.base import Base
from app.db.models import TraceSpanORM
from app.domain.career_context import EvidenceType
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.llm.semantic_matchers import FixtureSemanticMatcher
from app.repositories import SqlAlchemyTraceUnitOfWork
from app.workflows.semantic_match import SemanticMatchWorkflow


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'semantic-match.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _eligibility(
    *,
    status: RequirementFitStatus = RequirementFitStatus.MISSING,
    overall: EligibilityDecision = EligibilityDecision.BLOCKED,
    evidence_ids: tuple[str, ...] = (),
    profile_fact_refs: tuple[str, ...] = (),
) -> JobEligibilityResult:
    item = RequirementEligibilityResult(
        requirement_id="req_mcp",
        requirement_index=0,
        type=RequirementType.SKILL,
        importance=RequirementImportance.MUST_HAVE,
        original_text="熟悉 MCP 协议",
        normalized_capability="MCP",
        status=status,
        evidence_ids=evidence_ids,
        profile_fact_refs=profile_fact_refs,
        reason="deterministic eligibility",
    )
    return JobEligibilityResult(
        job_id="job_1",
        profile_id="profile_1",
        profile_version=3,
        extraction_id="reqrun_1",
        eligibility=overall,
        requirements=(item,),
        matched_count=int(status is RequirementFitStatus.MATCHED),
        conditional_count=int(status is RequirementFitStatus.CONDITIONAL),
        missing_count=int(status is RequirementFitStatus.MISSING),
    )


def _related_retrieval() -> JobEvidenceRetrievalResult:
    candidate = CandidateEvidence(
        evidence_id="ev_tools",
        evidence_key="agent-tools",
        evidence_type=EvidenceType.PROJECT,
        summary="实现 Agent Function Calling、工具调用和工具集成。",
        source="confirmed by user",
        relevance_tier=EvidenceRelevanceTier.RELATED,
        retrieval_basis=EvidenceRetrievalBasis.RELATED_CAPABILITY_HINT,
        matched_terms=("Function Calling", "工具调用", "工具集成"),
        reason="与 MCP 工具生态相关，但不等同于 MCP 经验。",
    )
    requirement = RequirementEvidenceCandidates(
        requirement_id="req_mcp",
        requirement_index=0,
        type=RequirementType.SKILL,
        importance=RequirementImportance.MUST_HAVE,
        original_text="熟悉 MCP 协议",
        normalized_capability="MCP",
        candidates=(candidate,),
    )
    return JobEvidenceRetrievalResult(
        job_id="job_1",
        profile_id="profile_1",
        profile_version=3,
        extraction_id="reqrun_1",
        requirements=(requirement,),
        candidate_count=1,
    )


def _workflow(
    factory: sessionmaker[Session],
    matcher: AbstractSemanticMatcher,
) -> SemanticMatchWorkflow:
    return SemanticMatchWorkflow(
        matcher=matcher,
        trace_uow_factory=lambda: SqlAlchemyTraceUnitOfWork(factory),
    )


def test_related_mcp_evidence_can_be_partial_but_cannot_override_blocked(
    session_factory: sessionmaker[Session],
) -> None:
    result = _workflow(session_factory, FixtureSemanticMatcher()).execute(
        eligibility=_eligibility(),
        evidence=_related_retrieval(),
    )

    assert result.eligibility is EligibilityDecision.BLOCKED
    assert result.assessments[0].eligibility_status is RequirementFitStatus.MISSING
    assert result.assessments[0].verdict is SemanticMatchVerdict.PARTIAL
    assert result.assessments[0].evidence_ids == ("ev_tools",)
    assert result.assessments[0].profile_fact_refs == ()
    assert result.provider_calls == 1
    assert result.trace_runs_created == 1
    assert result.trace_run_id is not None

    with session_factory() as session:
        trace = session.get(TraceSpanORM, result.trace_run_id)
        assert trace is not None
        assert trace.capability == "semantic_match"
        assert trace.output["assessments"][0]["verdict"] == "partial"
        assert trace.input_refs["jobId"] == "job_1"
        assert trace.input_refs["candidateEvidenceIds"] == ["ev_tools"]
        assert "实现 Agent Function Calling" not in str(trace.input_refs)
        assert trace.error is None


class _OverclaimingMatcher(AbstractSemanticMatcher):
    @property
    def model_name(self) -> str:
        return "overclaiming"

    def match(self, requirements):
        return SemanticMatcherResult(
            output=SemanticMatchOutput(
                assessments=(
                    SemanticMatchAssessmentOutput(
                        requirement_id="req_mcp",
                        verdict=SemanticMatchVerdict.MATCHED,
                        evidence_ids=("ev_tools",),
                        reason="Function Calling is close enough to MCP.",
                    ),
                )
            ),
            model=self.model_name,
        )


def test_related_only_evidence_cannot_be_promoted_to_matched_even_if_provider_overclaims(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(InvalidSemanticMatcherOutputError) as captured:
        _workflow(session_factory, _OverclaimingMatcher()).execute(
            eligibility=_eligibility(),
            evidence=_related_retrieval(),
        )

    assert captured.value.run_id is not None
    with session_factory() as session:
        trace = session.get(TraceSpanORM, captured.value.run_id)
        assert trace is not None
        assert "related-only" in (trace.error or "")
        assert trace.output["assessments"][0]["verdict"] == "matched"


class _HallucinatingEvidenceMatcher(AbstractSemanticMatcher):
    @property
    def model_name(self) -> str:
        return "hallucinating-evidence"

    def match(self, requirements):
        return SemanticMatcherResult(
            output=SemanticMatchOutput(
                assessments=(
                    SemanticMatchAssessmentOutput(
                        requirement_id="req_mcp",
                        verdict=SemanticMatchVerdict.PARTIAL,
                        evidence_ids=("ev_invented",),
                        reason="invented evidence",
                    ),
                )
            ),
            model=self.model_name,
        )


def test_provider_cannot_cite_evidence_outside_retrieved_candidates(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(InvalidSemanticMatcherOutputError):
        _workflow(session_factory, _HallucinatingEvidenceMatcher()).execute(
            eligibility=_eligibility(),
            evidence=_related_retrieval(),
        )


class _ShouldNotRunMatcher(AbstractSemanticMatcher):
    @property
    def model_name(self) -> str:
        return "should-not-run"

    def match(self, requirements):
        raise AssertionError("deterministic matched requirements must bypass semantic provider")


def test_deterministic_matched_requirement_bypasses_provider_and_trace(
    session_factory: sessionmaker[Session],
) -> None:
    result = _workflow(session_factory, _ShouldNotRunMatcher()).execute(
        eligibility=_eligibility(
            status=RequirementFitStatus.MATCHED,
            overall=EligibilityDecision.ELIGIBLE,
            evidence_ids=("ev_tools",),
        ),
        evidence=_related_retrieval(),
    )

    assert result.eligibility is EligibilityDecision.ELIGIBLE
    assert result.assessments[0].verdict is SemanticMatchVerdict.MATCHED
    assert result.assessments[0].evidence_ids == ("ev_tools",)
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0
    assert result.trace_run_id is None
    with session_factory() as session:
        assert session.query(TraceSpanORM).count() == 0
