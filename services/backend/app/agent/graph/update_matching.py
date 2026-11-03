"""Bounded matching inside the existing run, with replay-safe explicit commands."""
from dataclasses import dataclass, replace
import logging

_logger = logging.getLogger(__name__)
from app.agent.graph.command_digest import _digest
from app.agent.graph.checkpoint_port import CheckpointConflictError
from app.agent.graph.state import CareerAgentStatus, UpdateBatchCommand
from app.application.rule_match import RuleMatchRequiresModel
from app.application.analysis_update import UpdateMatchFactsChanged
from app.db.models.common import new_match_report_id


@dataclass(frozen=True, slots=True)
class UpdateBatchRequest:
    action_id: str
    expected_revision: int
    use_completed_only: bool = False

    def digest(self):
        return _digest('update_batch', dict(action=self.action_id, revision=self.expected_revision,
                                           use_completed_only=self.use_completed_only))


def batch_replayed(state, command):
    if command is None:
        return False
    for accepted in state.update_batch_commands:
        if accepted.action_id == command.action_id:
            if accepted.digest != command.digest():
                raise CheckpointConflictError('分批请求标识已用于不同内容，请查看原运行')
            return True
    return False


class UpdateMatchingExecutor:
    MAX_ATTEMPTS = 5

    def __init__(self, *, facts, matcher):
        self.facts, self.matcher = facts, matcher

    def execute(self, state, checkpoints, command):
        if batch_replayed(state, command):
            return state
        if command is None:
            raise CheckpointConflictError('请使用新的明确分批命令继续；查看或重放不会自动重算')
        if command.expected_revision != state.revision:
            raise CheckpointConflictError('运行修订已变化，请读取最新状态后再继续')
        successful = lambda s: s.status in {'completed', 'reused'}
        if command.use_completed_only and not any(successful(s) for s in state.update_steps):
            raise CheckpointConflictError('当前没有可用岗位，不能用空结果生成目标建议')
        try:
            self.facts.capture(state)
        except UpdateMatchFactsChanged:
            return checkpoints.transition(state, replace(state, status=CareerAgentStatus.STALE,
                current_step='update_inputs_changed', pending_approval=False))
        partial = state.update_partial or (command.use_completed_only and not all(successful(s) for s in state.update_steps))
        accepted = UpdateBatchCommand(command.action_id, command.digest())
        state = checkpoints.transition(state, replace(state, status=CareerAgentStatus.RUNNING,
            current_step='update_matching', update_batch_commands=(*state.update_batch_commands, accepted),
            update_partial=partial))
        if partial:
            return state
        # Pending work has priority over previous failures: one broken job cannot starve a batch.
        eligible = [s.job_id for s in state.update_steps if s.status in {'pending', 'running'}]
        eligible += [s.job_id for s in state.update_steps if s.status == 'failed']
        for job_id in eligible[:self.MAX_ATTEMPTS]:
            checkpoints.assert_execution()
            try:
                facts = self.facts.capture(state)
            except UpdateMatchFactsChanged:
                return checkpoints.transition(state, replace(state, status=CareerAgentStatus.STALE,
                    current_step='update_inputs_changed', pending_approval=False))
            step = next(s for s in state.update_steps if s.job_id == job_id)
            claimed = replace(step, status='running', attempt=step.attempt + 1, error_code=None)
            state = checkpoints.transition(state, self._set_step(state, claimed))
            item = next(j for j in facts.jobs if j.job_id == job_id)
            try:
                report = self.matcher.execute(profile=facts.context.profile, intent=facts.context.search_intent,
                                              job=item.job, extraction=item.extraction)
            except RuleMatchRequiresModel:
                state = checkpoints.transition(state, self._set_step(state,
                    replace(claimed, status='requires_model', error_code='model_authorization_required')))
                continue
            except Exception as exc:
                # Do not log exception messages, Profile content or raw job descriptions.
                _logger.warning("Rule match failed thread=%s job=%s attempt=%s error_type=%s",
                    state.thread_id, job_id, claimed.attempt, type(exc).__name__)
                # This boundary surrounds pure computation only. Persistence errors are never masked.
                candidate = self._set_step(state, replace(claimed, status='failed', error_code='rule_match_failed'))
                state = checkpoints.transition(state, replace(candidate, last_error_class=type(exc).__name__))
                continue
            report_id = new_match_report_id()
            candidate = self._set_step(state, replace(claimed, status='completed', report_id=report_id))
            state = checkpoints.complete_update_match(state, candidate, report_id, replace(report, db_writes=1),
                                                      validate=self.facts.stale)
            if state.status is CareerAgentStatus.STALE:
                return state
        return state

    @staticmethod
    def _set_step(state, updated):
        return replace(state, update_steps=tuple(updated if s.job_id == updated.job_id else s for s in state.update_steps))
