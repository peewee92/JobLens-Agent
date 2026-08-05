"""Explicit live Requirement Canary operator boundary tests."""
from __future__ import annotations

from dataclasses import replace
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.application.requirement_acceptance.errors import (
    RequirementAcceptanceExecutionLeaseUnavailableError,
)
from app.application.requirement_acceptance.live_canary_operator import (
    RequirementAcceptanceCanaryOperatorState,
    evaluate_requirement_acceptance_canary_operator,
)
from app.application.requirement_acceptance.models import (
    RequirementAcceptanceCaseStatus,
)
from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessNextAction,
    RequirementAcceptanceReadinessResult,
)
from app.application.requirement_acceptance.runs import (
    RequirementAcceptancePreflight,
    RequirementAcceptanceRunCaseStatus,
)
import scripts.operate_requirement_acceptance_canary as operator_cli

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


def _preflight() -> RequirementAcceptancePreflight:
    return RequirementAcceptancePreflight(
        dataset_fingerprint="a" * 64,
        source_version="1.4.5",
        generated_at="2026-08-04T08:31:15.681Z",
        selected_count=20,
        total_description_characters=20_000,
        minimum_description_characters=500,
        maximum_description_characters=1_500,
        average_description_characters=1_000.0,
    )


def _readiness(
    *,
    next_action: RequirementAcceptanceReadinessNextAction = (
        RequirementAcceptanceReadinessNextAction.RUN_CANARY
    ),
    allowed: bool = True,
    attempted_calls: int = 0,
    requested: int = 3,
    run_id: str | None = None,
) -> RequirementAcceptanceReadinessResult:
    return RequirementAcceptanceReadinessResult(
        dataset_fingerprint="a" * 64,
        source_version="1.4.5",
        selected_count=20,
        provider="openai",
        model="gpt-test",
        api_key_configured=True,
        reviewer="will",
        title="Real Requirement acceptance",
        requested_max_new_extractions=requested,
        database_reachable=True,
        database_revision="head",
        migration_head="head",
        workflow_ready=True,
        provider_execution_allowed=allowed,
        ready_for_next_action=(
            allowed
            or next_action
            in {
                RequirementAcceptanceReadinessNextAction.REVIEW_CANARY,
                RequirementAcceptanceReadinessNextAction.OPEN_MANUAL_REVIEW,
            }
        ),
        next_action=next_action,
        run_id=run_id,
        run_status="partial" if run_id else None,
        attempted_calls=attempted_calls,
        canary_decision=None,
        batch_id=None,
        workbench_url=(
            f"http://localhost:3000/evals/requirements/canary/{run_id}"
            if run_id
            else None
        ),
        manual_review_url=None,
        blockers=(),
    )


def _case(
    index: int,
    *,
    attempt_count: int,
    trace_run_id: str | None,
    extraction_id: str | None = None,
    status: RequirementAcceptanceRunCaseStatus = (
        RequirementAcceptanceRunCaseStatus.EXTRACTED
    ),
):
    return SimpleNamespace(
        id=f"case_{index}",
        case_index=index,
        job_id=f"job_{index}",
        status=status,
        attempt_count=attempt_count,
        extraction_id=extraction_id,
        trace_run_id=trace_run_id,
        error_code=None,
    )


def _run(*cases, attempted_calls: int):
    return SimpleNamespace(
        id="run_1",
        attempted_calls=attempted_calls,
        cases=tuple(cases),
    )


def _preparation(*, failed: int = 0):
    case = SimpleNamespace(
        input_index=0,
        job_id="job_0",
        title="Agent Engineer",
        company="Example",
        status=(
            RequirementAcceptanceCaseStatus.FAILED
            if failed
            else RequirementAcceptanceCaseStatus.EXTRACTED
        ),
        extraction_id=None if failed else "extraction_0",
        trace_run_id="trace_0",
        error_code="provider_error" if failed else None,
        error_message="provider failed" if failed else None,
    )
    return SimpleNamespace(
        run_id="run_1",
        dataset_fingerprint="a" * 64,
        import_id="import_1",
        source_version="1.4.5",
        received=20,
        created_jobs=20,
        updated_jobs=0,
        reused_extractions=0,
        created_extractions=0 if failed else 1,
        failed_extractions=failed,
        deferred_extractions=19,
        max_new_extractions=1,
        provider="openai",
        model="gpt-test",
        extractor_version="requirement-extractor-v1",
        prompt_version="requirement-extraction-v1",
        batch_id=None,
        batch_reused=False,
        ready_for_manual_review=False,
        cases=(case,),
    )


def _args(
    *,
    dataset: Path,
    private_root: Path,
    execute: bool,
    confirmed: bool,
    session_manifest: Path | None = None,
    max_new_extractions: int = 1,
):
    return SimpleNamespace(
        dataset=dataset,
        reviewer="will",
        title="Real Requirement acceptance",
        max_new_extractions=max_new_extractions,
        web_base_url="http://localhost:3000",
        private_root=private_root,
        session_manifest=session_manifest,
        execute_canary=execute,
        confirm_live_cost_and_human_review=confirmed,
        json=True,
    )


def test_operator_policy_separates_ready_plan_from_explicit_authorization(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    manifest = private_root / "session-manifests" / "session.json"

    plan = evaluate_requirement_acceptance_canary_operator(
        readiness=_readiness(requested=3),
        dataset_path=dataset,
        expected_dataset_path=dataset,
        private_root=private_root,
        session_manifest_path=manifest,
        execute_requested=False,
        live_cost_confirmed=False,
    )
    assert plan.state is RequirementAcceptanceCanaryOperatorState.READY_FOR_EXPLICIT_EXECUTION
    assert plan.plan_ready is True
    assert plan.execution_authorized is False
    assert plan.blockers == ()

    missing_confirmation = evaluate_requirement_acceptance_canary_operator(
        readiness=_readiness(requested=3),
        dataset_path=dataset,
        expected_dataset_path=dataset,
        private_root=private_root,
        session_manifest_path=manifest,
        execute_requested=True,
        live_cost_confirmed=False,
    )
    assert missing_confirmation.plan_ready is True
    assert missing_confirmation.execution_authorized is False
    assert {item.code for item in missing_confirmation.blockers} == {
        "live_cost_confirmation_missing"
    }

    authorized = evaluate_requirement_acceptance_canary_operator(
        readiness=_readiness(requested=3),
        dataset_path=dataset,
        expected_dataset_path=dataset,
        private_root=private_root,
        session_manifest_path=manifest,
        execute_requested=True,
        live_cost_confirmed=True,
    )
    assert authorized.state is RequirementAcceptanceCanaryOperatorState.AUTHORIZED
    assert authorized.execution_authorized is True


def test_operator_policy_rejects_datasetless_dashboard_readiness(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    readiness = replace(
        _readiness(requested=1),
        dataset_fingerprint=None,
        source_version=None,
    )

    plan = evaluate_requirement_acceptance_canary_operator(
        readiness=readiness,
        dataset_path=dataset,
        expected_dataset_path=dataset,
        private_root=private_root,
        session_manifest_path=None,
        execute_requested=True,
        live_cost_confirmed=True,
    )

    assert plan.state is RequirementAcceptanceCanaryOperatorState.BLOCKED
    assert "formal_dataset_identity_missing" in {
        item.code for item in plan.blockers
    }
    assert plan.execution_authorized is False


def test_operator_policy_requires_canonical_private_handoff_and_run_canary_action(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"
    expected = private_root / "datasets" / f"formal-{'a' * 16}.json"
    outside = tmp_path / "upload.json"

    plan = evaluate_requirement_acceptance_canary_operator(
        readiness=_readiness(
            next_action=RequirementAcceptanceReadinessNextAction.REVIEW_CANARY,
            allowed=False,
            attempted_calls=3,
            run_id="run_1",
        ),
        dataset_path=outside,
        expected_dataset_path=expected,
        private_root=private_root,
        session_manifest_path=tmp_path / "outside-manifest.json",
        execute_requested=True,
        live_cost_confirmed=True,
    )
    codes = {item.code for item in plan.blockers}
    assert plan.state is RequirementAcceptanceCanaryOperatorState.BLOCKED
    assert "dataset_outside_private_root" in codes
    assert "dataset_not_canonical_private_handoff" in codes
    assert "session_manifest_outside_private_root" in codes
    assert "next_action_is_not_run_canary" in codes
    assert "provider_execution_not_allowed" in codes


def _patch_common(
    monkeypatch,
    *,
    args,
    readiness_sequence,
    run_after=None,
) -> None:
    args.dataset.parent.mkdir(parents=True, exist_ok=True)
    args.dataset.write_text('{"formal":true}', encoding="utf-8")
    monkeypatch.setattr(operator_cli, "PRIVATE_DATA_ROOT", args.private_root.parent.resolve())
    monkeypatch.setattr(operator_cli, "_arguments", lambda: args)
    monkeypatch.setattr(operator_cli, "_load_payload", lambda _path: {"formal": True})
    monkeypatch.setattr(
        operator_cli,
        "preflight_requirement_acceptance_dataset",
        lambda _payload: _preflight(),
    )
    monkeypatch.setattr(
        operator_cli,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="sqlite:///unused.db",
            requirement_extractor_provider="openai",
            requirement_extractor_model="gpt-test",
            openai_api_key="test-key-not-a-real-secret",
        ),
    )
    sequence = iter(readiness_sequence)
    monkeypatch.setattr(operator_cli, "_assess_readiness", lambda **_kwargs: next(sequence))
    if run_after is not None:
        monkeypatch.setattr(operator_cli, "_existing_run", lambda **_kwargs: run_after)


def test_plan_mode_never_builds_or_executes_provider_use_case(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=False, confirmed=False)
    _patch_common(monkeypatch, args=args, readiness_sequence=[(_readiness(requested=1), None)])

    monkeypatch.setattr(
        operator_cli,
        "_build_use_case",
        lambda: (_ for _ in ()).throw(AssertionError("provider runtime must not build")),
    )
    monkeypatch.setattr(
        operator_cli,
        "_write_manifest",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("implicit plan must not write")),
    )

    assert operator_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "ready_for_explicit_execution"
    assert body["operator"]["executionAuthorized"] is False
    assert body["liveExtractionAttemptsObserved"] == 0
    assert body["automaticCanaryDecisionSubmitted"] is False


def test_execute_requires_confirmation_before_runtime_is_built(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=False)
    _patch_common(monkeypatch, args=args, readiness_sequence=[(_readiness(requested=1), None)])
    writes = []
    monkeypatch.setattr(operator_cli, "_write_manifest", lambda **kwargs: writes.append(kwargs))
    monkeypatch.setattr(
        operator_cli,
        "_build_use_case",
        lambda: (_ for _ in ()).throw(AssertionError("runtime must not build")),
    )

    assert operator_cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "blocked"
    assert {item["code"] for item in body["operator"]["blockers"]} == {
        "live_cost_confirmation_missing"
    }
    assert len(writes) == 1


def test_concurrent_execution_lease_conflict_is_reported_before_post_readiness(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[(_readiness(requested=1), None)],
    )

    def raise_conflict(**_kwargs):
        raise RequirementAcceptanceExecutionLeaseUnavailableError(
            "another execution already owns this identity"
        )

    fake_use_case = SimpleNamespace(execute=raise_conflict)
    monkeypatch.setattr(operator_cli, "_build_use_case", lambda: (fake_use_case, object()))
    monkeypatch.setattr(operator_cli, "_write_manifest", lambda **_kwargs: None)

    assert operator_cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "execution_rejected"
    assert body["executionError"] == {
        "type": "RequirementAcceptanceExecutionLeaseUnavailableError",
        "message": "another execution already owns this identity",
    }
    assert body["preparation"] is None
    assert body["postReadiness"] is None
    assert body["liveExtractionAttemptsObserved"] == 0


def test_confirmed_execute_records_new_case_extraction_and_trace_without_auto_decision(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    post_run = _run(
        _case(0, attempt_count=1, trace_run_id="trace_0", extraction_id="extraction_0"),
        attempted_calls=1,
    )
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[
            (_readiness(requested=1), None),
            (_readiness(requested=2, attempted_calls=1, run_id="run_1"), post_run),
        ],
        run_after=post_run,
    )
    fake_use_case = SimpleNamespace(execute=lambda **_kwargs: _preparation())
    monkeypatch.setattr(operator_cli, "_build_use_case", lambda: (fake_use_case, object()))
    writes = []
    monkeypatch.setattr(operator_cli, "_write_manifest", lambda **kwargs: writes.append(kwargs))

    assert operator_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "completed"
    assert body["liveExtractionAttemptsObserved"] == 1
    assert body["newAttemptEvidence"] == [
        {
            "caseId": "case_0",
            "caseIndex": 0,
            "jobId": "job_0",
            "status": "extracted",
            "attemptDelta": 1,
            "extractionId": "extraction_0",
            "traceRunId": "trace_0",
            "errorCode": None,
        }
    ]
    assert body["missingTraceCaseIds"] == []
    assert body["manualHumanDecisionRequired"] is False
    assert body["automaticCanaryDecisionSubmitted"] is False
    assert len(writes) == 2


def test_third_attempt_returns_human_workbench_and_never_submits_decision(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    before_run = _run(
        _case(0, attempt_count=1, trace_run_id="trace_0", extraction_id="extraction_0"),
        _case(1, attempt_count=1, trace_run_id="trace_1", extraction_id="extraction_1"),
        attempted_calls=2,
    )
    post_run = _run(
        _case(0, attempt_count=1, trace_run_id="trace_0", extraction_id="extraction_0"),
        _case(1, attempt_count=1, trace_run_id="trace_1", extraction_id="extraction_1"),
        _case(2, attempt_count=1, trace_run_id="trace_2", extraction_id="extraction_2"),
        attempted_calls=3,
    )
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[
            (_readiness(requested=1, attempted_calls=2, run_id="run_1"), before_run),
            (
                _readiness(
                    next_action=RequirementAcceptanceReadinessNextAction.REVIEW_CANARY,
                    allowed=False,
                    requested=1,
                    attempted_calls=3,
                    run_id="run_1",
                ),
                post_run,
            ),
        ],
        run_after=post_run,
    )
    fake_use_case = SimpleNamespace(execute=lambda **_kwargs: _preparation())
    monkeypatch.setattr(operator_cli, "_build_use_case", lambda: (fake_use_case, object()))
    monkeypatch.setattr(operator_cli, "_write_manifest", lambda **_kwargs: None)

    assert operator_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["liveExtractionAttemptsObserved"] == 1
    assert body["manualHumanDecisionRequired"] is True
    assert body["workbenchUrl"].endswith("/evals/requirements/canary/run_1")
    assert body["automaticCanaryDecisionSubmitted"] is False
    assert body["postReadiness"]["nextAction"] == "review_canary"
    assert body["postReadiness"]["recommendedCommand"] is None


def test_attempt_delta_above_explicit_budget_requires_attention(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    post_run = _run(
        _case(0, attempt_count=1, trace_run_id="trace_0", extraction_id="extraction_0"),
        _case(1, attempt_count=1, trace_run_id="trace_1", extraction_id="extraction_1"),
        attempted_calls=2,
    )
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[
            (_readiness(requested=1), None),
            (_readiness(requested=1, attempted_calls=2, run_id="run_1"), post_run),
        ],
        run_after=post_run,
    )
    fake_use_case = SimpleNamespace(execute=lambda **_kwargs: _preparation())
    monkeypatch.setattr(operator_cli, "_build_use_case", lambda: (fake_use_case, object()))
    monkeypatch.setattr(operator_cli, "_write_manifest", lambda **_kwargs: None)

    assert operator_cli.main() == 1
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "completed_with_attention_required"
    assert body["liveExtractionAttemptsObserved"] == 2
    assert body["attemptBudgetExceeded"] is True
    assert body["automaticCanaryDecisionSubmitted"] is False


def test_missing_trace_or_provider_failure_requires_attention(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    post_run = _run(
        _case(
            0,
            attempt_count=1,
            trace_run_id=None,
            extraction_id=None,
            status=RequirementAcceptanceRunCaseStatus.FAILED,
        ),
        attempted_calls=1,
    )
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[
            (_readiness(requested=1), None),
            (_readiness(requested=2, attempted_calls=1, run_id="run_1"), post_run),
        ],
        run_after=post_run,
    )
    fake_use_case = SimpleNamespace(execute=lambda **_kwargs: _preparation(failed=1))
    monkeypatch.setattr(operator_cli, "_build_use_case", lambda: (fake_use_case, object()))
    monkeypatch.setattr(operator_cli, "_write_manifest", lambda **_kwargs: None)

    assert operator_cli.main() == 1
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "completed_with_attention_required"
    assert body["missingTraceCaseIds"] == ["case_0"]
    assert body["automaticCanaryDecisionSubmitted"] is False


def test_dataset_outside_private_root_is_rejected_before_json_is_read(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = tmp_path / "uploaded.json"
    dataset.write_text('{"formal":true}', encoding="utf-8")
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    monkeypatch.setattr(operator_cli, "PRIVATE_DATA_ROOT", private_root.parent.resolve())
    monkeypatch.setattr(operator_cli, "_arguments", lambda: args)
    monkeypatch.setattr(
        operator_cli,
        "_load_payload",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("outside-private dataset must not be parsed")
        ),
    )
    monkeypatch.setattr(
        operator_cli,
        "_build_use_case",
        lambda: (_ for _ in ()).throw(AssertionError("runtime must not execute")),
    )

    assert operator_cli.main() == 2
    output = capsys.readouterr().out
    assert "must be staged under" in output


def test_blocked_readiness_or_noncanonical_dataset_never_writes_or_executes(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / "uploaded.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[
            (
                _readiness(
                    next_action=RequirementAcceptanceReadinessNextAction.FIX_BLOCKERS,
                    allowed=False,
                    requested=1,
                ),
                None,
            )
        ],
    )
    monkeypatch.setattr(
        operator_cli,
        "_write_manifest",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("blocked plan must not write")),
    )
    monkeypatch.setattr(
        operator_cli,
        "_build_use_case",
        lambda: (_ for _ in ()).throw(AssertionError("blocked plan must not execute")),
    )

    assert operator_cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "blocked"
    codes = {item["code"] for item in body["operator"]["blockers"]}
    assert "dataset_not_canonical_private_handoff" in codes
    assert "next_action_is_not_run_canary" in codes
    assert body["sessionManifestPath"] is None


def test_manifest_write_rechecks_private_root_after_late_symlink_escape(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"
    outside = tmp_path / "tracked"
    private_root.mkdir()
    outside.mkdir()
    (private_root / "session-manifests").symlink_to(
        outside,
        target_is_directory=True,
    )
    manifest = private_root / "session-manifests" / "session.json"

    try:
        operator_cli._write_manifest(
            path=manifest,
            private_root=private_root,
            readiness=_readiness(requested=1),
            existing_run=None,
            dataset=private_root / "datasets" / f"formal-{'a' * 16}.json",
            recommended_command=None,
        )
    except operator_cli.RequirementAcceptanceCanaryOperatorError as error:
        assert "escaped" in str(error)
    else:  # pragma: no cover - explicit safety assertion
        raise AssertionError("late symlink escape must be rejected")


def test_post_readiness_failure_preserves_first_successful_run_snapshot(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    post_run = _run(
        _case(0, attempt_count=1, trace_run_id="trace_0", extraction_id="extraction_0"),
        attempted_calls=1,
    )
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[
            (_readiness(requested=1), None),
            (
                _readiness(
                    next_action=RequirementAcceptanceReadinessNextAction.FIX_BLOCKERS,
                    allowed=False,
                    requested=1,
                    attempted_calls=1,
                    run_id="run_1",
                ),
                None,
            ),
        ],
        run_after=post_run,
    )
    fake_use_case = SimpleNamespace(execute=lambda **_kwargs: _preparation())
    monkeypatch.setattr(operator_cli, "_build_use_case", lambda: (fake_use_case, object()))
    monkeypatch.setattr(operator_cli, "_write_manifest", lambda **_kwargs: None)

    assert operator_cli.main() == 1
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "completed_with_attention_required"
    assert body["liveExtractionAttemptsObserved"] == 1
    assert body["newAttemptEvidence"][0]["traceRunId"] == "trace_0"
    assert body["postReadiness"]["nextAction"] == "fix_blockers"
    assert body["automaticCanaryDecisionSubmitted"] is False


def test_post_execution_run_read_failure_keeps_attempt_count_unknown(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[(_readiness(requested=1), None)],
    )
    fake_use_case = SimpleNamespace(execute=lambda **_kwargs: _preparation())
    monkeypatch.setattr(operator_cli, "_build_use_case", lambda: (fake_use_case, object()))
    monkeypatch.setattr(
        operator_cli,
        "_existing_run",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("temporary read failure")),
    )
    monkeypatch.setattr(operator_cli, "_write_manifest", lambda **_kwargs: None)

    assert operator_cli.main() == 1
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "completed_with_attention_required"
    assert body["liveExtractionAttemptsObserved"] is None
    assert body["postExecutionEvidenceError"]["type"] == "RuntimeError"
    assert body["preparation"]["runId"] == "run_1"
    assert body["sessionManifestWrittenBeforeExecution"] is True
    assert body["sessionManifestUpdatedAfterExecution"] is False
    assert body["automaticCanaryDecisionSubmitted"] is False


def test_post_execution_manifest_failure_is_not_reported_as_clean_completion(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    post_run = _run(
        _case(0, attempt_count=1, trace_run_id="trace_0", extraction_id="extraction_0"),
        attempted_calls=1,
    )
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[
            (_readiness(requested=1), None),
            (_readiness(requested=2, attempted_calls=1, run_id="run_1"), post_run),
        ],
        run_after=post_run,
    )
    fake_use_case = SimpleNamespace(execute=lambda **_kwargs: _preparation())
    monkeypatch.setattr(operator_cli, "_build_use_case", lambda: (fake_use_case, object()))
    writes = iter([None, OSError("disk full")])

    def write_manifest(**_kwargs):
        outcome = next(writes)
        if isinstance(outcome, OSError):
            raise outcome

    monkeypatch.setattr(operator_cli, "_write_manifest", write_manifest)

    assert operator_cli.main() == 1
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "completed_with_attention_required"
    assert body["sessionManifestWrittenBeforeExecution"] is True
    assert body["sessionManifestUpdatedAfterExecution"] is False
    assert body["postExecutionManifestError"] == "OSError"
    assert body["postReadiness"]["sessionManifestPath"] is None
    assert body["liveExtractionAttemptsObserved"] == 1


def test_operator_source_has_no_human_decision_or_resume_execution() -> None:
    source = Path(operator_cli.__file__).read_text(encoding="utf-8")
    assert "ReviewRequirementAcceptanceCanaryUseCase" not in source
    assert "RequirementAcceptanceCanaryDecision.CONTINUE" not in source
    assert "RequirementAcceptanceCanaryDecision.STOP" not in source
    assert "--allow-fixture" not in source
    assert "except Exception" not in source
