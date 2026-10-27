"""Strictly read-only access to the old standalone checkpoint file."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3

from app.agent.graph.state import CareerAgentState, CareerAgentStatus


def load_legacy_checkpoint(path: Path | None, thread_id: str) -> CareerAgentState | None:
    if path is None or not path.is_file():
        return None
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='career_agent_checkpoints'").fetchone() is None:
            return None
        row = connection.execute("SELECT payload_json FROM career_agent_checkpoints WHERE thread_id=?", (thread_id,)).fetchone()
    if row is None:
        return None
    state = CareerAgentState.from_payload(json.loads(row[0]))
    if state.status is CareerAgentStatus.COMPLETED:
        return replace(state, legacy_read_only=True, pending_approval=False, current_step="legacy_completed_no_snapshot")
    if state.status in {CareerAgentStatus.CANCELLED, CareerAgentStatus.BLOCKED, CareerAgentStatus.FAILED, CareerAgentStatus.STALE}:
        return replace(state, legacy_read_only=True, pending_approval=False)
    return replace(state, legacy_read_only=True, status=CareerAgentStatus.STALE,
                   current_step="legacy_reanalysis_required", pending_approval=False)
