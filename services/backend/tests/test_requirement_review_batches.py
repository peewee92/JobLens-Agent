"""Persistence and policy tests for Requirement manual review batches."""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.requirement_reviews import (
    InvalidRequirementCaseReviewError,
    InvalidRequirementReviewBatchError,
    RequirementReviewCaseAlreadyReviewedError,
    RequirementReviewDecision,
    RequirementReviewIssueCode,
)
from app.application.requirement_reviews.use_cases import (
    CreateRequirementReviewBatchUseCase,
    ReviewRequirementBatchCaseUseCase,
)
from app.db.base import Base
from app.db.models import (
    JobORM,
    JobRequirementExtractionORM,
    JobRequirementORM,
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
    with factory() as session:
        job = session.get(JobORM, job_id)
        if job is None:
            job = JobORM(
                id=job_id,
                canonical_key=f"review:v1:{index}",
                title=f"AI Engineer {index}",
                company=f"Company {index}",
                description=(
                    f"岗位 {index} 需要 Python、FastAPI 和 Agent 工程经验，"
                    "负责构建可追溯的 AI 应用。"
                ),
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
            input_hash=f"{index:02d}{version:02d}".ljust(64, "0"),
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


class FailingCommitRequirementReviewUnitOfWork(
    SqlAlchemyRequirementReviewUnitOfWork
):
    def commit(self) -> None:
        raise RuntimeError("simulated commit failure")


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
