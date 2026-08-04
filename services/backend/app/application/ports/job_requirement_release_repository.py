"""Read port for immutable Trace facts used by Requirement release policy."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class JobRequirementTraceFact:
    trace_run_id: str
    capability: str
    version: str
    model: str
    prompt_version: str
    input_refs: dict[str, Any]
    output: dict[str, Any] | None
    error: str | None


class AbstractJobRequirementReleaseQueryRepository(ABC):
    @abstractmethod
    def get_trace(self, trace_run_id: str) -> JobRequirementTraceFact | None:
        raise NotImplementedError
