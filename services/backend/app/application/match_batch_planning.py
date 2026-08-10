"""Read-only planning for a future Phase 5 batch Match queue."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from app.application.match_inputs.readiness import MatchInputReadiness


class MatchReadinessGate(Protocol):
    def execute(self, job_id: str) -> MatchInputReadiness: ...


class BatchMatchPlanStatus(StrEnum):
    READY = "ready"
    INPUT_BLOCKED = "input_blocked"
    PERSISTENCE_BLOCKED = "persistence_blocked"


@dataclass(frozen=True, slots=True)
class BatchMatchPlanItem:
    job_id: str
    status: BatchMatchPlanStatus
    blocker_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BatchMatchPlan:
    total: int
    ready_count: int
    input_blocked_count: int
    persistence_blocked_count: int
    items: tuple[BatchMatchPlanItem, ...]
    db_writes: int = 0
    provider_calls: int = 0
    trace_runs_created: int = 0


class PlanBatchMatchUseCase:
    """Classify requested jobs without executing Eligibility or Semantic Match."""

    def __init__(
        self,
        *,
        readiness_gate: MatchReadinessGate,
        persistence_ready: Callable[[], bool],
    ) -> None:
        self._readiness_gate = readiness_gate
        self._persistence_ready = persistence_ready

    def execute(self, job_ids: tuple[str, ...]) -> BatchMatchPlan:
        unique_job_ids = tuple(dict.fromkeys(job_ids))
        if not unique_job_ids:
            return BatchMatchPlan(
                total=0,
                ready_count=0,
                input_blocked_count=0,
                persistence_blocked_count=0,
                items=(),
            )

        persistence_ready = self._persistence_ready()
        items: list[BatchMatchPlanItem] = []
        for job_id in unique_job_ids:
            readiness = self._readiness_gate.execute(job_id)
            if not readiness.inputs_release_eligible:
                items.append(
                    BatchMatchPlanItem(
                        job_id=job_id,
                        status=BatchMatchPlanStatus.INPUT_BLOCKED,
                        blocker_codes=tuple(
                            _blocker_code(item.code) for item in readiness.blockers
                        ),
                    )
                )
                continue
            if not persistence_ready:
                items.append(
                    BatchMatchPlanItem(
                        job_id=job_id,
                        status=BatchMatchPlanStatus.PERSISTENCE_BLOCKED,
                        blocker_codes=("match_report_persistence_not_ready",),
                    )
                )
                continue
            items.append(
                BatchMatchPlanItem(
                    job_id=job_id,
                    status=BatchMatchPlanStatus.READY,
                    blocker_codes=(),
                )
            )

        result_items = tuple(items)
        return BatchMatchPlan(
            total=len(result_items),
            ready_count=sum(
                item.status is BatchMatchPlanStatus.READY for item in result_items
            ),
            input_blocked_count=sum(
                item.status is BatchMatchPlanStatus.INPUT_BLOCKED
                for item in result_items
            ),
            persistence_blocked_count=sum(
                item.status is BatchMatchPlanStatus.PERSISTENCE_BLOCKED
                for item in result_items
            ),
            items=result_items,
        )


def _blocker_code(code: object) -> str:
    value = getattr(code, "value", code)
    return str(value)
