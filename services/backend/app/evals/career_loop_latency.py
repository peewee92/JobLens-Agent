"""vNext 1.1 Tool Loop latency baseline.

PRD §16 requires "P95 Tool Loop latency 有基线并可解释" -- a baseline that can be
explained, not a bare number.  This module produces that baseline from the frozen
trajectory cohort and reports it segmented by trajectory class, together with the
sample count, the terminal-reason distribution, provider attempts and tool calls.

**Scope and honest limits.** These samples come from the deterministic cohort, so
they measure the *governed loop and durable-dispatch plumbing* only.  They exclude
model latency, which dominates production.  The numbers are therefore a floor, not
a production latency claim.  Model-layer latency requires the separately authorized
provider gate and is deliberately not extrapolated here.

Two measurement sources are reported and never conflated:

- ``measured_by_core`` -- the governed loop's own ``runtime_latency_ms``.
- ``measured_by_eval`` -- wall clock taken by this module around a durable dispatch
  run.  That path builds a throwaway SQLite checkpoint store per case, so its
  latency is an **upper bound** inflated by fixture I/O, not a product figure.

No latency threshold is asserted as a gate: wall-clock assertions are flaky and
would make the release gate untrustworthy.  The tests assert coverage and
distribution sanity instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.evals.career_trajectory import (
    CareerTrajectoryEvalCase,
    CareerTrajectoryEvalDriver,
)


class LatencyTrajectoryClass(StrEnum):
    CLARIFICATION = "clarification"
    SINGLE_TOOL = "single_tool"
    MULTI_TOOL = "multi_tool"
    RETRY_OR_RECOVERY = "retry_or_recovery"
    FAILURE = "failure"
    DURABLE_DISPATCH = "durable_dispatch"


_FAMILY_TO_CLASS: dict[str, LatencyTrajectoryClass] = {
    "clarification": LatencyTrajectoryClass.CLARIFICATION,
    "tool_empty": LatencyTrajectoryClass.CLARIFICATION,
    "completed_single": LatencyTrajectoryClass.SINGLE_TOOL,
    "completed_multi": LatencyTrajectoryClass.MULTI_TOOL,
    "completed_triple": LatencyTrajectoryClass.MULTI_TOOL,
    "transient_retry": LatencyTrajectoryClass.RETRY_OR_RECOVERY,
    "corrected_retry": LatencyTrajectoryClass.RETRY_OR_RECOVERY,
    "unknown_tool_replan": LatencyTrajectoryClass.RETRY_OR_RECOVERY,
    "stale_terminate": LatencyTrajectoryClass.FAILURE,
    "budget_exhausted": LatencyTrajectoryClass.FAILURE,
    "runtime_timeout": LatencyTrajectoryClass.FAILURE,
    "run_cancelled": LatencyTrajectoryClass.FAILURE,
    "loop_detected": LatencyTrajectoryClass.FAILURE,
    "invalid_tool_params": LatencyTrajectoryClass.FAILURE,
    "invalid_intent_output": LatencyTrajectoryClass.FAILURE,
    "unsupported": LatencyTrajectoryClass.FAILURE,
    "blocked": LatencyTrajectoryClass.FAILURE,
    "durable_dispatch": LatencyTrajectoryClass.DURABLE_DISPATCH,
}


@dataclass(frozen=True, slots=True)
class LatencySample:
    case_id: str
    family: str
    trajectory_class: str
    terminal_reason: str
    latency_ms: float
    tool_calls: int
    provider_attempts: int
    workflow_invocations: int
    measured_by_core: bool


@dataclass(frozen=True, slots=True)
class LatencyDistribution:
    trajectory_class: str
    sample_count: int
    min_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float
    terminal_reasons: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class LatencyBaselineReport:
    sample_count: int
    min_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float
    provider_attempts: int
    provider_completed: int
    tool_calls: int
    core_reported_samples: int
    eval_timed_samples: int
    excluded_virtual_clock_samples: int
    terminal_reason_distribution: tuple[tuple[str, int], ...]
    by_class: tuple[LatencyDistribution, ...]
    samples: tuple[LatencySample, ...]


def percentile(values: tuple[float, ...], quantile: float) -> float:
    """Linear-interpolation percentile over a sorted copy.

    ``quantile`` is in [0, 1].  A single sample returns itself; an empty input
    raises, because a percentile of nothing is not zero, it is unknown.
    """

    if not values:
        raise ValueError("percentile requires at least one sample")
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be between 0 and 1")

    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * (len(ordered) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction


def measure_loop_latency_baseline(
    *,
    cases: tuple[CareerTrajectoryEvalCase, ...],
    driver: CareerTrajectoryEvalDriver | None = None,
    warm_up: bool = True,
) -> LatencyBaselineReport:
    """Measure one latency sample per case and aggregate the baseline.

    One warm-up pass is discarded by default so first-run import, SQLite and file
    system costs do not dominate the sample.  Each measured sample is taken from
    the driver's first replay run; the second replay run exists for determinism
    checking and is not the reported measurement.

    Cases that inject a virtual monotonic clock are **excluded**, not measured:
    their ``runtime_latency_ms`` is an artifact of the scripted clock, so
    publishing it would put a fictional number into the baseline.  The exclusion
    count is reported so the sample size stays auditable.
    """

    if not cases:
        raise ValueError("latency baseline requires at least one case")

    active_driver = driver or CareerTrajectoryEvalDriver()
    measurable = tuple(case for case in cases if not case.clock_script)
    excluded = len(cases) - len(measurable)

    if warm_up:
        for case in measurable:
            active_driver.run(case=case)

    samples: list[LatencySample] = []
    for case in measurable:
        execution = active_driver.run(case=case)
        if execution.unclassified_error is not None:
            raise ValueError(
                f"{case.case_id}: latency baseline cannot measure an unclassified failure: "
                f"{execution.unclassified_error}"
            )
        measured_by_core = case.driver == "governed_loop"
        samples.append(
            LatencySample(
                case_id=case.case_id,
                family=case.family,
                trajectory_class=_class_for_family(case.family).value,
                terminal_reason=execution.terminal_reason or "unknown",
                latency_ms=execution.runtime_latency_ms,
                tool_calls=execution.workflow_invocations,
                provider_attempts=execution.provider_attempts,
                workflow_invocations=execution.workflow_invocations,
                measured_by_core=measured_by_core,
            )
        )

    return _build_report(tuple(samples), excluded_virtual_clock_samples=excluded)


def _class_for_family(family: str) -> LatencyTrajectoryClass:
    try:
        return _FAMILY_TO_CLASS[family]
    except KeyError as exc:  # pragma: no cover - loader keeps families closed
        raise ValueError(f"no latency trajectory class for family {family!r}") from exc


def _build_report(
    samples: tuple[LatencySample, ...],
    *,
    excluded_virtual_clock_samples: int,
) -> LatencyBaselineReport:
    latencies = tuple(sample.latency_ms for sample in samples)
    by_class: list[LatencyDistribution] = []
    for trajectory_class in LatencyTrajectoryClass:
        members = tuple(
            sample for sample in samples if sample.trajectory_class == trajectory_class.value
        )
        if not members:
            continue
        member_latencies = tuple(sample.latency_ms for sample in members)
        by_class.append(
            LatencyDistribution(
                trajectory_class=trajectory_class.value,
                sample_count=len(members),
                min_ms=min(member_latencies),
                p50_ms=percentile(member_latencies, 0.50),
                p95_ms=percentile(member_latencies, 0.95),
                max_ms=max(member_latencies),
                terminal_reasons=_counter(members),
            )
        )

    return LatencyBaselineReport(
        sample_count=len(samples),
        min_ms=min(latencies),
        p50_ms=percentile(latencies, 0.50),
        p95_ms=percentile(latencies, 0.95),
        max_ms=max(latencies),
        provider_attempts=sum(sample.provider_attempts for sample in samples),
        provider_completed=0,
        tool_calls=sum(sample.tool_calls for sample in samples),
        core_reported_samples=sum(1 for sample in samples if sample.measured_by_core),
        eval_timed_samples=sum(1 for sample in samples if not sample.measured_by_core),
        excluded_virtual_clock_samples=excluded_virtual_clock_samples,
        terminal_reason_distribution=_counter(samples),
        by_class=tuple(by_class),
        samples=samples,
    )


def _counter(samples: tuple[LatencySample, ...]) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for sample in samples:
        counts[sample.terminal_reason] = counts.get(sample.terminal_reason, 0) + 1
    return tuple(sorted(counts.items()))


def render_latency_baseline(report: LatencyBaselineReport) -> str:
    """Render the baseline as a human-readable, PRD-citable block."""

    lines = [
        "vNext 1.1 Tool Loop latency baseline (deterministic cohort)",
        f"  sample count      : {report.sample_count}",
        f"  P50               : {report.p50_ms:.3f} ms",
        f"  P95               : {report.p95_ms:.3f} ms",
        f"  max               : {report.max_ms:.3f} ms",
        f"  min               : {report.min_ms:.3f} ms",
        f"  tool calls        : {report.tool_calls}",
        f"  Provider attempts : {report.provider_attempts}",
        f"  measured by Core  : {report.core_reported_samples}",
        f"  measured by Eval  : {report.eval_timed_samples} (durable dispatch, fixture I/O included)",
        f"  excluded (virtual clock): {report.excluded_virtual_clock_samples}",
        "  terminal reasons  : "
        + ", ".join(f"{reason}={count}" for reason, count in report.terminal_reason_distribution),
        "  by trajectory class:",
    ]
    for item in report.by_class:
        lines.append(
            f"    {item.trajectory_class:<18} n={item.sample_count:<3} "
            f"min={item.min_ms:8.3f}  p50={item.p50_ms:8.3f}  "
            f"p95={item.p95_ms:8.3f}  max={item.max_ms:8.3f} ms"
        )
    return "\n".join(lines)


__all__ = [
    "LatencyBaselineReport",
    "LatencyDistribution",
    "LatencySample",
    "LatencyTrajectoryClass",
    "measure_loop_latency_baseline",
    "percentile",
    "render_latency_baseline",
]
