"""Deterministic Recommendation Policy + transient MatchReport tests."""
from __future__ import annotations

from app.application.eligibility import (
    EligibilityDecision,
    JobEligibilityResult,
    RequirementEligibilityResult,
    RequirementFitStatus,
)
from app.application.semantic_match import (
    JobSemanticMatchResult,
    SemanticAssessmentSource,
    SemanticMatchVerdict,
    SemanticRequirementAssessment,
)
from app.domain.job_requirements import RequirementImportance, RequirementType


def _assessment(
    requirement_id: str,
    index: int,
    *,
    importance: RequirementImportance,
    verdict: SemanticMatchVerdict,
    eligibility_status: RequirementFitStatus = RequirementFitStatus.MATCHED,
    evidence_ids: tuple[str, ...] = ("ev_1",),
) -> SemanticRequirementAssessment:
    return SemanticRequirementAssessment(
        requirement_id=requirement_id,
        requirement_index=index,
        type=RequirementType.SKILL,
        importance=importance,
        original_text=f"requirement {requirement_id}",
        normalized_capability=requirement_id,
        eligibility_status=eligibility_status,
        verdict=verdict,
        evidence_ids=evidence_ids if verdict is not SemanticMatchVerdict.NOT_MATCHED else (),
        profile_fact_refs=(),
        reason=f"reason for {requirement_id}",
        source=SemanticAssessmentSource.DETERMINISTIC,
    )


def _semantic(
    *,
    eligibility: EligibilityDecision,
    assessments: tuple[SemanticRequirementAssessment, ...],
) -> JobSemanticMatchResult:
    return JobSemanticMatchResult(
        job_id="job_1",
        profile_id="profile_1",
        profile_version=3,
        extraction_id="reqrun_1",
        eligibility=eligibility,
        assessments=assessments,
        matched_count=sum(item.verdict is SemanticMatchVerdict.MATCHED for item in assessments),
        partial_count=sum(item.verdict is SemanticMatchVerdict.PARTIAL for item in assessments),
        not_matched_count=sum(item.verdict is SemanticMatchVerdict.NOT_MATCHED for item in assessments),
        matcher_version="semantic-match-v1",
        prompt_version="semantic-match-v1",
        model="fixture-semantic-matcher",
        trace_run_id="run_1",
        provider_calls=1,
        trace_runs_created=1,
    )


def _eligibility(
    *,
    decision: EligibilityDecision,
    requirements: tuple[RequirementEligibilityResult, ...],
) -> JobEligibilityResult:
    return JobEligibilityResult(
        job_id="job_1",
        profile_id="profile_1",
        profile_version=3,
        extraction_id="reqrun_1",
        eligibility=decision,
        requirements=requirements,
        matched_count=sum(item.status is RequirementFitStatus.MATCHED for item in requirements),
        conditional_count=sum(
            item.status is RequirementFitStatus.CONDITIONAL for item in requirements
        ),
        missing_count=sum(item.status is RequirementFitStatus.MISSING for item in requirements),
    )


class _EligibilityRunner:
    def __init__(self, result: JobEligibilityResult) -> None:
        self.result = result
        self.calls = 0

    def execute(self, job_id: str) -> JobEligibilityResult:
        assert job_id == "job_1"
        self.calls += 1
        return self.result


class _SemanticRunner:
    def __init__(self, result: JobSemanticMatchResult) -> None:
        self.result = result
        self.calls = 0

    def execute(self, job_id: str) -> JobSemanticMatchResult:
        assert job_id == "job_1"
        self.calls += 1
        return self.result


class _ReportRepository:
    def __init__(self) -> None:
        self.added = []

    def add(self, report):
        self.added.append(report)
        return None


class _ReportUnitOfWork:
    def __init__(self) -> None:
        self.reports = _ReportRepository()
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        return None


def test_match_report_persistence_gate_fails_before_semantic_provider_work() -> None:
    from app.application.match_report import (
        BuildJobMatchReportUseCase,
        MatchReportPersistenceNotReadyError,
    )

    runner = _SemanticRunner(
        _semantic(
            eligibility=EligibilityDecision.ELIGIBLE,
            assessments=(
                _assessment(
                    "req_rag",
                    0,
                    importance=RequirementImportance.MUST_HAVE,
                    verdict=SemanticMatchVerdict.MATCHED,
                ),
            ),
        )
    )

    use_case = BuildJobMatchReportUseCase(
        runner,
        persistence_ready=lambda: False,
        uow_factory=lambda: (_ for _ in ()).throw(AssertionError("must not open UoW")),
    )

    import pytest

    with pytest.raises(MatchReportPersistenceNotReadyError):
        use_case.execute("job_1")

    assert runner.calls == 0


def test_blocked_match_report_skips_semantic_provider_work() -> None:
    from app.application.match_report import BuildJobMatchReportUseCase, MatchRecommendation

    eligibility = _EligibilityRunner(
        _eligibility(
            decision=EligibilityDecision.BLOCKED,
            requirements=(
                RequirementEligibilityResult(
                    requirement_id="req_direct",
                    requirement_index=0,
                    type=RequirementType.SKILL,
                    importance=RequirementImportance.MUST_HAVE,
                    original_text="熟悉 React",
                    normalized_capability="React",
                    status=RequirementFitStatus.MATCHED,
                    evidence_ids=("ev_react",),
                    profile_fact_refs=("skill:react",),
                    reason="已有直接证据。",
                ),
                RequirementEligibilityResult(
                    requirement_id="req_missing",
                    requirement_index=1,
                    type=RequirementType.EXPERIENCE,
                    importance=RequirementImportance.MUST_HAVE,
                    original_text="5 年后端经验",
                    normalized_capability="Backend Development",
                    status=RequirementFitStatus.MISSING,
                    evidence_ids=(),
                    profile_fact_refs=(),
                    reason="当前没有足够专项年限证据。",
                ),
                RequirementEligibilityResult(
                    requirement_id="req_conditional",
                    requirement_index=2,
                    type=RequirementType.SKILL,
                    importance=RequirementImportance.PREFERRED,
                    original_text="熟悉 Agent 工程实践",
                    normalized_capability="Agent Engineering",
                    status=RequirementFitStatus.CONDITIONAL,
                    evidence_ids=(),
                    profile_fact_refs=(),
                    reason="需要语义判断。",
                ),
            ),
        )
    )
    semantic = _SemanticRunner(
        _semantic(
            eligibility=EligibilityDecision.BLOCKED,
            assessments=(
                _assessment(
                    "req_missing",
                    1,
                    importance=RequirementImportance.MUST_HAVE,
                    verdict=SemanticMatchVerdict.PARTIAL,
                    eligibility_status=RequirementFitStatus.MISSING,
                ),
            ),
        )
    )

    report = BuildJobMatchReportUseCase(
        semantic,
        eligibility=eligibility,
        persistence_ready=lambda: True,
    ).execute("job_1")

    assert eligibility.calls == 1
    assert semantic.calls == 0
    assert report.recommendation is MatchRecommendation.BLOCKED
    assert report.provider_calls == 0
    assert report.trace_runs_created == 0
    assert report.model is None
    assert report.trace_run_id is None
    assert report.matcher_version == "eligibility-only-v1"
    assert report.missing_requirement_ids == ("req_missing",)
    assert report.matched_requirement_ids == ("req_direct",)
    conditional = next(
        item for item in report.requirement_results if item.requirement_id == "req_conditional"
    )
    assert conditional.eligibility_status is RequirementFitStatus.CONDITIONAL
    assert "不再执行语义匹配" in conditional.reason


def test_match_report_runtime_persists_one_immutable_snapshot_when_schema_ready() -> None:
    from app.application.match_report import BuildJobMatchReportUseCase

    runner = _SemanticRunner(
        _semantic(
            eligibility=EligibilityDecision.ELIGIBLE,
            assessments=(
                _assessment(
                    "req_rag",
                    0,
                    importance=RequirementImportance.MUST_HAVE,
                    verdict=SemanticMatchVerdict.MATCHED,
                ),
            ),
        )
    )
    uow = _ReportUnitOfWork()
    use_case = BuildJobMatchReportUseCase(
        runner,
        persistence_ready=lambda: True,
        uow_factory=lambda: uow,
    )

    report = use_case.execute("job_1")

    assert runner.calls == 1
    assert report.db_writes == 1
    assert uow.committed is True
    assert uow.reports.added == [report]


def test_blocked_eligibility_can_never_be_upgraded_by_semantic_match() -> None:
    from app.application.match_report import MatchRecommendation, build_match_report

    report = build_match_report(
        _semantic(
            eligibility=EligibilityDecision.BLOCKED,
            assessments=(
                _assessment(
                    "req_mcp",
                    0,
                    importance=RequirementImportance.MUST_HAVE,
                    verdict=SemanticMatchVerdict.PARTIAL,
                    eligibility_status=RequirementFitStatus.MISSING,
                ),
            ),
        )
    )

    assert report.recommendation is MatchRecommendation.BLOCKED
    assert report.eligibility is EligibilityDecision.BLOCKED
    assert report.partial_requirement_ids == ("req_mcp",)
    assert report.missing_requirement_ids == ("req_mcp",)


def test_even_semantic_matched_cannot_upgrade_blocked_eligibility() -> None:
    from app.application.match_report import MatchRecommendation, build_match_report

    report = build_match_report(
        _semantic(
            eligibility=EligibilityDecision.BLOCKED,
            assessments=(
                _assessment(
                    "req_backend",
                    0,
                    importance=RequirementImportance.MUST_HAVE,
                    verdict=SemanticMatchVerdict.MATCHED,
                    eligibility_status=RequirementFitStatus.MISSING,
                ),
            ),
        )
    )

    assert report.recommendation is MatchRecommendation.BLOCKED
    assert report.missing_requirement_ids == ("req_backend",)
    assert report.matched_requirement_ids == ()
    assert report.strengths == ()
    assert report.requirement_results[0].semantic_verdict is SemanticMatchVerdict.MATCHED


def test_conditional_without_hard_missing_is_stretch() -> None:
    from app.application.match_report import MatchRecommendation, build_match_report

    report = build_match_report(
        _semantic(
            eligibility=EligibilityDecision.CONDITIONAL,
            assessments=(
                _assessment(
                    "req_office_ai",
                    0,
                    importance=RequirementImportance.MUST_HAVE,
                    verdict=SemanticMatchVerdict.PARTIAL,
                    eligibility_status=RequirementFitStatus.CONDITIONAL,
                ),
            ),
        )
    )

    assert report.recommendation is MatchRecommendation.STRETCH
    assert "挑战" in report.summary


def test_eligible_with_every_must_have_and_preferred_matched_is_strong() -> None:
    from app.application.match_report import MatchRecommendation, build_match_report

    report = build_match_report(
        _semantic(
            eligibility=EligibilityDecision.ELIGIBLE,
            assessments=(
                _assessment(
                    "req_rag",
                    0,
                    importance=RequirementImportance.MUST_HAVE,
                    verdict=SemanticMatchVerdict.MATCHED,
                ),
                _assessment(
                    "req_agent",
                    1,
                    importance=RequirementImportance.PREFERRED,
                    verdict=SemanticMatchVerdict.MATCHED,
                ),
                _assessment(
                    "req_langchain",
                    2,
                    importance=RequirementImportance.BONUS,
                    verdict=SemanticMatchVerdict.NOT_MATCHED,
                ),
            ),
        )
    )

    assert report.recommendation is MatchRecommendation.STRONG
    assert report.matched_requirement_ids == ("req_rag", "req_agent")
    assert [item.requirement_id for item in report.strengths] == ["req_rag", "req_agent"]


def test_eligible_with_preferred_gap_is_good() -> None:
    from app.application.match_report import MatchRecommendation, build_match_report

    report = build_match_report(
        _semantic(
            eligibility=EligibilityDecision.ELIGIBLE,
            assessments=(
                _assessment(
                    "req_rag",
                    0,
                    importance=RequirementImportance.MUST_HAVE,
                    verdict=SemanticMatchVerdict.MATCHED,
                ),
                _assessment(
                    "req_mcp",
                    1,
                    importance=RequirementImportance.PREFERRED,
                    verdict=SemanticMatchVerdict.PARTIAL,
                ),
            ),
        )
    )

    assert report.recommendation is MatchRecommendation.GOOD
    assert report.partial_requirement_ids == ("req_mcp",)
    assert [item.requirement_id for item in report.risks] == ["req_mcp"]


def test_eligible_without_must_have_and_with_no_matched_core_preference_is_low() -> None:
    from app.application.match_report import MatchRecommendation, build_match_report

    report = build_match_report(
        _semantic(
            eligibility=EligibilityDecision.ELIGIBLE,
            assessments=(
                _assessment(
                    "req_domain",
                    0,
                    importance=RequirementImportance.PREFERRED,
                    verdict=SemanticMatchVerdict.NOT_MATCHED,
                ),
                _assessment(
                    "req_bonus",
                    1,
                    importance=RequirementImportance.BONUS,
                    verdict=SemanticMatchVerdict.MATCHED,
                ),
            ),
        )
    )

    assert report.recommendation is MatchRecommendation.LOW


def test_bonus_gap_does_not_surface_as_a_primary_risk() -> None:
    from app.application.match_report import build_match_report

    report = build_match_report(
        _semantic(
            eligibility=EligibilityDecision.ELIGIBLE,
            assessments=(
                _assessment(
                    "req_rag",
                    0,
                    importance=RequirementImportance.MUST_HAVE,
                    verdict=SemanticMatchVerdict.MATCHED,
                ),
                _assessment(
                    "req_autogpt",
                    1,
                    importance=RequirementImportance.BONUS,
                    verdict=SemanticMatchVerdict.NOT_MATCHED,
                ),
            ),
        )
    )

    assert report.risks == ()


def test_match_report_evidence_links_only_reference_semantic_assessment_evidence() -> None:
    from app.application.match_report import build_match_report

    report = build_match_report(
        _semantic(
            eligibility=EligibilityDecision.ELIGIBLE,
            assessments=(
                _assessment(
                    "req_rag",
                    0,
                    importance=RequirementImportance.MUST_HAVE,
                    verdict=SemanticMatchVerdict.MATCHED,
                    evidence_ids=("ev_rag", "ev_agent"),
                ),
            ),
        )
    )

    assert report.evidence_links[0].requirement_id == "req_rag"
    assert report.evidence_links[0].evidence_ids == ("ev_rag", "ev_agent")
    assert report.db_writes == 0
    assert report.provider_calls == 1
    assert report.trace_runs_created == 1
