"""Atomic transition boundary shared by graph orchestration and persistence."""
from __future__ import annotations

from dataclasses import replace
from typing import Protocol, Any

from app.agent.graph.state import CareerAgentState, CareerAgentStatus as Status


class CheckpointConflictError(ValueError):
    """The expected run revision/phase is no longer authoritative."""


class CheckpointPersistenceError(RuntimeError):
    """A runtime transaction failed without accepting a partial result."""


class CheckpointNotReadyError(RuntimeError):
    """The primary runtime schema requires migration or database repair."""


def next_revision(previous: CareerAgentState | None, candidate: CareerAgentState) -> CareerAgentState:
    if previous is not None:
        if previous.legacy_read_only:
            raise CheckpointConflictError("旧运行仅供查看，请重新分析")
        frozen = ("thread_id", "run_id", "request_id", "goal", "profile_id", "profile_version",
                  "search_intent_id", "search_intent_version", "requested_job_ids", "start_command_digest", "requested_top_n",
                  "update_source_thread_id", "update_source_result_id", "update_scope", "update_input_digest", "update_report_ids", "update_policy_version")
        if any(getattr(previous, key) != getattr(candidate, key) for key in frozen):
            raise CheckpointConflictError("不能更改已有运行的身份或事实版本")
        if previous.update_steps:
            before, after = previous.update_steps, candidate.update_steps
            if len(before) != len(after):
                raise CheckpointConflictError("不能替换更新岗位范围")
            for old, new in zip(before, after, strict=True):
                if (old.job_id, old.extraction_id, old.input_fingerprint, old.base_report_id) != (
                    new.job_id, new.extraction_id, new.input_fingerprint, new.base_report_id):
                    raise CheckpointConflictError("不能替换更新步骤的固定输入")
                if old.status in {"completed", "reused", "requires_model", "input_blocked"} and old != new:
                    raise CheckpointConflictError("不能改写已保存或已阻断的步骤")
                allowed_steps = {"pending": {"pending", "running"}, "running": {"running", "completed", "failed", "requires_model"},
                                 "failed": {"failed", "running"}}
                if old.status in allowed_steps and new.status not in allowed_steps[old.status]:
                    raise CheckpointConflictError("更新步骤迁移不合法")
                if new.attempt != old.attempt + (new.status == "running" and new != old):
                    raise CheckpointConflictError("步骤尝试次数与领取不一致")
                if new.status in {"completed", "reused"} and not new.report_id:
                    raise CheckpointConflictError("完成步骤缺少报告")
            if candidate.update_batch_commands[:len(previous.update_batch_commands)] != previous.update_batch_commands:
                raise CheckpointConflictError("不能改写已接受的分批命令")
            if len({c.action_id for c in candidate.update_batch_commands}) != len(candidate.update_batch_commands):
                raise CheckpointConflictError("分批命令标识不能重复")
            if previous.update_partial and not candidate.update_partial:
                raise CheckpointConflictError("不能扩大已接受的部分分析范围")
            if previous.current_match_report_ids and (before != after or previous.update_partial != candidate.update_partial
                    or previous.update_batch_commands != candidate.update_batch_commands):
                raise CheckpointConflictError("排序之后不能更改更新步骤或范围")
        if previous.result_id is not None and candidate.result_id != previous.result_id:
            raise CheckpointConflictError("不能改写已保存的分析结果引用")
        if previous.decision_action_id is not None:
            for key in ("decision_action_id", "decision_command_digest", "human_decision", "confirmed_target_job_ids"):
                if getattr(previous, key) != getattr(candidate, key):
                    raise CheckpointConflictError("不能改写已经接受的人工决定")
        if previous.current_match_report_ids:
            for key in ("current_match_report_ids", "match_fingerprint", "ranked_job_ids", "proposed_target_job_ids"):
                if getattr(previous, key) != getattr(candidate, key):
                    raise CheckpointConflictError("等待确认后不能替换原始报告与目标建议")
        expected_steps = {
            Status.INTERRUPTED: {"target_cohort_confirmation"},
            Status.RESUMING: {"target_cohort_resume", "skill_gap_ready"},
            Status.COMPLETED: {"skill_gap_completed"},
            Status.CANCELLED: {"target_cohort_rejected"},
        }
        if candidate.status in expected_steps and candidate.current_step not in expected_steps[candidate.status]:
            raise CheckpointConflictError("运行步骤与状态不一致")
        if previous.current_step == "skill_gap_ready" and candidate.current_step == "target_cohort_resume":
            raise CheckpointConflictError("不能退回已经完成的确认步骤")
        allowed = {
            Status.CREATED: {Status.RUNNING, Status.BLOCKED, Status.FAILED, Status.STALE},
            Status.RUNNING: {Status.RUNNING, Status.INTERRUPTED, Status.BLOCKED, Status.FAILED, Status.STALE},
            Status.INTERRUPTED: {Status.RESUMING, Status.CANCELLED, Status.STALE},
            Status.RESUMING: {Status.RESUMING, Status.COMPLETED, Status.BLOCKED, Status.FAILED, Status.STALE},
        }
        if candidate.status not in allowed.get(previous.status, set()):
            raise CheckpointConflictError("运行状态迁移不合法，请读取最新状态")
        if candidate.status is Status.COMPLETED and previous.current_step != "skill_gap_ready":
            raise CheckpointConflictError("尚未领取可完成的分析步骤")
    elif candidate.status not in {Status.CREATED, Status.RUNNING, Status.INTERRUPTED, Status.BLOCKED}:
        raise CheckpointConflictError("新运行不能直接写入最终结果")
    return replace(candidate, revision=0 if previous is None else previous.revision + 1)


class CareerAgentCheckpointStore(Protocol):
    def transition(self, previous: CareerAgentState | None, candidate: CareerAgentState) -> CareerAgentState: ...
    def load(self, *, thread_id: str) -> CareerAgentState | None: ...
    def load_payload(self, *, thread_id: str) -> dict[str, Any] | None: ...
    def load_history(self, *, thread_id: str) -> tuple[CareerAgentState, ...]: ...
