"""Versioned command identity, independent of transport and private fact payloads."""
from __future__ import annotations

import hashlib
import json


def _digest(kind: str, content: dict) -> str:
    encoded = json.dumps({"version": 1, "kind": kind, **content}, sort_keys=True,
                         ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def start_command_digest(*, thread_id: str, run_id: str, request_id: str,
                         job_ids: tuple[str, ...], top_n: int) -> str:
    return _digest("start", {"thread": thread_id, "run": run_id, "request": request_id,
                             "jobs": list(dict.fromkeys(job_ids)), "top_n": top_n})


def decision_command_digest(*, thread_id: str, interrupt_id: str, action_id: str,
                            decision: str, selected_job_ids: tuple[str, ...]) -> str:
    return _digest("decision", {"thread": thread_id, "interrupt": interrupt_id,
                                "action": action_id, "decision": decision,
                                "jobs": list(dict.fromkeys(selected_job_ids))})


def update_command_digest(*, thread_id: str, run_id: str, request_id: str,
                          source_thread_id: str, source_result_id: str, scope: str,
                          input_digest: str, top_n: int) -> str:
    return _digest("update", dict(thread=thread_id, run=run_id, request=request_id,
        source=source_thread_id, result=source_result_id, scope=scope,
        inputs=input_digest, top_n=top_n))
