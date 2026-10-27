"""Read-only Application Workspace overview and deterministic next action."""
from __future__ import annotations

from dataclasses import dataclass

from app.application.application_workspace.evidence_proposal import EvidenceProposalStatus, pending_evidence_proposals
from app.application.application_workspace.execution_action import ExecutionActionStatus
from app.application.application_workspace.models import ApplicationTimelineEventType, ApplicationWorkspace
from app.application.application_workspace.resume_variant import ResumeVariantStatus


class ApplicationWorkspaceOverviewBlockedError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ApplicationNextBestAction:
    code: str
    label: str
    reason: str
    href: str


@dataclass(frozen=True, slots=True)
class ApplicationWorkspaceOverview:
    workspace: ApplicationWorkspace
    resume_status: str
    action_total: int
    action_open: int
    evidence_pending_confirmation: int
    evidence_confirmed: int
    timeline_event_count: int
    next_best_action: ApplicationNextBestAction


class BuildApplicationWorkspaceOverviewUseCase:
    def __init__(self, *, workspaces, variants, actions, proposals, timeline, analyses=None) -> None:
        self._workspaces = workspaces
        self._variants = variants
        self._actions = actions
        self._proposals = proposals
        self._timeline = timeline
        self._analyses = analyses

    def execute(self, workspace_id: str) -> ApplicationWorkspaceOverview:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise ApplicationWorkspaceOverviewBlockedError("application_workspace_not_found")
        variants = tuple(self._variants.list_for_workspace(workspace_id))
        actions = tuple(self._actions.list_for_workspace(workspace_id))
        proposals = tuple(self._proposals.list_for_workspace(workspace_id))
        timeline = tuple(self._timeline.list_for_workspace(workspace_id))
        reviewed_resume = any(item.status == ResumeVariantStatus.REVIEWED for item in variants)
        pending_evidence = pending_evidence_proposals(proposals)
        confirmed_evidence = tuple(item for item in proposals if item.status == EvidenceProposalStatus.CONFIRMED)
        rematch_completed = any(item.event_type == ApplicationTimelineEventType.REMATCH_COMPLETED for item in timeline)
        open_actions = tuple(item for item in actions if item.status in {ExecutionActionStatus.TODO, ExecutionActionStatus.IN_PROGRESS})
        done_actions = tuple(item for item in actions if item.status == ExecutionActionStatus.DONE)

        needs_scoped_update = bool(confirmed_evidence and getattr(workspace, "current_analysis_thread_id", None))
        if needs_scoped_update and self._analyses is not None:
            analysis = self._analyses.load_analysis(thread_id=workspace.current_analysis_thread_id)
            if analysis and analysis.result_id == workspace.current_analysis_result_id:
                needs_scoped_update = any(p.confirmed_profile_version is None or
                    p.confirmed_profile_version > analysis.inputs.profile_version for p in confirmed_evidence)
        base = f"/applications/{workspace_id}"
        if not reviewed_resume:
            next_action = ApplicationNextBestAction("prepare_resume_variant", "审核岗位简历", "先把已确认经历整理成这个岗位可用的简历版本。", f"{base}#resume")
        elif pending_evidence:
            next_action = ApplicationNextBestAction("confirm_evidence", "确认真实经历证据", "已有行动产生待确认 Evidence，只有你确认后才能进入职业事实。", f"{base}#evidence")
        elif needs_scoped_update:
            from urllib.parse import quote
            next_action = ApplicationNextBestAction("update_analysis", "核对范围并更新分析",
                "已有新增事实；先检查关联分析的版本和可复用结果，不自动重算，也不承诺结论改善。",
                f"/agent/results/{quote(workspace.current_analysis_thread_id, safe='')}/update")
        elif confirmed_evidence and not getattr(workspace, "current_analysis_thread_id", None) and not rematch_completed:
            next_action = ApplicationNextBestAction("rematch", "重新验证岗位匹配", "新的职业事实已经确认，需要显式重新匹配才能核对判断变化；不承诺改善。", f"{base}#evidence")
        elif not actions:
            next_action = ApplicationNextBestAction("create_execution_actions", "建立准备行动", "把当前岗位的学习与准备清单变成可跟踪行动。", f"{base}#actions")
        elif open_actions:
            next_action = ApplicationNextBestAction("continue_action", "继续当前行动", "仍有未完成的岗位准备行动，优先完成已有事项。", f"{base}#actions")
        elif done_actions and not proposals:
            next_action = ApplicationNextBestAction("propose_evidence", "核实行动是否形成证据", "行动已完成，但完成不等于获得能力；如有真实经历，请提交 Evidence Proposal。", f"{base}#evidence")
        else:
            next_action = ApplicationNextBestAction("practice_interview", "练习岗位面试", "核心准备事实已形成，继续用真实 Evidence 练习岗位问题。", f"{base}#interview")

        resume_status = "reviewed" if reviewed_resume else (variants[-1].status.value if variants else "not_started")
        return ApplicationWorkspaceOverview(
            workspace=workspace, resume_status=resume_status, action_total=len(actions), action_open=len(open_actions),
            evidence_pending_confirmation=len(pending_evidence), evidence_confirmed=len(confirmed_evidence),
            timeline_event_count=len(timeline), next_best_action=next_action,
        )
