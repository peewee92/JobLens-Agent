from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.application.application_workspace.interview_mock import (
    BuildInterviewMockQuestionSetUseCase,
    InterviewAnswerGroundingStatus,
    InterviewMockBlockedError,
    ReviewInterviewMockAnswerUseCase,
)
from app.application.application_workspace.models import (
    ApplicationWorkspace,
    ApplicationWorkspaceSourceSnapshot,
    ApplicationWorkspaceStatus,
)
from app.application.application_workspace.resume_variant import (
    BuildResumeVariantProposalUseCase,
    ResumeVariantBlockedError,
)
from app.application.application_workspace.status_use_case import (
    ApplicationStatusBlockedError,
    UpdateApplicationStatusCommand,
    UpdateApplicationStatusUseCase,
)
from app.application.job_preparation.interview_question_facts import (
    InterviewEvidenceStatus,
    InterviewPreparationPriority,
    InterviewQuestionFactItem,
    InterviewQuestionFacts,
)
from app.application.job_preparation.resume_delta import (
    ResumeDeltaEvidenceGap,
    ResumeDeltaFacts,
    ResumeDeltaGapStatus,
    ResumeDeltaHighlight,
)
from app.domain.job_requirements import RequirementImportance, RequirementType

NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)


class WorkspaceRepo:
    def __init__(self, workspace):
        self.workspace = workspace

    def get(self, workspace_id):
        return self.workspace if workspace_id == self.workspace.workspace_id else None


class Preparation:
    def __init__(self, bundle):
        self.bundle = bundle

    def execute(self, job_id):
        assert job_id == self.bundle.job_id
        return self.bundle


class Timeline:
    def __init__(self):
        self.events = {}

    def get_by_actor_and_idempotency_key(self, actor_id, key):
        return self.events.get((actor_id, key))

    def add(self, event):
        self.events[(event.actor_id, event.idempotency_key)] = event
        return event


class MutableWorkspaceRepo(WorkspaceRepo):
    def update_status(self, *, workspace_id, expected_status, new_status, updated_at):
        if self.workspace.workspace_id != workspace_id or self.workspace.status != expected_status:
            return None
        self.workspace = replace(self.workspace, status=new_status, updated_at=updated_at)
        return self.workspace


def workspace(case: int, *, profile_version: int = 3) -> ApplicationWorkspace:
    return ApplicationWorkspace(
        workspace_id=f"ws_{case}",
        job_id=f"job_{case}",
        actor_id=f"user_{case}",
        idempotency_key=f"create-{case}",
        status=ApplicationWorkspaceStatus.PREPARING,
        source_snapshot=ApplicationWorkspaceSourceSnapshot(
            f"prof_{case}", profile_version, f"intent_{case}", 2, f"reqrun_{case}", f"match_{case}"
        ),
        current_fact_fingerprint=f"{case:064x}"[-64:],
        created_at=NOW,
        updated_at=NOW,
    )


def resume_bundle(case: int, *, profile_version: int = 3):
    delta = ResumeDeltaFacts(
        f"job_{case}",
        True,
        f"prof_{case}",
        profile_version,
        f"reqrun_{case}",
        (ResumeDeltaHighlight(f"r_{case}", f"Capability {case}", (f"skill_{case}",), (f"ev_{case}",)),),
        (ResumeDeltaEvidenceGap(f"gap_{case}", f"Missing {case}", ResumeDeltaGapStatus.MISSING, ()),),
        (),
    )
    return SimpleNamespace(
        job_id=f"job_{case}", facts_usable=True, profile_id=f"prof_{case}", profile_version=profile_version,
        extraction_id=f"reqrun_{case}", resume_delta=delta,
    )


def interview_bundle(case: int, *, profile_version: int = 3):
    facts = InterviewQuestionFacts(
        job_id=f"job_{case}", facts_usable=True, profile_id=f"prof_{case}", profile_version=profile_version,
        extraction_id=f"reqrun_{case}",
        items=(
            InterviewQuestionFactItem(
                requirement_id=f"r_{case}", requirement_type=RequirementType.SKILL,
                requirement_text=f"Requirement {case}", importance=RequirementImportance.MUST_HAVE,
                normalized_capability=f"Capability {case}", preparation_priority=InterviewPreparationPriority.HIGH,
                evidence_status=InterviewEvidenceStatus.SUPPORTED, profile_skill_ids=(f"skill_{case}",),
                evidence_ids=(f"ev_{case}",), evidence_summaries=(f"Evidence {case}",),
            ),
        ), blockers=(),
    )
    return SimpleNamespace(
        job_id=f"job_{case}", facts_usable=True, profile_id=f"prof_{case}", profile_version=profile_version,
        extraction_id=f"reqrun_{case}", interview_facts=facts,
    )


@pytest.mark.parametrize("case", range(10))
def test_resume_gate_grounded_content_has_exact_job_requirement_and_evidence_provenance(case: int) -> None:
    proposal = BuildResumeVariantProposalUseCase(
        workspaces=WorkspaceRepo(workspace(case)), preparation=Preparation(resume_bundle(case))
    ).execute(f"ws_{case}")

    assert proposal.highlights[0].requirement_id == f"r_{case}"
    assert proposal.highlights[0].evidence_ids == (f"ev_{case}",)
    assert proposal.unresolved_requirement_ids == (f"gap_{case}",)


@pytest.mark.parametrize("case", range(10, 20))
def test_resume_gate_never_promotes_unevidenced_requirement_to_resume_content(case: int) -> None:
    proposal = BuildResumeVariantProposalUseCase(
        workspaces=WorkspaceRepo(workspace(case)), preparation=Preparation(resume_bundle(case))
    ).execute(f"ws_{case}")

    highlight_requirement_ids = {item.requirement_id for item in proposal.highlights}
    assert f"gap_{case}" not in highlight_requirement_ids
    assert all(item.evidence_ids for item in proposal.highlights)


@pytest.mark.parametrize("case", range(20, 30))
def test_resume_gate_rejects_stale_profile_snapshot(case: int) -> None:
    with pytest.raises(ResumeVariantBlockedError, match="application_workspace_facts_stale"):
        BuildResumeVariantProposalUseCase(
            workspaces=WorkspaceRepo(workspace(case)),
            preparation=Preparation(resume_bundle(case, profile_version=4)),
        ).execute(f"ws_{case}")


@pytest.mark.parametrize("case", range(30, 40))
def test_interview_gate_question_and_grounded_answer_stay_with_current_requirement(case: int) -> None:
    questions = BuildInterviewMockQuestionSetUseCase(
        workspaces=WorkspaceRepo(workspace(case)), preparation=Preparation(interview_bundle(case))
    )
    result = questions.execute(f"ws_{case}")
    review = ReviewInterviewMockAnswerUseCase(
        question_sets=questions, timeline=Timeline(), now=lambda: NOW, new_event_id=lambda: f"evt_{case}"
    ).execute(
        workspace_id=f"ws_{case}", question_id=f"iq_r_{case}", answer_text="grounded answer",
        evidence_ids=(f"ev_{case}",), actor_id=f"user_{case}", idempotency_key=f"mock-{case}",
    )

    assert result.questions[0].requirement_id == f"r_{case}"
    assert result.questions[0].allowed_evidence_ids == (f"ev_{case}",)
    assert review.grounding_status is InterviewAnswerGroundingStatus.GROUNDED


@pytest.mark.parametrize("case", range(40, 50))
def test_interview_gate_rejects_cross_job_or_invented_evidence(case: int) -> None:
    questions = BuildInterviewMockQuestionSetUseCase(
        workspaces=WorkspaceRepo(workspace(case)), preparation=Preparation(interview_bundle(case))
    )
    review = ReviewInterviewMockAnswerUseCase(
        question_sets=questions, timeline=Timeline(), now=lambda: NOW, new_event_id=lambda: f"evt_{case}"
    ).execute(
        workspace_id=f"ws_{case}", question_id=f"iq_r_{case}", answer_text="unsupported answer",
        evidence_ids=(f"ev_{case + 1}",), actor_id=f"user_{case}", idempotency_key=f"mock-{case}",
    )

    assert review.grounding_status is InterviewAnswerGroundingStatus.UNGROUNDED
    assert review.accepted_evidence_ids == ()
    assert review.rejected_evidence_ids == (f"ev_{case + 1}",)
    assert review.retry_recommended is True


@pytest.mark.parametrize("case", range(50, 60))
def test_interview_gate_rejects_stale_workspace_facts(case: int) -> None:
    with pytest.raises(InterviewMockBlockedError, match="application_workspace_facts_stale"):
        BuildInterviewMockQuestionSetUseCase(
            workspaces=WorkspaceRepo(workspace(case)),
            preparation=Preparation(interview_bundle(case, profile_version=4)),
        ).execute(f"ws_{case}")


@pytest.mark.parametrize("case", range(60, 65))
def test_state_gate_user_status_write_is_idempotent(case: int) -> None:
    repo = MutableWorkspaceRepo(workspace(case))
    timeline = Timeline()
    use_case = UpdateApplicationStatusUseCase(
        workspaces=repo, timeline=timeline, now=lambda: NOW + timedelta(minutes=1), new_event_id=lambda: f"evt_{case}"
    )
    command = UpdateApplicationStatusCommand(
        workspace_id=f"ws_{case}", actor_id=f"user_{case}", idempotency_key=f"status-{case}",
        expected_status=ApplicationWorkspaceStatus.PREPARING, new_status=ApplicationWorkspaceStatus.READY_TO_APPLY,
    )

    first = use_case.execute(command)
    second = use_case.execute(command)
    assert first == second
    assert len(timeline.events) == 1


@pytest.mark.parametrize("case", range(65, 70))
def test_state_gate_rejects_non_owner_status_mutation(case: int) -> None:
    use_case = UpdateApplicationStatusUseCase(
        workspaces=MutableWorkspaceRepo(workspace(case)), timeline=Timeline(),
        now=lambda: NOW + timedelta(minutes=1), new_event_id=lambda: f"evt_{case}"
    )
    with pytest.raises(ApplicationStatusBlockedError, match="workspace_actor_mismatch"):
        use_case.execute(UpdateApplicationStatusCommand(
            workspace_id=f"ws_{case}", actor_id="agent", idempotency_key=f"status-{case}",
            expected_status=ApplicationWorkspaceStatus.PREPARING, new_status=ApplicationWorkspaceStatus.APPLIED,
        ))


@pytest.mark.parametrize("case", range(70, 75))
def test_state_gate_rejects_stale_expected_status(case: int) -> None:
    use_case = UpdateApplicationStatusUseCase(
        workspaces=MutableWorkspaceRepo(workspace(case)), timeline=Timeline(),
        now=lambda: NOW + timedelta(minutes=1), new_event_id=lambda: f"evt_{case}"
    )
    with pytest.raises(ApplicationStatusBlockedError, match="application_status_conflict"):
        use_case.execute(UpdateApplicationStatusCommand(
            workspace_id=f"ws_{case}", actor_id=f"user_{case}", idempotency_key=f"status-{case}",
            expected_status=ApplicationWorkspaceStatus.CONSIDERING, new_status=ApplicationWorkspaceStatus.APPLIED,
        ))


@pytest.mark.parametrize("case", range(75, 80))
def test_state_gate_rejects_idempotency_reuse_for_different_transition(case: int) -> None:
    repo = MutableWorkspaceRepo(workspace(case))
    timeline = Timeline()
    use_case = UpdateApplicationStatusUseCase(
        workspaces=repo, timeline=timeline, now=lambda: NOW + timedelta(minutes=1), new_event_id=lambda: f"evt_{case}"
    )
    use_case.execute(UpdateApplicationStatusCommand(
        workspace_id=f"ws_{case}", actor_id=f"user_{case}", idempotency_key=f"status-{case}",
        expected_status=ApplicationWorkspaceStatus.PREPARING, new_status=ApplicationWorkspaceStatus.READY_TO_APPLY,
    ))
    with pytest.raises(ApplicationStatusBlockedError, match="idempotency_key_conflict"):
        use_case.execute(UpdateApplicationStatusCommand(
            workspace_id=f"ws_{case}", actor_id=f"user_{case}", idempotency_key=f"status-{case}",
            expected_status=ApplicationWorkspaceStatus.READY_TO_APPLY, new_status=ApplicationWorkspaceStatus.APPLIED,
        ))
