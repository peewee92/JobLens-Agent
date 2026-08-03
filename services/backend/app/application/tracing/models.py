"""Application trace write model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TraceWrite:
    run_id: str
    capability: str
    version: str
    model: str
    prompt_version: str
    input_refs: dict[str, Any]
    output: dict[str, Any] | None
    latency_ms: int
    input_tokens: int | None
    output_tokens: int | None
    error: str | None
