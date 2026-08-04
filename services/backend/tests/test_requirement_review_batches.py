"""Persistence and policy tests for Requirement manual review batches."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.requirement_reviews import (
    AcceptedRequirementReviewBaselineNotFoundError,
    InvalidRequirementCaseReviewError,
    InvalidRequirementReviewBatchError,
    InvalidRequirementReviewBatchFinalDecisionError,
    RequirementReviewBatchFinalDecision,
    RequirementReviewBatchFinalDecisionAlreadyExistsError,
    RequirementReviewCaseAlreadyReviewedError,
    RequirementReviewDecision,
    RequirementReviewIssueCode,
)
from app.application.requirement_reviews.use_cases import (
    CreateRequirementReviewBatchUseCase,
    FinalizeRequirementReviewBatchUseCase,
    GetAcceptedRequirementReviewBaselineUseCase,
    ReviewRequirementBatchCaseUseCase,
)
from app.db.base import Base
from app.db.models import (
    JobORM,
    JobRequirementExtractionORM,
    JobRequirementORM,
    RequirementReviewBatchFinalDecisionORM,
    RequirementReviewBatchORM,
    RequirementReviewCaseReviewORM,
    TraceSpanORM,
)
from app.repositories import (
    SqlAlchemyRequirementReviewQueryRepository,
    SqlAlchemyRequirementReviewUnitOfWork,
)


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'requirement-reviews.db'}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed_extraction(
    factory: sessionmaker[Session],
    *,
    index: int,
    version: int = 1,
    provider: str = "openai",
    model: str = "quality-model",
    prompt_version: str = "requirement-extraction-v1",
    created_at: datetime | None = None,
) -> tuple[str, str]:
    job_id = f"job_review_{index}"
    extraction_id = f"reqrun_review_{index}_{version}"
    trace_id = f"run_review_{index}_{version}"
    created_at = created_at or datetime(2026, 8, 3, 10, index % 60, tzinfo=timezone.utc)
    description = (
        f"岗位 {index} 需要 Python、FastAPI 和 Agent 工程经验，"
        "负责构建可追溯的 AI 应用。"
    )
    with factory() as session:
        job = session.get(JobORM, job_id)
        if job is None:
            job = JobORM(
                id=job_id,
                canonical_key=f"review:v1:{index}",
                title=f"AI Engineer {index}",
                company=f"Company {index}",
                description=description,
                skills=["Python", "FastAPI", "Agent"],
            )
            session.add(job)
        session.add(
            TraceSpanORM(
                id=trace_id,
                capability="requirement_extraction",
                version="requirement-extractor-v1",
                model=model,
                prompt_version=prompt_version,
                input_refs={"jobId": job_id, "descriptionSha256": f"hash-{index}-{version}"},
                output={"requirements": [{"normalizedCapability": "Python"}]},
                latency_ms=10,
                input_tokens=20,
                output_tokens=10,
                error=None,
                created_at=created_at,
            )
        )
        session.flush()
        extraction = JobRequirementExtractionORM(
            id=extraction_id,
            job_id=job_id,
            input_hash=sha256(description.encode("utf-8")).hexdigest(),
            description_characters=80,
            extractor_version="requirement-extractor-v1",
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            trace_run_id=trace_id,
            requirement_count=1,
            created_at=created_at,
        )
        extraction.requirements.append(
            JobRequirementORM(
                id=f"req_review_{index}_{version}",
                job_id=job_id,
                requirement_index=0,
                type="skill",
                original_text="需要 Python、FastAPI 和 Agent 工程经验",
                normalized_capability="Python",
                importance="must_have",
                evidence_span="需要 Python、FastAPI 和 Agent 工程经验",
                confidence=0.95,
                extractor_version="requirement-extractor-v1",
                created_at=created_at,
            )
        )
        session.add(extraction)
        session.commit()
    return job_id, extraction_id


def _create_use_case(factory: sessionmaker[Session]) -> CreateRequirementReviewBatchUseCase:
    return CreateRequirementReviewBatchUseCase(
        SqlAlchemyRequirementReviewQueryRepository(factory),
        lambda: SqlAlchemyRequirementReviewUnitOfWork(factory),
    )


def _review_use_case(factory: sessionmaker[Session]) -> ReviewRequirementBatchCaseUseCase:
    return ReviewRequirementBatchCaseUseCase(
        SqlAlchemyRequirementReviewQueryRepository(factory),
        lambda: SqlAlchemyRequirementReviewUnitOfWork(factory),
    )


def _finalize_use_case(
    factory: sessionmaker[Session],
) -> FinalizeRequirementReviewBatchUseCase:
    return FinalizeRequirementReviewBatchUseCase(
        SqlAlchemyRequirementReviewQueryRepository(factory),
        lambda: SqlAlchemyRequirementReviewUnitOfWork(factory),
    )


def _complete_formal_batch(
    factory: sessionmaker[Session],
    *,
    start_index: int,
    rejected_indexes: set[int] | None = None,
):
    rejected_indexes = rejected_indexes or set()
    extraction_ids = tuple(
        _seed_extraction(factory, index=start_index + index)[1]
        for index in range(20)
    )
    batch = _create_use_case(factory).execute(
        title=f"Formal batch {start_index}",
        reviewer="will",
        extraction_ids=extraction_ids,
    )
    review_use_case = _review_use_case(factory)
    for index, case in enumerate(batch.cases):
        rejected = index in rejected_indexes
        review_use_case.execute(
            batch_id=batch.summary.id,
            case_id=case.id,
            decision=(
                RequirementReviewDecision.REJECTED
                if rejected
                else RequirementReviewDecision.ACCEPTED
            ),
            issue_codes=(
                (RequirementReviewIssueCode.MISSING_REQUIREMENT,)
                if rejected
                else ()
            ),
            notes=(
                f"Reviewed {case.job_id}; the extraction omits one grounded requirement."
                if rejected
                else f"Reviewed {case.job_id}; the extraction is grounded in the frozen JD."
            ),
        )
    detail = SqlAlchemyRequirementReviewQueryRepository(factory).get_batch(
        batch.summary.id
    )
    assert detail is not None
    assert detail.summary.formal_evidence_eligible is True
    return detail


def test_candidate_list_returns_only_latest_extraction_per_job(
    session_factory: sessionmaker[Session],
) -> None:
    job_id, old_id = _seed_extraction(session_factory, index=1, version=1)
    _job_id, latest_id = _seed_extraction(
        session_factory,
        index=1,
        version=2,
        created_at=datetime(2026, 8, 3, 11, 0, tzinfo=timezone.utc),
    )

    page = SqlAlchemyRequirementReviewQueryRepository(session_factory).list_candidates(
        limit=50,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].job_id == job_id
    assert page.items[0].extraction_id == latest_id
    assert page.items[0].extraction_id != old_id


def test_changed_job_description_immediately_stales_existing_extraction_and_batch(
    session_factory: sessionmaker[Session],
) -> None:
    _job_id, extraction_id = _seed_extraction(session_factory, index=7)
    batch = _create_use_case(session_factory).execute(
        title="description snapshot",
        reviewer="will",
        extraction_ids=(extraction_id,),
    )

    with session_factory() as session:
        job = session.get(JobORM, "job_review_7")
        assert job is not None
        job.description = (job.description or "") + " 新增必须掌握生产级可观测性。"
        session.commit()

    repository = SqlAlchemyRequirementReviewQueryRepository(session_factory)
    candidates = repository.list_candidates(limit=50, offset=0)
    stale_batch = repository.get_batch(batch.summary.id)

    assert candidates.total == 0
    assert stale_batch is not None
    assert stale_batch.summary.stale_case_count == 1
    assert stale_batch.cases[0].is_current is False
    with pytest.raises(InvalidRequirementReviewBatchError, match="latest"):
        _create_use_case(session_factory).execute(
            title="must not reuse stale input",
            reviewer="will",
            extraction_ids=(extraction_id,),
        )


def test_practice_batch_freezes_exact_versions_and_derives_progress(
    session_factory: sessionmaker[Session],
) -> None:
    extraction_ids = tuple(
        _seed_extraction(session_factory, index=index)[1]
        for index in range(2)
    )

    detail = _create_use_case(session_factory).execute(
        title="First manual Requirement review",
        reviewer="will",
        extraction_ids=extraction_ids,
    )

    assert detail.summary.sample_size == 2
    assert detail.summary.reviewed_count == 0
    assert detail.summary.completed is False
    assert detail.summary.formal_evidence_eligible is False
    assert [item.extraction_id for item in detail.cases] == list(extraction_ids)
    assert all(item.is_current for item in detail.cases)
    assert all(item.description and item.requirements for item in detail.cases)

    first_review = _review_use_case(session_factory).execute(
        batch_id=detail.summary.id,
        case_id=detail.cases[0].id,
        decision=RequirementReviewDecision.ACCEPTED,
        issue_codes=(),
        notes="JD and extracted Requirements are aligned for this practice case.",
    )
    second_review = _review_use_case(session_factory).execute(
        batch_id=detail.summary.id,
        case_id=detail.cases[1].id,
        decision=RequirementReviewDecision.REJECTED,
        issue_codes=(RequirementReviewIssueCode.WRONG_IMPORTANCE,),
        notes="The optional wording was incorrectly promoted to a must-have requirement.",
    )

    assert first_review.decision is RequirementReviewDecision.ACCEPTED
    assert second_review.issue_codes == (RequirementReviewIssueCode.WRONG_IMPORTANCE,)
    refreshed = SqlAlchemyRequirementReviewQueryRepository(session_factory).get_batch(
        detail.summary.id
    )
    assert refreshed is not None
    assert refreshed.summary.reviewed_count == 2
    assert refreshed.summary.accepted_count == 1
    assert refreshed.summary.rejected_count == 1
    assert refreshed.summary.completed is True
    assert refreshed.summary.formal_evidence_eligible is False
    assert refreshed.issue_code_counts == {"wrong_importance": 1}


def test_batch_rejects_duplicates_missing_stale_and_mixed_cohorts(
    session_factory: sessionmaker[Session],
) -> None:
    _job, first = _seed_extraction(session_factory, index=10, version=1)
    _job, latest = _seed_extraction(
        session_factory,
        index=10,
        version=2,
        created_at=datetime(2026, 8, 3, 12, 0, tzinfo=timezone.utc),
    )
    _job, other_model = _seed_extraction(
        session_factory,
        index=11,
        model="different-model",
    )
    use_case = _create_use_case(session_factory)

    with pytest.raises(InvalidRequirementReviewBatchError, match="duplicates"):
        use_case.execute(title="duplicate", reviewer="will", extraction_ids=(latest, latest))
    with pytest.raises(InvalidRequirementReviewBatchError, match="not found"):
        use_case.execute(title="missing", reviewer="will", extraction_ids=("reqrun_missing",))
    with pytest.raises(InvalidRequirementReviewBatchError, match="latest"):
        use_case.execute(title="stale", reviewer="will", extraction_ids=(first,))
    with pytest.raises(InvalidRequirementReviewBatchError, match="share provider"):
        use_case.execute(
            title="mixed",
            reviewer="will",
            extraction_ids=(latest, other_model),
        )

    with session_factory() as session:
        assert int(
            session.scalar(select(func.count()).select_from(RequirementReviewBatchORM))
            or 0
        ) == 0


def test_case_review_truth_table_and_duplicate_protection(
    session_factory: sessionmaker[Session],
) -> None:
    extraction_id = _seed_extraction(session_factory, index=20)[1]
    batch = _create_use_case(session_factory).execute(
        title="truth table",
        reviewer="will",
        extraction_ids=(extraction_id,),
    )
    case_id = batch.cases[0].id
    use_case = _review_use_case(session_factory)

    with pytest.raises(InvalidRequirementCaseReviewError, match="must not contain"):
        use_case.execute(
            batch_id=batch.summary.id,
            case_id=case_id,
            decision=RequirementReviewDecision.ACCEPTED,
            issue_codes=(RequirementReviewIssueCode.OTHER,),
            notes="Accepted output cannot carry an issue label in the same judgment.",
        )
    with pytest.raises(InvalidRequirementCaseReviewError, match="at least one"):
        use_case.execute(
            batch_id=batch.summary.id,
            case_id=case_id,
            decision=RequirementReviewDecision.REJECTED,
            issue_codes=(),
            notes="Rejected output must explain at least one structured issue category.",
        )

    use_case.execute(
        batch_id=batch.summary.id,
        case_id=case_id,
        decision=RequirementReviewDecision.REJECTED,
        issue_codes=(RequirementReviewIssueCode.MISSING_REQUIREMENT,),
        notes="The JD contains a responsibility that is absent from the extraction.",
    )
    with pytest.raises(RequirementReviewCaseAlreadyReviewedError):
        use_case.execute(
            batch_id=batch.summary.id,
            case_id=case_id,
            decision=RequirementReviewDecision.ACCEPTED,
            issue_codes=(),
            notes="An immutable case review must not be overwritten by a second request.",
        )


def test_twenty_complete_current_live_cases_are_formal_evidence_until_stale(
    session_factory: sessionmaker[Session],
) -> None:
    extraction_ids = tuple(
        _seed_extraction(session_factory, index=100 + index)[1]
        for index in range(20)
    )
    batch = _create_use_case(session_factory).execute(
        title="20-job live Requirement review",
        reviewer="will",
        extraction_ids=extraction_ids,
    )
    use_case = _review_use_case(session_factory)
    for case in batch.cases:
        use_case.execute(
            batch_id=batch.summary.id,
            case_id=case.id,
            decision=RequirementReviewDecision.ACCEPTED,
            issue_codes=(),
            notes=f"Reviewed {case.job_id} against its JD and frozen extraction evidence.",
        )

    repository = SqlAlchemyRequirementReviewQueryRepository(session_factory)
    completed = repository.get_batch(batch.summary.id)
    assert completed is not None
    assert completed.summary.reviewed_count == 20
    assert completed.summary.completed is True
    assert completed.summary.stale_case_count == 0
    assert completed.summary.formal_evidence_eligible is True

    _seed_extraction(
        session_factory,
        index=100,
        version=2,
        created_at=datetime(2026, 8, 4, 9, 0, tzinfo=timezone.utc),
    )
    stale = repository.get_batch(batch.summary.id)
    assert stale is not None
    assert stale.summary.stale_case_count == 1
    assert stale.summary.formal_evidence_eligible is False
    assert stale.cases[0].review is not None


def test_fixture_batch_never_becomes_formal_release_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    extraction_ids = tuple(
        _seed_extraction(session_factory, index=200 + index, provider="fixture")[1]
        for index in range(20)
    )
    batch = _create_use_case(session_factory).execute(
        title="fixture practice",
        reviewer="will",
        extraction_ids=extraction_ids,
    )
    for case in batch.cases:
        _review_use_case(session_factory).execute(
            batch_id=batch.summary.id,
            case_id=case.id,
            decision=RequirementReviewDecision.ACCEPTED,
            issue_codes=(),
            notes="Fixture output reviewed only to validate the manual review workflow.",
        )
    detail = SqlAlchemyRequirementReviewQueryRepository(session_factory).get_batch(
        batch.summary.id
    )
    assert detail is not None
    assert detail.summary.completed is True
    assert detail.summary.formal_evidence_eligible is False


def test_final_decision_requires_complete_current_live_evidence_and_owner(
    session_factory: sessionmaker[Session],
) -> None:
    extraction_id = _seed_extraction(session_factory, index=400)[1]
    batch = _create_use_case(session_factory).execute(
        title="incomplete final decision",
        reviewer="will",
        extraction_ids=(extraction_id,),
    )
    use_case = _finalize_use_case(session_factory)

    with pytest.raises(
        InvalidRequirementReviewBatchFinalDecisionError,
        match="exactly 20 reviewed",
    ):
        use_case.execute(
            batch_id=batch.summary.id,
            decision=RequirementReviewBatchFinalDecision.ACCEPT_FOR_MATCH,
            reviewer="will",
            notes="This incomplete practice evidence must not authorize Match.",
        )

    complete = _complete_formal_batch(session_factory, start_index=420)
    with pytest.raises(
        InvalidRequirementReviewBatchFinalDecisionError,
        match="must match",
    ):
        use_case.execute(
            batch_id=complete.summary.id,
            decision=RequirementReviewBatchFinalDecision.ACCEPT_FOR_MATCH,
            reviewer="another-reviewer",
            notes="A different reviewer must not finalize evidence owned by Will.",
        )

    with session_factory() as session:
        assert int(
            session.scalar(
                select(func.count()).select_from(
                    RequirementReviewBatchFinalDecisionORM
                )
            )
            or 0
        ) == 0


def test_human_acceptance_creates_immutable_current_match_baseline(
    session_factory: sessionmaker[Session],
) -> None:
    batch = _complete_formal_batch(
        session_factory,
        start_index=500,
        rejected_indexes={3},
    )
    decision = _finalize_use_case(session_factory).execute(
        batch_id=batch.summary.id,
        decision=RequirementReviewBatchFinalDecision.ACCEPT_FOR_MATCH,
        reviewer="will",
        notes=(
            "I reviewed all twenty frozen Jobs, Requirements and Trace evidence; "
            "the observed issue distribution is acceptable for the first Match slice."
        ),
    )

    assert decision.sample_size == 20
    assert decision.reviewed_count == 20
    assert decision.accepted_count == 19
    assert decision.rejected_count == 1
    assert decision.stale_case_count == 0
    assert decision.issue_code_counts == {"missing_requirement": 1}
    assert len(decision.evidence_fingerprint) == 64

    repository = SqlAlchemyRequirementReviewQueryRepository(session_factory)
    detail = repository.get_batch(batch.summary.id)
    assert detail is not None
    assert detail.final_decision is not None
    assert detail.summary.final_decision is (
        RequirementReviewBatchFinalDecision.ACCEPT_FOR_MATCH
    )
    assert detail.summary.match_release_eligible is True

    baseline = GetAcceptedRequirementReviewBaselineUseCase(repository).execute()
    assert baseline.batch.id == batch.summary.id
    assert baseline.batch.match_release_eligible is True
    assert baseline.decision.id == decision.id
    assert baseline.issue_code_counts == {"missing_requirement": 1}

    with pytest.raises(RequirementReviewBatchFinalDecisionAlreadyExistsError):
        _finalize_use_case(session_factory).execute(
            batch_id=batch.summary.id,
            decision=RequirementReviewBatchFinalDecision.REJECT_FOR_MATCH,
            reviewer="will",
            notes="A second decision must never overwrite the frozen acceptance history.",
        )


def test_rejected_final_decision_preserves_evidence_without_match_release(
    session_factory: sessionmaker[Session],
) -> None:
    batch = _complete_formal_batch(
        session_factory,
        start_index=540,
        rejected_indexes=set(range(20)),
    )
    decision = _finalize_use_case(session_factory).execute(
        batch_id=batch.summary.id,
        decision=RequirementReviewBatchFinalDecision.REJECT_FOR_MATCH,
        reviewer="will",
        notes=(
            "All twenty cases contain material grounded Requirement omissions, so this "
            "cohort must not become the Match fact baseline."
        ),
    )

    detail = SqlAlchemyRequirementReviewQueryRepository(session_factory).get_batch(
        batch.summary.id
    )
    assert detail is not None
    assert decision.rejected_count == 20
    assert detail.summary.formal_evidence_eligible is True
    assert detail.summary.final_decision is (
        RequirementReviewBatchFinalDecision.REJECT_FOR_MATCH
    )
    assert detail.summary.match_release_eligible is False
    with pytest.raises(AcceptedRequirementReviewBaselineNotFoundError):
        GetAcceptedRequirementReviewBaselineUseCase(
            SqlAlchemyRequirementReviewQueryRepository(session_factory)
        ).execute()


def test_newer_extraction_revokes_match_eligibility_but_keeps_final_history(
    session_factory: sessionmaker[Session],
) -> None:
    batch = _complete_formal_batch(session_factory, start_index=580)
    decision = _finalize_use_case(session_factory).execute(
        batch_id=batch.summary.id,
        decision=RequirementReviewBatchFinalDecision.ACCEPT_FOR_MATCH,
        reviewer="will",
        notes=(
            "All twenty frozen cases were reviewed and this cohort is accepted for the "
            "current Match fact baseline while those versions remain current."
        ),
    )

    _seed_extraction(
        session_factory,
        index=580,
        version=2,
        created_at=datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc),
    )
    repository = SqlAlchemyRequirementReviewQueryRepository(session_factory)
    stale = repository.get_batch(batch.summary.id)
    assert stale is not None
    assert stale.final_decision is not None
    assert stale.final_decision.id == decision.id
    assert stale.summary.formal_evidence_eligible is False
    assert stale.summary.match_release_eligible is False
    assert stale.summary.stale_case_count == 1
    with pytest.raises(AcceptedRequirementReviewBaselineNotFoundError):
        GetAcceptedRequirementReviewBaselineUseCase(repository).execute()


class FailingCommitRequirementReviewUnitOfWork(
    SqlAlchemyRequirementReviewUnitOfWork
):
    def commit(self) -> None:
        raise RuntimeError("simulated commit failure")


def test_failed_final_decision_commit_leaves_no_partial_decision(
    session_factory: sessionmaker[Session],
) -> None:
    batch = _complete_formal_batch(session_factory, start_index=620)
    use_case = FinalizeRequirementReviewBatchUseCase(
        SqlAlchemyRequirementReviewQueryRepository(session_factory),
        lambda: FailingCommitRequirementReviewUnitOfWork(session_factory),
    )

    with pytest.raises(RuntimeError, match="simulated commit failure"):
        use_case.execute(
            batch_id=batch.summary.id,
            decision=RequirementReviewBatchFinalDecision.ACCEPT_FOR_MATCH,
            reviewer="will",
            notes=(
                "This otherwise valid final decision must rollback when the transaction "
                "commit fails before durable persistence."
            ),
        )

    with session_factory() as session:
        assert int(
            session.scalar(
                select(func.count()).select_from(
                    RequirementReviewBatchFinalDecisionORM
                )
            )
            or 0
        ) == 0


def test_failed_review_commit_leaves_no_partial_review(
    session_factory: sessionmaker[Session],
) -> None:
    extraction_id = _seed_extraction(session_factory, index=300)[1]
    batch = _create_use_case(session_factory).execute(
        title="transaction failure",
        reviewer="will",
        extraction_ids=(extraction_id,),
    )
    use_case = ReviewRequirementBatchCaseUseCase(
        SqlAlchemyRequirementReviewQueryRepository(session_factory),
        lambda: FailingCommitRequirementReviewUnitOfWork(session_factory),
    )

    with pytest.raises(RuntimeError, match="simulated commit failure"):
        use_case.execute(
            batch_id=batch.summary.id,
            case_id=batch.cases[0].id,
            decision=RequirementReviewDecision.ACCEPTED,
            issue_codes=(),
            notes="The transaction must rollback this otherwise valid review judgment.",
        )

    with session_factory() as session:
        assert int(
            session.scalar(
                select(func.count()).select_from(RequirementReviewCaseReviewORM)
            )
            or 0
        ) == 0
