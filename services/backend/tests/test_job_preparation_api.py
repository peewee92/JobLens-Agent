"""HTTP contract tests for the read-only Phase 7 Job Preparation bundle."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_job_preparation_bundle_use_case
from app.application.job_preparation.bundle import JobPreparationBundle
from app.application.job_preparation.experience_priority import ExperiencePriorityFacts
from app.application.job_preparation.interview_question_facts import InterviewQuestionFacts
from app.application.job_preparation.resume_delta import ResumeDeltaFacts
from app.application.job_preparation.story_facts import StoryFactSelection
from app.application.job_preparation.study_checklist import StudyChecklistFacts
from app.main import app


class _UseCase:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, job_id: str) -> JobPreparationBundle:
        self.calls.append(job_id)
        identity = {
            "job_id": job_id,
            "facts_usable": True,
            "profile_id": "prof_1",
            "profile_version": 3,
            "extraction_id": "extract_1",
            "blockers": (),
        }
        return JobPreparationBundle(
            **identity,
            resume_delta=ResumeDeltaFacts(highlights=(), evidence_gaps=(), **identity),
            experience_priority=ExperiencePriorityFacts(items=(), **identity),
            story_facts=StoryFactSelection(items=(), **identity),
            interview_facts=InterviewQuestionFacts(items=(), **identity),
            study_checklist=StudyChecklistFacts(items=(), **identity),
        )


def test_job_preparation_api_exposes_all_five_read_only_fact_sections() -> None:
    use_case = _UseCase()
    app.dependency_overrides[get_job_preparation_bundle_use_case] = lambda: use_case
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/job-preparation/job_1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["jobId"] == "job_1"
    assert body["factsUsable"] is True
    assert body["profileId"] == "prof_1"
    assert body["profileVersion"] == 3
    assert body["extractionId"] == "extract_1"
    assert body["resumeDelta"] == {"highlights": [], "evidenceGaps": []}
    assert body["experiencePriority"] == {"items": []}
    assert body["storyFacts"] == {"items": []}
    assert body["interviewFacts"] == {"items": []}
    assert body["studyChecklist"] == {"items": []}
    assert body["blockers"] == []
    assert body["dbWrites"] == body["providerCalls"] == body["traceRunsCreated"] == 0
    assert use_case.calls == ["job_1"]


def test_openapi_registers_job_preparation_get_contract() -> None:
    with TestClient(app) as client:
        operation = client.get("/openapi.json").json()["paths"][
            "/api/v1/job-preparation/{job_id}"
        ]["get"]

    assert "200" in operation["responses"]
