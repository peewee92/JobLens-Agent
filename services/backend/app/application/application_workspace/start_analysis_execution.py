"""Start long-lived preparation from a saved analysis, not a long-lived Agent run."""
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Callable
from pydantic import TypeAdapter

from app.application.saved_career_analysis import fact_json
from app.application.application_workspace.models import ApplicationWorkspaceSourceSnapshot
from app.application.application_workspace.use_case import CreateApplicationWorkspaceCommand, CreateApplicationWorkspaceUseCase, _fingerprint
from app.application.application_workspace.resume_variant import BuildResumeVariantProposalUseCase, SaveResumeVariantUseCase
from app.application.application_workspace.execution_action import (
    CreateStudyExecutionActionsUseCase, ExecutionActionItem, ExecutionActionType, ExecutionActionStatus,
)

LOCAL_ACTOR_ID = "local-user"


class StartAnalysisExecutionError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class StartAnalysisExecutionCommand:
    thread_id: str
    command_id: str
    result_id: str
    job_ids: tuple[str, ...]

    def digest(self) -> str:
        return sha256(json.dumps({"thread": self.thread_id, "result": self.result_id,
            "jobs": sorted(set(self.job_ids))}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class AnalysisExecutionWorkspace:
    job_id: str
    workspace_id: str
    resume_variant_id: str | None
    action_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisExecutionResult:
    thread_id: str
    result_id: str
    command_id: str
    items: tuple[AnalysisExecutionWorkspace, ...]

    def to_payload(self):
        return fact_json(self)

    @classmethod
    def from_payload(cls, value):
        return TypeAdapter(cls).validate_python(value)


def analysis_source_snapshot(result, binding):
    return ApplicationWorkspaceSourceSnapshot(result.inputs.profile_id, result.inputs.profile_version,
        result.inputs.search_intent_id, result.inputs.search_intent_version,
        binding.extraction_id, binding.match_report_id)


class StartAnalysisExecutionUseCase:
    def __init__(self, *, uow_factory, now: Callable, new_id: Callable):
        self._uow_factory, self._now, self._new_id = uow_factory, now, new_id

    def execute(self, command: StartAnalysisExecutionCommand) -> AnalysisExecutionResult:
        if not 1 <= len(command.job_ids) <= 5 or not all(command.job_ids):
            raise StartAnalysisExecutionError("analysis_execution_selection_invalid")
        with self._uow_factory() as uow:
            receipt = uow.find_receipt(LOCAL_ACTOR_ID, command.command_id)
            if receipt is not None:
                if receipt.command_digest != command.digest():
                    raise StartAnalysisExecutionError("analysis_execution_command_conflict")
                return AnalysisExecutionResult.from_payload(receipt.response)
            analysis, status = uow.load_analysis(command.thread_id)
            if analysis is None or analysis.result_id != command.result_id:
                raise StartAnalysisExecutionError("analysis_execution_result_missing")
            if status != "completed":
                raise StartAnalysisExecutionError("analysis_execution_not_completed")
            if not set(command.job_ids) <= set(analysis.inputs.selected_job_ids):
                raise StartAnalysisExecutionError("analysis_execution_selection_invalid")
            if uow.stale_reasons(analysis.inputs):
                raise StartAnalysisExecutionError("analysis_execution_facts_stale")
            bundles = {item.job_id: item for item in analysis.preparations}
            bindings = {item.job_id: item for item in analysis.bindings}
            items = []
            # The accepted target order, not concurrent request ordering, owns presentation order.
            for job_id in analysis.inputs.selected_job_ids:
                if job_id not in command.job_ids:
                    continue
                bundle = bundles.get(job_id)
                if bundle is None or not bundle.facts_usable:
                    raise StartAnalysisExecutionError("analysis_execution_materials_unusable")
                binding = bindings[job_id]
                snapshot = analysis_source_snapshot(analysis, binding)
                workspace = uow.workspaces.get_latest_for_actor_and_job(LOCAL_ACTOR_ID, job_id)
                if workspace is None:
                    key = f"web-application-workspace:{job_id}"
                    creator = CreateApplicationWorkspaceUseCase(career_context=None, requirement_gate=None,
                        match_reports=None, workspaces=uow.workspaces, timeline=uow.timeline,
                        now=self._now, new_id=self._new_id, new_event_id=self._new_id)
                    workspace = creator.execute_from_snapshot(CreateApplicationWorkspaceCommand(
                        job_id, LOCAL_ACTOR_ID, key), snapshot)
                # Never rewrite original facts, manual status, completed actions or old resume variants.
                workspace = uow.workspaces.link_analysis(workspace.workspace_id, thread_id=analysis.thread_id,
                    result_id=analysis.result_id, fingerprint=_fingerprint(job_id, snapshot), updated_at=self._now())
                material_hash = sha256(json.dumps(fact_json(bundle), sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest()
                material_key = f"prep-v1:{material_hash}:{workspace.workspace_id}"
                proposal = BuildResumeVariantProposalUseCase.execute_from_bundle(workspace, bundle, snapshot=snapshot)
                variant = None
                if proposal.highlights:
                    class PinnedProposal:
                        def execute(self, workspace_id):
                            return proposal
                    variant = SaveResumeVariantUseCase(proposals=PinnedProposal(), variants=uow.variants,
                        timeline=uow.timeline, now=self._now, new_id=self._new_id, new_event_id=self._new_id).execute(
                        workspace_id=workspace.workspace_id, actor_id=LOCAL_ACTOR_ID, idempotency_key=f"resume:{material_key}")
                studies = CreateStudyExecutionActionsUseCase(workspaces=uow.workspaces, preparation=None,
                    actions=uow.actions, now=self._now, new_id=self._new_id).execute_from_bundle(
                    workspace=workspace, bundle=bundle, actor_id=LOCAL_ACTOR_ID,
                    idempotency_key=f"study:{material_key}", snapshot=snapshot)
                extras = self._preparation_actions(uow, workspace, bundle, material_key)
                items.append(AnalysisExecutionWorkspace(job_id, workspace.workspace_id,
                    variant.variant_id if variant else None, tuple(item.action_id for item in (*studies, *extras))))
            response = AnalysisExecutionResult(analysis.thread_id, analysis.result_id, command.command_id, tuple(items))
            uow.save_receipt(actor_id=LOCAL_ACTOR_ID, command=command, response=response)
            uow.commit()
            return response

    def _preparation_actions(self, uow, workspace, bundle, material_key):
        """Real preparation work is useful even when no learning gap is detected."""
        specs = []
        if bundle.resume_delta and bundle.resume_delta.highlights:
            specs.append(("resume", ExecutionActionType.IMPROVE_RESUME,
                tuple(item.requirement_id for item in bundle.resume_delta.highlights),
                "核对并整理这个岗位的简历事实要点", (
                    "逐项核对岗位要求与已确认经历的对应关系。",
                    "只采用可引用的事实，明确保留未覆盖或待核实项。")))
        if bundle.interview_facts and bundle.interview_facts.items:
            specs.append(("interview", ExecutionActionType.PREPARE_INTERVIEW,
                tuple(item.requirement_id for item in bundle.interview_facts.items),
                "围绕岗位要求准备真实经历说明", (
                    "逐项查看已保存的面试问题及允许引用的证据。",
                    "形成真实经历说明；没有证据的部分如实列为待核实，不编造结果或指标。")))
        created = []
        for name, action_type, requirements, description, criteria in specs:
            key = f"{name}:{material_key}"
            action = uow.actions.get_by_actor_and_idempotency_key(LOCAL_ACTOR_ID, key)
            if action is None:
                now = self._now()
                action = uow.actions.add(ExecutionActionItem(self._new_id(), workspace.workspace_id,
                    LOCAL_ACTOR_ID, key, action_type, ExecutionActionStatus.TODO, requirements, None,
                    description, criteria, now, now, source_analysis_thread_id=workspace.current_analysis_thread_id,
                    source_analysis_result_id=workspace.current_analysis_result_id))
            created.append(action)
        return tuple(created)
