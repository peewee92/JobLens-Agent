from __future__ import annotations

import pytest

from app.evals.career_loop_latency import (
    LatencyTrajectoryClass,
    measure_loop_latency_baseline,
    percentile,
    render_latency_baseline,
)
from app.evals.career_trajectory import load_career_trajectory_eval_dataset


def test_percentile_matches_known_values() -> None:
    values = (1.0, 2.0, 3.0, 4.0, 5.0)

    assert percentile(values, 0.0) == 1.0
    assert percentile(values, 0.5) == 3.0
    assert percentile(values, 1.0) == 5.0
    assert percentile(values, 0.25) == 2.0
    assert percentile((7.0,), 0.95) == 7.0


def test_percentile_rejects_empty_input_and_bad_quantile() -> None:
    with pytest.raises(ValueError, match="at least one sample"):
        percentile((), 0.5)
    with pytest.raises(ValueError, match="between 0 and 1"):
        percentile((1.0,), 1.5)


def test_baseline_covers_every_measurable_frozen_case() -> None:
    cases = load_career_trajectory_eval_dataset()
    measurable = {case.case_id for case in cases if not case.clock_script}

    report = measure_loop_latency_baseline(cases=cases)

    assert len(cases) == 50
    assert report.sample_count == len(measurable) == 48
    assert {sample.case_id for sample in report.samples} == measurable
    assert report.excluded_virtual_clock_samples == 2


def test_virtual_clock_cases_are_excluded_not_published() -> None:
    """A scripted clock makes latency an artifact, so it must not reach the baseline."""

    cases = load_career_trajectory_eval_dataset()
    virtual = {case.case_id for case in cases if case.clock_script}
    assert virtual == {"traj-timeout-01", "traj-timeout-02"}

    report = measure_loop_latency_baseline(cases=cases)

    assert not (virtual & {sample.case_id for sample in report.samples})
    assert report.excluded_virtual_clock_samples == len(virtual)


def test_baseline_segments_every_trajectory_class() -> None:
    cases = load_career_trajectory_eval_dataset()

    report = measure_loop_latency_baseline(cases=cases)

    assert {item.trajectory_class for item in report.by_class} == {
        item.value for item in LatencyTrajectoryClass
    }
    assert sum(item.sample_count for item in report.by_class) == 48


def test_distribution_ordering_is_sane() -> None:
    cases = load_career_trajectory_eval_dataset()

    report = measure_loop_latency_baseline(cases=cases)

    assert report.min_ms <= report.p50_ms <= report.p95_ms <= report.max_ms
    for item in report.by_class:
        assert item.min_ms <= item.p50_ms <= item.p95_ms <= item.max_ms, item.trajectory_class
        assert item.sample_count > 0


def test_every_latency_sample_is_non_negative() -> None:
    cases = load_career_trajectory_eval_dataset()

    report = measure_loop_latency_baseline(cases=cases)

    assert all(sample.latency_ms >= 0.0 for sample in report.samples)


def test_baseline_records_zero_provider_attempts() -> None:
    cases = load_career_trajectory_eval_dataset()

    report = measure_loop_latency_baseline(cases=cases)

    assert report.provider_attempts == 0
    assert report.provider_completed == 0
    assert all(sample.provider_attempts == 0 for sample in report.samples)


def test_core_reported_and_eval_timed_samples_are_kept_apart() -> None:
    cases = load_career_trajectory_eval_dataset()

    report = measure_loop_latency_baseline(cases=cases)

    dispatch_cases = sum(1 for case in cases if case.driver == "durable_dispatch")
    assert report.eval_timed_samples == dispatch_cases == 8
    assert report.core_reported_samples == len(cases) - dispatch_cases - 2 == 40


def test_terminal_reason_distribution_matches_the_cohort() -> None:
    cases = load_career_trajectory_eval_dataset()

    report = measure_loop_latency_baseline(cases=cases)

    reasons = dict(report.terminal_reason_distribution)
    assert sum(reasons.values()) == 48
    assert reasons["clarification_required"] == 4  # 2 clarification + 2 tool_empty
    assert reasons["blocked"] == 2
    assert reasons["completed"] == 15
    assert reasons["durable_hitl"] == 4
    assert reasons["governed_loop"] == 2
    assert reasons["stale_state"] == 3
    assert reasons["invalid_tool_params"] == 4
    assert reasons["run_cancelled"] == 2
    assert "runtime_timeout" not in reasons  # virtual clock, excluded by design


def test_p95_is_explained_by_the_durable_dispatch_segment() -> None:
    """A P95 that cannot be attributed to a segment is not a baseline.

    The cohort-wide P95 must land inside the durable-dispatch range, and every
    governed-loop segment must stay below it.  If a future change makes the pure
    loop path as slow as the durable HITL fixture, this fails and forces the
    baseline to be re-explained rather than silently re-published.
    """

    cases = load_career_trajectory_eval_dataset()

    report = measure_loop_latency_baseline(cases=cases)

    dispatch = next(
        item for item in report.by_class if item.trajectory_class == "durable_dispatch"
    )
    governed = tuple(
        item for item in report.by_class if item.trajectory_class != "durable_dispatch"
    )
    assert dispatch.max_ms == report.max_ms
    assert dispatch.min_ms <= report.p95_ms <= dispatch.max_ms
    assert max(item.max_ms for item in governed) < dispatch.min_ms


def test_rendered_baseline_names_every_segment() -> None:
    cases = load_career_trajectory_eval_dataset()

    report = measure_loop_latency_baseline(cases=cases)
    rendered = render_latency_baseline(report)

    assert "P95" in rendered
    assert "sample count" in rendered
    assert "Provider attempts : 0" in rendered
    for item in LatencyTrajectoryClass:
        assert item.value in rendered


def test_baseline_requires_at_least_one_case() -> None:
    with pytest.raises(ValueError, match="at least one case"):
        measure_loop_latency_baseline(cases=())
