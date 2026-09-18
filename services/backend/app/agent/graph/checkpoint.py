"""SQLite-first persistence for framework-neutral Career Agent checkpoints."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.agent.graph.state import CareerAgentState


class SQLiteCareerAgentCheckpointStore:
    """Persist the latest runtime state for each thread in a local SQLite file."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._database_path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS career_agent_checkpoints (
                    thread_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    current_step TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS career_agent_checkpoint_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(thread_id, payload_json)
                )
                """
            )

    def save(self, state: CareerAgentState) -> None:
        payload_json = json.dumps(
            state.to_payload(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO career_agent_checkpoints (
                    thread_id, run_id, status, current_step, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(thread_id) DO UPDATE SET
                    run_id = excluded.run_id,
                    status = excluded.status,
                    current_step = excluded.current_step,
                    payload_json = excluded.payload_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    state.thread_id,
                    state.run_id,
                    state.status.value,
                    state.current_step,
                    payload_json,
                ),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO career_agent_checkpoint_events (thread_id, payload_json)
                VALUES (?, ?)
                """,
                (state.thread_id, payload_json),
            )

    def load(self, *, thread_id: str) -> CareerAgentState | None:
        payload = self.load_payload(thread_id=thread_id)
        if payload is None:
            return None
        return CareerAgentState.from_payload(payload)

    def load_payload(self, *, thread_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM career_agent_checkpoints WHERE thread_id = ?",
                (thread_id,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(row[0])
        if not isinstance(payload, dict):
            raise ValueError("career agent checkpoint payload must be an object")
        return payload

    def load_history(self, *, thread_id: str) -> tuple[CareerAgentState, ...]:
        """Return unique persisted state transitions in first-seen order."""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM career_agent_checkpoint_events
                WHERE thread_id = ?
                ORDER BY event_id ASC
                """,
                (thread_id,),
            ).fetchall()
        return tuple(CareerAgentState.from_payload(json.loads(row[0])) for row in rows)


__all__ = ["SQLiteCareerAgentCheckpointStore"]
