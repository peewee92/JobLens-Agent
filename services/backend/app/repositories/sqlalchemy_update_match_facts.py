"""Pinned update input checks, including the final caller-owned write transaction."""
from app.application.match_policy_version import CURRENT_MATCH_POLICY_VERSION
from app.application.search_preferences import preference_input_fingerprint


from app.application.analysis_update import UpdateMatchFactsChanged, AnalysisUpdatePlanError


class SqlAlchemyUpdateMatchFacts:
    def __init__(self, *, reader, readiness):
        self.reader, self.readiness = reader, readiness

    def capture(self, state, *, session=None):
        try:
            facts = (self.reader.read_initial_scope(state.requested_job_ids, session=session)
                     if state.update_initial_scope else
                     self.reader.read_legacy_workspace(state.update_legacy_workspace_id, session=session)
                     if state.update_legacy_workspace_id else
                     self.reader.read(state.update_source_thread_id, state.update_scope, session=session))
        except AnalysisUpdatePlanError as exc:
            raise UpdateMatchFactsChanged('update_source_changed') from exc
        profile, intent = facts.context.profile, facts.context.search_intent
        identity = (profile.id if profile else None, profile.version if profile else None,
                    intent.id if intent else None, intent.version if intent else None)
        if identity != (state.profile_id, state.profile_version, state.search_intent_id, state.search_intent_version):
            raise UpdateMatchFactsChanged('career_context_changed')
        if (not state.update_initial_scope and not state.update_legacy_workspace_id and facts.result_id != state.update_source_result_id) or state.update_policy_version != CURRENT_MATCH_POLICY_VERSION:
            raise UpdateMatchFactsChanged('update_source_or_policy_changed')
        if tuple(item.job_id for item in facts.jobs) != state.requested_job_ids:
            raise UpdateMatchFactsChanged('update_scope_changed')
        for item, step in zip(facts.jobs, state.update_steps, strict=True):
            if step.status != 'input_blocked' and item.job and item.job.user_marked_inactive:
                raise UpdateMatchFactsChanged('job_user_marked_inactive')
            fingerprint = preference_input_fingerprint(intent, item.job) if intent and item.job else 'missing'
            extraction_id = item.extraction.extraction_id if item.extraction else None
            report_id = item.latest_report.id if item.latest_report else None
            expected_report = step.report_id if step.status in {'reused', 'completed'} else step.base_report_id
            if (extraction_id, fingerprint, report_id) != (step.extraction_id, step.input_fingerprint, expected_report):
                raise UpdateMatchFactsChanged('job_inputs_changed')
            if step.status != 'input_blocked':
                ready = self.readiness.execute(item.job_id)
                if not ready.inputs_release_eligible or (
                    ready.career_context.profile_id, ready.career_context.profile_version,
                    ready.career_context.search_intent_id, ready.career_context.search_intent_version,
                    ready.job_requirements.extraction_id) != (*identity, extraction_id):
                    raise UpdateMatchFactsChanged('release_changed')
        return facts

    def stale(self, state, *, session):
        try:
            self.capture(state, session=session)
        except UpdateMatchFactsChanged:
            return True
        return False
