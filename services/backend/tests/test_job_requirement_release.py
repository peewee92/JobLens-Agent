"""Policy and adapter tests for Job Requirement fact release readiness."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.application.job_queries.errors import JobNotFoundError
from app.application.job_queries.models import JobDetail
from app.application.job_requirements.models import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
)
from app.application.job_requirements.release import (
    GetJobRequirementReleaseReadinessUseCase,
    JobRequirementReleaseBlockerCode,
)
from app.application.ports.job_requirement_release_repository import (
    JobRequirementTraceFact,
)
from app.application.requirement_reviews.models import (
    AcceptedRequirementReviewBaseline,
    RequirementReviewBatchFinalDecision,
    RequirementReviewBatchFinalDecisionDetail,
    RequirementReviewBatchSummary,
)
from app.db.base import Base
from app.db.models import TraceSpanORM
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.domain.jobs import RemoteConfidence, RemoteStatus
from app.repositories.sqlalchemy_job_requirement_release_repository import (
    SqlAlchemyJobRequirementReleaseQueryRepository,
)

NOW = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)
DESCRIPTION = "负责使用 Python 和 FastAPI 构建 Agent 工作流，并维护 Trace 与质量评测。"
DESCRIPTION_HASH = sha256(DESCRIPTION.encode("utf-8")).hexdigest()


class FakeJobs:
    def __init__(self, job: JobDetail | None) -> None:
        self.job = job

    def get_job(self, job_id: str) -> JobDetail | None:
        return self.job if self.job is not None and self.job.id == job_id else None


class FakeRequirements:
    def __init__(self, extraction: JobRequirementExtractionDetail | None) -> None:
        self.extraction = extraction

    def get_latest(self, job_id: str) -> JobRequirementExtractionDetail | None:
        return (
            self.extraction
            if self.extraction is not None and self.extraction.job_id == job_id
            else None
        )


class FakeReviews:
    def __init__(self, baseline: AcceptedRequirementReviewBaseline | None) -> None:
        self.baseline = baseline

    def get_accepted_baseline(self) -> AcceptedRequirementReviewBaseline | None:
        return self.baseline


class FakeTraces:
    def __init__(self, trace: JobRequirementTraceFact | None) -> None:
        self.trace = trace

    def get_trace(self, trace_run_id: str) -> JobRequirementTraceFact | None:
        return (
            self.trace
            if self.trace is not None and self.trace.trace_run_id == trace_run_id
            else None
        )


def _job(*, description: str | None = DESCRIPTION) -> JobDetail:
    return JobDetail(
        id="job_release_1",
        title="Agent Engineer",
        company="Example",
        area="武汉",
        salary_min_k=20,
        salary_max_k=30,
        experience="3-5年",
        education="本科",
        description=description,
        skills=("Python", "FastAPI"),
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
        source="boss",
        source_url="https://example.test/job/1",
        source_version="1.4.6",
        description_quality="complete",
        requirement_review_eligible=True,
        requirement_review_ineligibility_reasons=(),
        collected_at=NOW,
    )


def _requirement() -> JobRequirementDetail:
    return JobRequirementDetail(
        id="req_release_1",
        job_id="job_release_1",
        extraction_id="reqrun_release_1",
        requirement_index=0,
        type=RequirementType.SKILL,
        original_text="使用 Python 和 FastAPI 构建 Agent 工作流",
        normalized_capability="Python",
        importance=RequirementImportance.MUST_HAVE,
        evidence_span="使用 Python 和 FastAPI 构建 Agent 工作流",
        confidence=0.95,
        extractor_version="requirement-extractor-v1",
    )


def _extraction(**overrides) -> JobRequirementExtractionDetail:
    values = {
        "extraction_id": "reqrun_release_1",
        "job_id": "job_release_1",
        "input_hash": DESCRIPTION_HASH,
        "extractor_version": "requirement-extractor-v1",
        "provider": "openai",
        "model": "quality-model",
        "prompt_version": "requirement-extraction-v1",
        "trace_run_id": "run_release_1",
        "requirement_count": 1,
        "created_at": NOW,
        "requirements": (_requirement(),),
        "semantic_policy_version": "requirement-semantics-v1",
    }
    values.update(overrides)
    return JobRequirementExtractionDetail(**values)


def _baseline(**batch_overrides) -> AcceptedRequirementReviewBaseline:
    batch_values = {
        "id": "reqreviewbatch_release_1",
        "title": "Accepted Requirement quality baseline",
        "reviewer": "will",
        "provider": "openai",
        "model": "quality-model",
        "extractor_version": "requirement-extractor-v1",
        "prompt_version": "requirement-extraction-v1",
        "sample_size": 20,
        "reviewed_count": 20,
        "accepted_count": 19,
        "rejected_count": 1,
        "stale_case_count": 0,
        "completed": True,
        "formal_evidence_eligible": True,
        "final_decision": RequirementReviewBatchFinalDecision.ACCEPT_FOR_MATCH,
        "match_release_eligible": True,
        "created_at": NOW,
        "semantic_policy_version": "requirement-semantics-v1",
    }
    batch_values.update(batch_overrides)
    decision = RequirementReviewBatchFinalDecisionDetail(
        id="reqbatchdecision_release_1",
        batch_id=batch_values["id"],
        decision=RequirementReviewBatchFinalDecision.ACCEPT_FOR_MATCH,
        reviewer="will",
        notes="The frozen evidence is acceptable for controlled Match use.",
        sample_size=20,
        reviewed_count=20,
        accepted_count=19,
        rejected_count=1,
        stale_case_count=0,
        issue_code_counts={"wrong_normalization": 1},
        evidence_fingerprint="a" * 64,
        decided_at=NOW,
    )
    return AcceptedRequirementReviewBaseline(
        decision=decision,
        batch=RequirementReviewBatchSummary(**batch_values),
        issue_code_counts={"wrong_normalization": 1},
    )


def _trace(**overrides) -> JobRequirementTraceFact:
    values = {
        "trace_run_id": "run_release_1",
        "capability": "requirement_extraction",
        "version": "requirement-extractor-v1",
        "model": "quality-model",
        "prompt_version": "requirement-extraction-v1",
        "input_refs": {
            "jobId": "job_release_1",
            "descriptionSha256": DESCRIPTION_HASH,
        },
        "output": {
            "requirements": [
                {
                    "type": "skill",
                    "originalText": "使用 Python 和 FastAPI 构建 Agent 工作流",
                    "normalizedCapability": "Python",
                    "importance": "must_have",
                    "evidenceSpan": "使用 Python 和 FastAPI 构建 Agent 工作流",
                    "confidence": 0.95,
                }
            ]
        },
        "error": None,
    }
    values.update(overrides)
    return JobRequirementTraceFact(**values)


def _execute(
    *,
    job: JobDetail | None = None,
    extraction: JobRequirementExtractionDetail | None = None,
    baseline: AcceptedRequirementReviewBaseline | None = None,
    trace: JobRequirementTraceFact | None = None,
):
    return GetJobRequirementReleaseReadinessUseCase(
        jobs=FakeJobs(_job() if job is None else job),
        requirements=FakeRequirements(_extraction() if extraction is None else extraction),
        reviews=FakeReviews(_baseline() if baseline is None else baseline),
        traces=FakeTraces(_trace() if trace is None else trace),
    ).execute("job_release_1")


def _codes(result) -> set[JobRequirementReleaseBlockerCode]:
    return {item.code for item in result.blockers}


def test_complete_current_accepted_cohort_is_released() -> None:
    result = _execute()

    assert result.release_eligible is True
    assert result.blockers == ()
    assert result.extraction_id == "reqrun_release_1"
    assert result.accepted_baseline_batch_id == "reqreviewbatch_release_1"
    assert result.accepted_baseline_decision_id == "reqbatchdecision_release_1"
    assert result.accepted_baseline_evidence_fingerprint == "a" * 64


def test_frozen_mvp_extraction_can_release_for_match_without_human_baseline() -> None:
    extraction = _extraction(extractor_version="requirement-extractor-v42.95")
    trace = _trace(version="requirement-extractor-v42.95")
    use_case = GetJobRequirementReleaseReadinessUseCase(
        jobs=FakeJobs(_job()),
        requirements=FakeRequirements(extraction),
        reviews=FakeReviews(None),
        traces=FakeTraces(trace),
        allow_frozen_mvp_without_baseline=True,
    )

    result = use_case.execute("job_release_1")

    assert result.release_eligible is True
    assert result.blockers == ()
    assert result.accepted_baseline_batch_id is None


def test_new_extractor_stays_blocked_without_human_accepted_baseline() -> None:
    use_case = GetJobRequirementReleaseReadinessUseCase(
        jobs=FakeJobs(_job()),
        requirements=FakeRequirements(_extraction(extractor_version="requirement-extractor-v42.96")),
        reviews=FakeReviews(None),
        traces=FakeTraces(_trace(version="requirement-extractor-v42.96")),
        allow_frozen_mvp_without_baseline=True,
    )

    result = use_case.execute("job_release_1")

    assert result.release_eligible is False
    assert _codes(result) == {
        JobRequirementReleaseBlockerCode.ACCEPTED_BASELINE_MISSING,
    }


def test_old_extraction_stays_blocked_without_human_baseline_in_mvp_mode() -> None:
    use_case = GetJobRequirementReleaseReadinessUseCase(
        jobs=FakeJobs(_job()),
        requirements=FakeRequirements(_extraction(extractor_version="requirement-extractor-v42.94")),
        reviews=FakeReviews(None),
        traces=FakeTraces(_trace(version="requirement-extractor-v42.94")),
        allow_frozen_mvp_without_baseline=True,
    )

    result = use_case.execute("job_release_1")

    assert result.release_eligible is False
    assert _codes(result) == {
        JobRequirementReleaseBlockerCode.ACCEPTED_BASELINE_MISSING,
    }


def test_missing_baseline_and_extraction_are_explicit_fail_closed_blockers() -> None:
    use_case = GetJobRequirementReleaseReadinessUseCase(
        jobs=FakeJobs(_job()),
        requirements=FakeRequirements(None),
        reviews=FakeReviews(None),
        traces=FakeTraces(None),
    )

    result = use_case.execute("job_release_1")

    assert result.release_eligible is False
    assert _codes(result) == {
        JobRequirementReleaseBlockerCode.ACCEPTED_BASELINE_MISSING,
        JobRequirementReleaseBlockerCode.EXTRACTION_MISSING,
    }
    assert result.trace_run_id is None


def test_semantic_policy_mismatch_with_accepted_baseline_does_not_release() -> None:
    result = _execute(
        extraction=_extraction(semantic_policy_version="requirement-semantics-v2"),
        baseline=_baseline(semantic_policy_version="requirement-semantics-v1"),
    )

    assert result.release_eligible is False
    assert _codes(result) == {
        JobRequirementReleaseBlockerCode.EXTRACTION_COHORT_MISMATCH,
    }


def test_stale_input_and_unaccepted_cohort_do_not_release() -> None:
    result = _execute(
        job=_job(description=DESCRIPTION + " 新增必须具备生产事故排查经验。"),
        baseline=_baseline(model="other-model"),
    )

    assert result.release_eligible is False
    assert _codes(result) == {
        JobRequirementReleaseBlockerCode.EXTRACTION_INPUT_STALE,
        JobRequirementReleaseBlockerCode.EXTRACTION_COHORT_MISMATCH,
    }


def test_empty_and_inconsistent_requirement_counts_do_not_release() -> None:
    result = _execute(extraction=_extraction(requirement_count=1, requirements=()))

    assert result.release_eligible is False
    assert _codes(result) == {
        JobRequirementReleaseBlockerCode.REQUIREMENTS_EMPTY,
        JobRequirementReleaseBlockerCode.REQUIREMENT_COUNT_MISMATCH,
        JobRequirementReleaseBlockerCode.TRACE_OUTPUT_MISMATCH,
    }


def test_missing_or_failed_trace_does_not_release() -> None:
    missing = GetJobRequirementReleaseReadinessUseCase(
        jobs=FakeJobs(_job()),
        requirements=FakeRequirements(_extraction()),
        reviews=FakeReviews(_baseline()),
        traces=FakeTraces(None),
    ).execute("job_release_1")
    failed = _execute(trace=_trace(error="provider timeout"))

    assert _codes(missing) == {JobRequirementReleaseBlockerCode.TRACE_MISSING}
    assert _codes(failed) == {JobRequirementReleaseBlockerCode.TRACE_FAILED}


def test_same_count_but_different_trace_requirement_content_does_not_release() -> None:
    result = _execute(
        trace=_trace(
            output={
                "requirements": [
                    {
                        "type": "skill",
                        "originalText": "必须掌握 Rust",
                        "normalizedCapability": "Rust",
                        "importance": "must_have",
                        "evidenceSpan": "必须掌握 Rust",
                        "confidence": 0.95,
                    }
                ]
            }
        )
    )

    assert _codes(result) == {
        JobRequirementReleaseBlockerCode.TRACE_OUTPUT_MISMATCH
    }



def test_trace_identity_cohort_input_and_output_must_match() -> None:
    result = _execute(
        trace=_trace(
            capability="profile_extraction",
            version="wrong-version",
            model="wrong-model",
            prompt_version="wrong-prompt",
            input_refs={"jobId": "job_other", "descriptionSha256": "bad"},
            output={"requirements": []},
        )
    )

    assert result.release_eligible is False
    assert _codes(result) == {
        JobRequirementReleaseBlockerCode.TRACE_CAPABILITY_MISMATCH,
        JobRequirementReleaseBlockerCode.TRACE_COHORT_MISMATCH,
        JobRequirementReleaseBlockerCode.TRACE_INPUT_MISMATCH,
        JobRequirementReleaseBlockerCode.TRACE_OUTPUT_MISMATCH,
    }


def test_missing_job_is_404_semantics_not_a_readiness_blocker() -> None:
    use_case = GetJobRequirementReleaseReadinessUseCase(
        jobs=FakeJobs(None),
        requirements=FakeRequirements(None),
        reviews=FakeReviews(None),
        traces=FakeTraces(None),
    )

    with pytest.raises(JobNotFoundError):
        use_case.execute("job_release_1")


def test_sqlalchemy_trace_adapter_returns_immutable_trace_fact(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'release-trace.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            TraceSpanORM(
                id="run_release_1",
                capability="requirement_extraction",
                version="requirement-extractor-v1",
                model="quality-model",
                prompt_version="requirement-extraction-v1",
                input_refs={"jobId": "job_release_1", "descriptionSha256": DESCRIPTION_HASH},
                output={"requirements": [{"normalizedCapability": "Python"}]},
                latency_ms=10,
                input_tokens=20,
                output_tokens=10,
                error=None,
                created_at=NOW,
            )
        )
        session.commit()

    repository = SqlAlchemyJobRequirementReleaseQueryRepository(factory)
    fact = repository.get_trace("run_release_1")

    assert fact is not None
    assert fact.input_refs["descriptionSha256"] == DESCRIPTION_HASH
    assert fact.output == {"requirements": [{"normalizedCapability": "Python"}]}
    assert repository.get_trace("run_missing") is None
    Base.metadata.drop_all(engine)
    engine.dispose()
