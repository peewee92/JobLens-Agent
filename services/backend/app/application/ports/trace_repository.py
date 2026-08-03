"""Application-owned trace persistence port."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.tracing import TraceWrite


class AbstractTraceRepository(ABC):
    @abstractmethod
    def add(self, trace: TraceWrite) -> None:
        raise NotImplementedError
