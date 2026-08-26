from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.application.career_context.models import SearchIntentDetail
from app.application.eligibility import EligibilityDecision
from app.application.job_queries.models import JobListItem, JobPage
from app.application.match_report import MatchRecommendation, MatchReport, StoredMatchReport
from app.application.recommendation_coverage import BuildRecommendationCoverageUseCase
from app.domain.jobs import RemoteConfidence, RemoteStatus


def _job(job_id: str, title: str, *, area: str = "武汉", salary_min: float = 15) -> JobListItem:
    return JobListItem(
        id=job_id,
        title=title,
        company=f"Company {job_id}",
        area=area,
        salary_min_k=salary_min,
        salary_max_k=salary_min + 10,
        remote_status=RemoteStatus.UNKNOWN,
        remote_confidence=RemoteConfidence.LOW,
        source="fixture",
        source_url="about:blank",
        source_version=None,
        collected_at=datetime(2026, 8, 26, tzinfo=UTC),
    )


def _report(job_id: str) -> StoredMatchReport:
    return StoredMatchReport(
        id=f"report_{job_id}",
        report=MatchReport(
            job_id=job_id,
            profile_id="profile_1",
            profile_version=1,
            extraction_id=f"ext_{job_id}",
            eligibility=EligibilityDecision.BLOCKED,
            recommendation=MatchRecommendation.BLOCKED,
            summary="blocked",
            strengths=(),
            risks=(),
            requirement_results=(),
            matched_requirement_ids=(),
            partial_requirement_ids=(),
            missing_requirement_ids=(),
            evidence_links=(),
            matcher_version="semantic-match-v1",
            prompt_version="semantic-match-v3",
            model=None,
            trace_run_id=None,
        ),
        created_at=datetime(2026, 8, 26, tzinfo=UTC),
    )


class _Jobs:
    def __init__(self, items: tuple[JobListItem, ...]) -> None:
        self.items = items

    def execute(self, query):
        assert query.limit == 50
        return JobPage(total=len(self.items), limit=query.limit, offset=0, items=self.items)


class _Ranking:
    def __init__(self, reports: tuple[StoredMatchReport, ...]) -> None:
        self.reports = reports

    def execute(self, job_ids, *, include_blocked=False, top_n=None):
        assert include_blocked is True
        return self.reports


class _Inputs:
    def __init__(self, details: dict[str, object]) -> None:
        self.details = details

    def execute(self, job_id: str):
        return self.details[job_id]


def _readiness(*, ready=False, career=True, requirements=True, codes=()):
    return SimpleNamespace(
        inputs_release_eligible=ready,
        career_context=SimpleNamespace(release_eligible=career),
        job_requirements=SimpleNamespace(release_eligible=requirements),
        blockers=tuple(SimpleNamespace(code=code) for code in codes),
    )


class _CareerContext:
    def __init__(self, intent: SearchIntentDetail | None) -> None:
        self.intent = intent

    def get_current_search_intent(self):
        return self.intent


def _intent() -> SearchIntentDetail:
    return SearchIntentDetail(
        id="intent_1",
        version=1,
        target_roles=("AI Agent工程师", "FDE", "ai产品经理"),
        cities=("武汉",),
        remote_accepted=True,
        minimum_salary_k=14,
        seniority=None,
        employment_types=(),
        exclude_keywords=(),
        hard_constraints=(),
        soft_preferences=(),
        created_at=datetime(2026, 8, 26, tzinfo=UTC),
    )


def test_coverage_prioritizes_requirement_refresh_candidates_by_explicit_intent_signals() -> None:
    items = (
        _job("job_report", "Frontend Engineer"),
        _job("job_ready", "AI Developer"),
        _job("job_plain", "Backend Engineer", area="北京", salary_min=10),
        _job("job_ai_platform", "高级AI平台工程师", salary_min=18),
        _job("job_fde", "前沿部署工程师(FDE)", salary_min=18),
        _job("job_agent", "AI Agent研发工程师", salary_min=20),
    )
    details = {
        "job_ready": _readiness(ready=True),
        "job_plain": _readiness(requirements=False, codes=("accepted_baseline_missing",)),
        "job_ai_platform": _readiness(requirements=False, codes=("accepted_baseline_missing",)),
        "job_fde": _readiness(requirements=False, codes=("accepted_baseline_missing",)),
        "job_agent": _readiness(requirements=False, codes=("accepted_baseline_missing",)),
    }

    result = BuildRecommendationCoverageUseCase(
        jobs=_Jobs(items),
        match_inputs=_Inputs(details),
        ranking=_Ranking((_report("job_report"),)),
        career_context=_CareerContext(_intent()),
    ).execute()

    assert result.current_report_count == 1
    assert result.match_ready_without_report_count == 1
    assert result.requirement_analysis_needed_count == 4
    assert result.profile_blocked_count == 0
    assert result.other_blocked_count == 0
    assert tuple(item.job_id for item in result.next_analysis_candidates) == (
        "job_fde",
        "job_agent",
        "job_ai_platform",
        "job_plain",
    )
    assert result.next_analysis_candidates[0].intent_signals == (
        "目标方向：FDE",
        "目标城市：武汉",
        "薪资下限达到 14K",
    )
    ai_platform = next(
        item for item in result.next_analysis_candidates if item.job_id == "job_ai_platform"
    )
    assert ai_platform.intent_signals == ("目标城市：武汉", "薪资下限达到 14K")
    assert all("ai产品经理" not in signal for signal in ai_platform.intent_signals)
    assert result.db_writes == result.provider_calls == result.trace_runs_created == 0


def test_coverage_keeps_profile_blockers_out_of_requirement_refresh_queue() -> None:
    items = (_job("job_profile", "AI Agent工程师"), _job("job_other", "FDE"))
    details = {
        "job_profile": _readiness(career=False, requirements=False, codes=("profile_missing",)),
        "job_other": _readiness(career=True, requirements=True, codes=("unknown",)),
    }

    result = BuildRecommendationCoverageUseCase(
        jobs=_Jobs(items),
        match_inputs=_Inputs(details),
        ranking=_Ranking(()),
        career_context=_CareerContext(_intent()),
    ).execute()

    assert result.profile_blocked_count == 1
    assert result.other_blocked_count == 1
    assert result.requirement_analysis_needed_count == 0
    assert result.next_analysis_candidates == ()
