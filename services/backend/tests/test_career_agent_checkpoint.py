from pathlib import Path

from app.agent.graph.checkpoint import SQLiteCareerAgentCheckpointStore
from app.agent.graph.state import CareerAgentState, CareerAgentStatus


def _pending_state() -> CareerAgentState:
    return CareerAgentState(
        thread_id="thread-1",
        run_id="run-1",
        request_id="request-1",
        status=CareerAgentStatus.INTERRUPTED,
        current_step="target_cohort_confirmation",
        goal="analyze_target_cohort_gaps",
        profile_id="profile-1",
        profile_version=3,
        search_intent_id="intent-1",
        search_intent_version=2,
        requested_job_ids=("job-1", "job-2", "job-3"),
        current_match_report_ids=("match-1", "match-2", "match-3"),
        match_fingerprint="match-fingerprint-1",
        ranked_job_ids=("job-2", "job-1", "job-3"),
        proposed_target_job_ids=("job-2", "job-1"),
        pending_approval=True,
    )


def test_checkpoint_round_trip_survives_store_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "career-agent-checkpoints.sqlite3"
    first_store = SQLiteCareerAgentCheckpointStore(database_path)
    state = _pending_state()

    first_store.save(state)

    restarted_store = SQLiteCareerAgentCheckpointStore(database_path)
    restored = restarted_store.load(thread_id=state.thread_id)

    assert restored == state
    assert restored is not state


def test_checkpoint_payload_contains_refs_not_raw_career_documents(tmp_path: Path) -> None:
    database_path = tmp_path / "career-agent-checkpoints.sqlite3"
    store = SQLiteCareerAgentCheckpointStore(database_path)
    state = _pending_state()

    store.save(state)
    payload = store.load_payload(thread_id=state.thread_id)

    assert payload["profile_id"] == "profile-1"
    assert payload["current_match_report_ids"] == ["match-1", "match-2", "match-3"]
    assert "resume" not in payload
    assert "raw_jd" not in payload
    assert "job_requirements" not in payload
