"""Read-only TargetCohort aggregation over released JobRequirement facts."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

from app.application.job_requirements import (
    JobRequirementDetail,
    JobRequirementExtractionDetail,
)
from app.application.target_cohort_requirement_aggregation import (
    AggregateTargetCohortRequirementsUseCase,
)
from app.domain.job_requirements import RequirementImportance, RequirementType
from app.domain.target_cohort import TargetCohortSelectionSource, TargetCohortSnapshot


def _cohort() -> TargetCohortSnapshot:
    return TargetCohortSnapshot.create(
        cohort_id="cohort_1",
        name="Agent roles",
        selection_source=TargetCohortSelectionSource.MANUAL,
        job_ids=("job_2", "job_1"),
    )


def _requirement(
    requirement_id: str,
    *,
    job_id: str,
    extraction_id: str,
    capability: str,
    importance: RequirementImportance,
) -> JobRequirementDetail:
    return JobRequirementDetail(
        id=requirement_id,
        job_id=job_id,
        extraction_id=extraction_id,
        requirement_index=0,
        type=RequirementType.SKILL,
        original_text=f"Need {capability}",
        normalized_capability=capability,
        importance=importance,
        evidence_span=f"Need {capability}",
        confidence=0.95,
        extractor_version="requirement-extractor-v3",
    )


def _extraction(job_id: str, extraction_id: str, requirement: JobRequirementDetail) -> JobRequirementExtractionDetail:
    return JobRequirementExtractionDetail(
        extraction_id=extraction_id,
        job_id=job_id,
        input_hash=f"hash-{job_id}",
        extractor_version="requirement-extractor-v3",
        provider="provider",
        model="model",
        prompt_version="prompt-v3",
        trace_run_id=f"trace-{job_id}",
        requirement_count=1,
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
        requirements=(requirement,),
    )


class _ReleaseGate:
    def __init__(self, readiness_by_job: dict[str, object]) -> None:
        self.readiness_by_job = readiness_by_job
        self.calls: list[str] = []

    def execute(self, job_id: str):
        self.calls.append(job_id)
        return self.readiness_by_job[job_id]


class _Requirements:
    def __init__(self, extractions: dict[str, JobRequirementExtractionDetail | None]) -> None:
        self.extractions = extractions
        self.calls: list[str] = []

    def get_latest(self, job_id: str) -> JobRequirementExtractionDetail | None:
        self.calls.append(job_id)
        return self.extractions.get(job_id)


def _ready(job_id: str, extraction_id: str):
    return SimpleNamespace(
        job_id=job_id,
        release_eligible=True,
        extraction_id=extraction_id,
        blockers=(),
    )


def test_aggregates_only_released_requirement_facts_in_cohort_order() -> None:
    req_2 = _requirement(
        "req_2",
        job_id="job_2",
        extraction_id="ext_2",
        capability="FastAPI",
        importance=RequirementImportance.MUST_HAVE,
    )
    req_1 = _requirement(
        "req_1",
        job_id="job_1",
        extraction_id="ext_1",
        capability="React",
        importance=RequirementImportance.PREFERRED,
    )
    gate = _ReleaseGate({"job_2": _ready("job_2", "ext_2"), "job_1": _ready("job_1", "ext_1")})
    requirements = _Requirements(
        {
            "job_2": _extraction("job_2", "ext_2", req_2),
            "job_1": _extraction("job_1", "ext_1", req_1),
        }
    )

    result = AggregateTargetCohortRequirementsUseCase(
        release_gate=gate,
        requirements=requirements,
    ).execute(_cohort())

    assert result.facts_usable is True
    assert result.cohort_id == "cohort_1"
    assert result.job_ids == ("job_2", "job_1")
    assert [(item.job_id, item.extraction_id) for item in result.sources] == [
        ("job_2", "ext_2"),
        ("job_1", "ext_1"),
    ]
    assert [item.requirement_id for item in result.requirements] == ["req_2", "req_1"]
    assert [item.normalized_capability for item in result.requirements] == ["FastAPI", "React"]
    assert result.blockers == ()
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0


def test_any_unreleased_job_blocks_the_entire_cohort_before_requirement_reads() -> None:
    blocked = SimpleNamespace(
        job_id="job_1",
        release_eligible=False,
        extraction_id="ext_1",
        blockers=(SimpleNamespace(code="accepted_baseline_missing"),),
    )
    gate = _ReleaseGate({"job_2": _ready("job_2", "ext_2"), "job_1": blocked})
    requirements = _Requirements({})

    result = AggregateTargetCohortRequirementsUseCase(
        release_gate=gate,
        requirements=requirements,
    ).execute(_cohort())

    assert result.facts_usable is False
    assert result.requirements == ()
    assert requirements.calls == []
    assert [(item.job_id, item.codes) for item in result.blockers] == [
        ("job_1", ("accepted_baseline_missing",)),
    ]


def test_extraction_identity_change_after_release_check_fails_closed() -> None:
    req = _requirement(
        "req_2",
        job_id="job_2",
        extraction_id="ext_new",
        capability="FastAPI",
        importance=RequirementImportance.MUST_HAVE,
    )
    changed = _extraction("job_2", "ext_new", req)
    stable_req = replace(req, id="req_1", job_id="job_1", extraction_id="ext_1")
    gate = _ReleaseGate({"job_2": _ready("job_2", "ext_old"), "job_1": _ready("job_1", "ext_1")})
    requirements = _Requirements(
        {
            "job_2": changed,
            "job_1": _extraction("job_1", "ext_1", stable_req),
        }
    )

    result = AggregateTargetCohortRequirementsUseCase(
        release_gate=gate,
        requirements=requirements,
    ).execute(_cohort())

    assert result.facts_usable is False
    assert result.requirements == ()
    assert [(item.job_id, item.codes) for item in result.blockers] == [
        ("job_2", ("release_identity_changed",)),
    ]
