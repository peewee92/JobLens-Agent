"""Read-only Match blocker aggregation tests."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.application.eligibility import EligibilityDecision
from app.application.match_blocker_summary import BuildMatchBlockerSummaryUseCase
from app.application.match_report import MatchRecommendation, MatchReport, StoredMatchReport
from app.domain.job_requirements import RequirementImportance, RequirementType


def _stored(job_id: str, *, missing: tuple[str, ...], blocked: bool = True) -> StoredMatchReport:
    return StoredMatchReport(
        id=f"match_{job_id}",
        report=MatchReport(
            job_id=job_id,
            profile_id="profile_1",
            profile_version=1,
            extraction_id=f"ext_{job_id}",
            eligibility=EligibilityDecision.BLOCKED if blocked else EligibilityDecision.ELIGIBLE,
            recommendation=MatchRecommendation.BLOCKED if blocked else MatchRecommendation.GOOD,
            summary="fixture",
            strengths=(),
            risks=(),
            requirement_results=(),
            matched_requirement_ids=(),
            partial_requirement_ids=(),
            missing_requirement_ids=missing,
            evidence_links=(),
            matcher_version="semantic-match-v1",
            prompt_version="semantic-match-v3",
            model=None,
            trace_run_id=None,
        ),
        created_at=datetime(2026, 8, 26, tzinfo=UTC),
    )


class _Ranking:
    def __init__(self, reports: tuple[StoredMatchReport, ...]) -> None:
        self.reports = reports
        self.calls: list[tuple[tuple[str, ...], bool]] = []

    def execute(self, job_ids: tuple[str, ...], *, include_blocked: bool = False):
        self.calls.append((job_ids, include_blocked))
        return self.reports


class _Requirements:
    def __init__(self, by_job: dict[str, object]) -> None:
        self.by_job = by_job

    def get_latest(self, job_id: str):
        return self.by_job.get(job_id)


def _requirement(requirement_id: str, requirement_type: RequirementType, text: str):
    return SimpleNamespace(
        id=requirement_id,
        type=requirement_type,
        importance=RequirementImportance.MUST_HAVE,
        original_text=text,
    )


def test_blocker_summary_groups_missing_evidence_by_requirement_type_and_job_coverage() -> None:
    ranking = _Ranking(
        (
            _stored("job_1", missing=("edu_1", "skill_1")),
            _stored("job_2", missing=("edu_2",)),
            _stored("job_3", missing=(), blocked=False),
        )
    )
    requirements = _Requirements(
        {
            "job_1": SimpleNamespace(
                requirements=(
                    _requirement("edu_1", RequirementType.EDUCATION, "本科及以上学历"),
                    _requirement("skill_1", RequirementType.SKILL, "熟练使用 Python"),
                )
            ),
            "job_2": SimpleNamespace(
                requirements=(
                    _requirement("edu_2", RequirementType.EDUCATION, "计算机相关专业本科及以上"),
                )
            ),
        }
    )

    result = BuildMatchBlockerSummaryUseCase(
        ranking=ranking,
        requirements=requirements,
    ).execute(("job_1", "job_2", "job_3"))

    assert ranking.calls == [(("job_1", "job_2", "job_3"), True)]
    assert result.analyzed_report_count == 3
    assert result.blocked_report_count == 2
    assert result.missing_requirement_count == 3
    assert result.resolved_missing_requirement_count == 3
    assert result.unresolved_missing_requirement_ids == ()
    assert [item.requirement_type for item in result.categories] == [
        RequirementType.EDUCATION,
        RequirementType.SKILL,
    ]
    education = result.categories[0]
    assert education.affected_job_count == 2
    assert education.missing_requirement_count == 2
    assert education.affected_job_ids == ("job_1", "job_2")
    assert education.examples == ("本科及以上学历", "计算机相关专业本科及以上")
    assert [item.job_id for item in result.job_blockers] == ["job_1", "job_2"]
    assert result.job_blockers[0].missing_requirement_count == 2
    assert [item.requirement_id for item in result.job_blockers[0].requirements] == ["edu_1", "skill_1"]
    assert [item.original_text for item in result.job_blockers[0].requirements] == [
        "本科及以上学历",
        "熟练使用 Python",
    ]
    assert result.job_blockers[0].unresolved_missing_requirement_ids == ()
    assert result.db_writes == 0
    assert result.provider_calls == 0
    assert result.trace_runs_created == 0


def test_blocker_summary_never_silently_drops_missing_requirement_ids() -> None:
    ranking = _Ranking((_stored("job_1", missing=("missing_unknown",)),))
    requirements = _Requirements({"job_1": SimpleNamespace(requirements=())})

    result = BuildMatchBlockerSummaryUseCase(
        ranking=ranking,
        requirements=requirements,
    ).execute(("job_1",))

    assert result.missing_requirement_count == 1
    assert result.resolved_missing_requirement_count == 0
    assert result.unresolved_missing_requirement_ids == ("missing_unknown",)
    assert result.categories == ()
    assert result.job_blockers[0].job_id == "job_1"
    assert result.job_blockers[0].missing_requirement_count == 1
    assert result.job_blockers[0].requirements == ()
    assert result.job_blockers[0].unresolved_missing_requirement_ids == ("missing_unknown",)
