"""Controlled post-Continue Requirement acceptance resume operator tests."""
from __future__ import annotations

from dataclasses import replace
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.application.requirement_acceptance.controlled_resume_operator import (
    RequirementAcceptanceResumeOperatorState,
    evaluate_requirement_acceptance_resume_operator,
)
from app.application.requirement_acceptance.errors import (
    RequirementAcceptanceExecutionLeaseLostError,
    RequirementAcceptanceExecutionLeaseUnavailableError,
)
from app.application.requirement_acceptance.models import (
    RequirementAcceptanceCaseStatus,
)
from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessNextAction,
    RequirementAcceptanceReadinessResult,
)
from app.application.requirement_acceptance.runs import (
    RequirementAcceptanceCanaryDecision,
    RequirementAcceptancePreflight,
    RequirementAcceptanceRunCaseStatus,
)
import scripts.operate_requirement_acceptance_resume as resume_cli

NOW = datetime(2026, 8, 5, 5, 0, tzinfo=timezone.utc)


def _preflight() -> RequirementAcceptancePreflight:
    return RequirementAcceptancePreflight(
        dataset_fingerprint="a" * 64,
        source_version="1.4.6",
        generated_at="2026-08-05T05:00:00Z",
        selected_count=20,
        total_description_characters=20_000,
        minimum_description_characters=500,
        maximum_description_characters=1_500,
        average_description_characters=1_000.0,
    )


def _readiness(
    *,
    next_action: RequirementAcceptanceReadinessNextAction = (
        RequirementAcceptanceReadinessNextAction.RESUME_RUN
    ),
    allowed: bool = True,
    requested: int = 2,
    attempted_calls: int = 3,
    run_id: str | None = "run_1",
    batch_id: str | None = None,
) -> RequirementAcceptanceReadinessResult:
    return RequirementAcceptanceReadinessResult(
        dataset_fingerprint="a" * 64,
        source_version="1.4.6",
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
        run_status="ready" if batch_id else "partial",
        attempted_calls=attempted_calls,
        canary_decision=RequirementAcceptanceCanaryDecision.CONTINUE,
        batch_id=batch_id,
        workbench_url=(
            f"http://localhost:3000/evals/requirements/canary/{run_id}"
            if run_id
            else None
        ),
        manual_review_url=(
            f"http://localhost:3000/evals/requirements/manual/{batch_id}"
            if batch_id
            else None
        ),
        blockers=(),
    )


def _case(index: int, *, completed: bool) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"case_{index}",
        case_index=index,
        job_id=f"job_{index}",
        status=(
            RequirementAcceptanceRunCaseStatus.EXTRACTED
            if completed
            else RequirementAcceptanceRunCaseStatus.DEFERRED
        ),
        attempt_count=1 if completed else 0,
        extraction_id=f"extraction_{index}" if completed else None,
        trace_run_id=f"trace_{index}" if completed else None,
        error_code=None,
        was_attempted=completed,
    )


def _review(
    *,
    decision: RequirementAcceptanceCanaryDecision = (
        RequirementAcceptanceCanaryDecision.CONTINUE
    ),
    review_id: str = "review_1",
    run_id: str = "run_1",
    reviewer: str = "will",
    reviewed_count: int = 3,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=review_id,
        run_id=run_id,
        reviewer=reviewer,
        decision=decision,
        reviewed_case_ids=tuple(f"case_{index}" for index in range(reviewed_count)),
        reviewed_extraction_ids=tuple(
            f"extraction_{index}" for index in range(reviewed_count)
        ),
        reviewed_trace_run_ids=tuple(
            f"trace_{index}" for index in range(reviewed_count)
        ),
    )


def _run(
    *,
    completed_count: int = 3,
    review: SimpleNamespace | None = None,
    batch_id: str | None = None,
    run_id: str = "run_1",
) -> SimpleNamespace:
    selected_review = review if review is not None else _review(run_id=run_id)
    return SimpleNamespace(
        id=run_id,
        dataset_fingerprint="a" * 64,
        title="Real Requirement acceptance",
        reviewer="will",
        provider="openai",
        model="gpt-test",
        batch_id=batch_id,
        canary_review=selected_review,
        completed_case_count=completed_count,
        attempted_calls=completed_count,
        cases=tuple(
            _case(index, completed=index < completed_count)
            for index in range(20)
        ),
    )


def _preparation(
    *,
    created: int,
    reused: int,
    failed: int = 0,
    deferred: int,
    batch_id: str | None = None,
) -> SimpleNamespace:
    cases = tuple(
        SimpleNamespace(
            input_index=index,
            job_id=f"job_{index}",
            title=f"Job {index}",
            company="Example",
            status=RequirementAcceptanceCaseStatus.EXTRACTED,
            extraction_id=f"extraction_{index}",
            trace_run_id=f"trace_{index}",
            error_code=None,
            error_message=None,
        )
        for index in range(created)
    )
    return SimpleNamespace(
        run_id="run_1",
        dataset_fingerprint="a" * 64,
        import_id="import_2",
        source_version="1.4.6",
        received=20,
        created_jobs=0,
        updated_jobs=20,
        reused_extractions=reused,
        created_extractions=created,
        failed_extractions=failed,
        deferred_extractions=deferred,
        max_new_extractions=created,
        provider="openai",
        model="gpt-test",
        extractor_version="requirement-extractor-v1",
        prompt_version="requirement-extraction-v1",
        batch_id=batch_id,
        batch_reused=False,
        ready_for_manual_review=batch_id is not None,
        cases=cases,
    )


def _args(
    *,
    dataset: Path,
    private_root: Path,
    execute: bool,
    confirmed: bool,
    max_new_extractions: int = 2,
    expected_run_id: str = "run_1",
    expected_canary_review_id: str = "review_1",
    session_manifest: Path | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        dataset=dataset,
        reviewer="will",
        title="Real Requirement acceptance",
        max_new_extractions=max_new_extractions,
        expected_run_id=expected_run_id,
        expected_canary_review_id=expected_canary_review_id,
        web_base_url="http://localhost:3000",
        private_root=private_root,
        session_manifest=session_manifest,
        execute_resume=execute,
        confirm_reviewed_canary_and_live_cost=confirmed,
        json=True,
    )


def _patch_common(
    monkeypatch,
    *,
    args: SimpleNamespace,
    readiness_sequence,
    post_run=None,
) -> None:
    args.dataset.parent.mkdir(parents=True, exist_ok=True)
    args.dataset.write_text('{"formal":true}', encoding="utf-8")
    monkeypatch.setattr(resume_cli, "PRIVATE_DATA_ROOT", args.private_root.parent.resolve())
    monkeypatch.setattr(resume_cli, "_arguments", lambda: args)
    monkeypatch.setattr(resume_cli, "_load_payload", lambda _path: {"formal": True})
    monkeypatch.setattr(
        resume_cli,
        "preflight_requirement_acceptance_dataset",
        lambda _payload: _preflight(),
    )
    monkeypatch.setattr(
        resume_cli,
        "get_settings",
        lambda: SimpleNamespace(
            database_url="sqlite:///unused.db",
            requirement_extractor_provider="openai",
            requirement_extractor_model="gpt-test",
            openai_api_key="test-key-not-a-real-secret",
        ),
    )
    sequence = iter(readiness_sequence)
    monkeypatch.setattr(resume_cli, "_assess_readiness", lambda **_kwargs: next(sequence))
    if post_run is not None:
        monkeypatch.setattr(resume_cli, "_existing_run", lambda **_kwargs: post_run)


def test_resume_policy_binds_continue_review_run_and_remaining_budget(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    manifest = private_root / "session-manifests" / "session.json"
    run = _run(completed_count=3)

    plan = evaluate_requirement_acceptance_resume_operator(
        readiness=_readiness(requested=17),
        existing_run=run,
        dataset_path=dataset,
        expected_dataset_path=dataset,
        private_root=private_root,
        session_manifest_path=manifest,
        expected_run_id="run_1",
        expected_canary_review_id="review_1",
        execute_requested=False,
        live_cost_confirmed=False,
    )
    assert plan.state is RequirementAcceptanceResumeOperatorState.READY_FOR_EXPLICIT_EXECUTION
    assert plan.plan_ready is True
    assert plan.execution_authorized is False
    assert plan.completed_case_count_before == 3
    assert plan.remaining_case_count_before == 17
    assert plan.blockers == ()

    authorized = evaluate_requirement_acceptance_resume_operator(
        readiness=_readiness(requested=17),
        existing_run=run,
        dataset_path=dataset,
        expected_dataset_path=dataset,
        private_root=private_root,
        session_manifest_path=manifest,
        expected_run_id="run_1",
        expected_canary_review_id="review_1",
        execute_requested=True,
        live_cost_confirmed=True,
    )
    assert authorized.state is RequirementAcceptanceResumeOperatorState.AUTHORIZED
    assert authorized.execution_authorized is True


def test_resume_policy_rejects_datasetless_dashboard_readiness(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    run = _run(completed_count=3)
    readiness = replace(
        _readiness(requested=17),
        dataset_fingerprint=None,
        source_version=None,
    )

    plan = evaluate_requirement_acceptance_resume_operator(
        readiness=readiness,
        existing_run=run,
        dataset_path=dataset,
        expected_dataset_path=dataset,
        private_root=private_root,
        session_manifest_path=None,
        expected_run_id="run_1",
        expected_canary_review_id="review_1",
        execute_requested=True,
        live_cost_confirmed=True,
    )

    assert plan.state is RequirementAcceptanceResumeOperatorState.BLOCKED
    assert "formal_dataset_identity_missing" in {
        item.code for item in plan.blockers
    }
    assert plan.execution_authorized is False


def test_resume_policy_preserves_historical_review_after_post_review_retry(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    run = _run(completed_count=3)
    run.cases[0].attempt_count = 2
    run.cases[0].extraction_id = "extraction_0_retry"
    run.cases[0].trace_run_id = "trace_0_retry"
    run.attempted_calls = 4

    plan = evaluate_requirement_acceptance_resume_operator(
        readiness=_readiness(requested=17, attempted_calls=4),
        existing_run=run,
        dataset_path=dataset,
        expected_dataset_path=dataset,
        private_root=private_root,
        session_manifest_path=None,
        expected_run_id="run_1",
        expected_canary_review_id="review_1",
        execute_requested=False,
        live_cost_confirmed=False,
    )

    assert plan.plan_ready is True
    assert plan.blockers == ()
    assert plan.attempted_calls_before == 4
    assert plan.remaining_case_count_before == 17


def test_resume_policy_rejects_wrong_review_identity_evidence_and_budget(
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "private"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    run = _run(completed_count=3)
    run.canary_review.reviewed_trace_run_ids = ("wrong_trace",)

    plan = evaluate_requirement_acceptance_resume_operator(
        readiness=_readiness(requested=18),
        existing_run=run,
        dataset_path=dataset,
        expected_dataset_path=dataset,
        private_root=private_root,
        session_manifest_path=None,
        expected_run_id="wrong_run",
        expected_canary_review_id="wrong_review",
        execute_requested=True,
        live_cost_confirmed=False,
    )
    codes = {item.code for item in plan.blockers}
    assert plan.state is RequirementAcceptanceResumeOperatorState.BLOCKED
    assert "expected_run_id_mismatch" in codes
    assert "expected_canary_review_id_mismatch" in codes
    assert "canary_review_trace_evidence_mismatch" in codes
    assert "resume_budget_exceeds_remaining_cases" in codes
    assert "review_and_live_cost_confirmation_missing" in codes


def test_resume_policy_requires_continue_and_resume_readiness(tmp_path: Path) -> None:
    private_root = tmp_path / "private"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    run = _run(
        completed_count=3,
        review=_review(decision=RequirementAcceptanceCanaryDecision.STOP),
    )

    plan = evaluate_requirement_acceptance_resume_operator(
        readiness=_readiness(
            next_action=RequirementAcceptanceReadinessNextAction.STOPPED,
            allowed=False,
            requested=1,
        ),
        existing_run=run,
        dataset_path=dataset,
        expected_dataset_path=dataset,
        private_root=private_root,
        session_manifest_path=None,
        expected_run_id="run_1",
        expected_canary_review_id="review_1",
        execute_requested=False,
        live_cost_confirmed=False,
    )
    codes = {item.code for item in plan.blockers}
    assert "next_action_is_not_resume_run" in codes
    assert "provider_execution_not_allowed" in codes
    assert "canary_decision_is_not_continue" in codes


def test_plan_mode_never_builds_provider_runtime(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=False, confirmed=False)
    run = _run(completed_count=3)
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[(_readiness(requested=2), run)],
    )
    monkeypatch.setattr(
        resume_cli,
        "_build_use_case",
        lambda: (_ for _ in ()).throw(AssertionError("provider runtime must not build")),
    )
    monkeypatch.setattr(
        resume_cli,
        "_write_resume_manifest",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("implicit plan must not write")),
    )

    assert resume_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "ready_for_explicit_execution"
    assert body["operator"]["runId"] == "run_1"
    assert body["operator"]["canaryReviewId"] == "review_1"
    assert body["operator"]["executionAuthorized"] is False
    assert body["liveExtractionAttemptsObserved"] == 0


def test_wrong_review_id_blocks_before_runtime_or_manifest(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(
        dataset=dataset,
        private_root=private_root,
        execute=False,
        confirmed=False,
        expected_canary_review_id="wrong_review",
    )
    run = _run(completed_count=3)
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[(_readiness(requested=2), run)],
    )
    monkeypatch.setattr(
        resume_cli,
        "_build_use_case",
        lambda: (_ for _ in ()).throw(AssertionError("runtime must not build")),
    )
    monkeypatch.setattr(
        resume_cli,
        "_write_resume_manifest",
        lambda **_kwargs: (_ for _ in ()).throw(AssertionError("blocked plan must not write")),
    )

    assert resume_cli.main() == 1
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "blocked"
    assert {item["code"] for item in body["operator"]["blockers"]} == {
        "expected_canary_review_id_mismatch"
    }
    assert body["liveExtractionAttemptsObserved"] == 0


def test_execute_requires_review_and_cost_confirmation_before_runtime(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=False)
    run = _run(completed_count=3)
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[(_readiness(requested=2), run)],
    )
    writes = []
    monkeypatch.setattr(
        resume_cli,
        "_write_resume_manifest",
        lambda **kwargs: writes.append(kwargs),
    )
    monkeypatch.setattr(
        resume_cli,
        "_build_use_case",
        lambda: (_ for _ in ()).throw(AssertionError("runtime must not build")),
    )

    assert resume_cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "blocked"
    assert {item["code"] for item in body["operator"]["blockers"]} == {
        "review_and_live_cost_confirmation_missing"
    }
    assert len(writes) == 1


def test_clean_partial_resume_records_new_attempts_and_next_resume_command(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    before_run = _run(completed_count=3)
    post_run = _run(completed_count=5)
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[
            (_readiness(requested=2, attempted_calls=3), before_run),
            (_readiness(requested=15, attempted_calls=5), post_run),
        ],
        post_run=post_run,
    )
    fake_use_case = SimpleNamespace(
        execute=lambda **_kwargs: _preparation(
            created=2,
            reused=3,
            deferred=15,
        )
    )
    monkeypatch.setattr(resume_cli, "_build_use_case", lambda: (fake_use_case, object()))
    writes = []
    monkeypatch.setattr(
        resume_cli,
        "_write_resume_manifest",
        lambda **kwargs: writes.append(kwargs),
    )

    assert resume_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "completed"
    assert body["liveExtractionAttemptsObserved"] == 2
    assert body["attemptBudgetExceeded"] is False
    assert body["furtherResumeRequired"] is True
    assert body["manualReviewReady"] is False
    assert body["postReadiness"]["nextAction"] == "resume_run"
    assert "scripts.operate_requirement_acceptance_resume" in body["postReadiness"][
        "recommendedCommand"
    ]
    assert "review_1" in body["postReadiness"]["recommendedCommand"]
    assert len(writes) == 2


def test_final_resume_hands_off_frozen_batch_to_manual_review(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(
        dataset=dataset,
        private_root=private_root,
        execute=True,
        confirmed=True,
        max_new_extractions=17,
    )
    before_run = _run(completed_count=3)
    post_run = _run(completed_count=20, batch_id="batch_1")
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[
            (_readiness(requested=17, attempted_calls=3), before_run),
            (
                _readiness(
                    next_action=RequirementAcceptanceReadinessNextAction.OPEN_MANUAL_REVIEW,
                    allowed=False,
                    requested=1,
                    attempted_calls=20,
                    batch_id="batch_1",
                ),
                post_run,
            ),
        ],
        post_run=post_run,
    )
    fake_use_case = SimpleNamespace(
        execute=lambda **_kwargs: _preparation(
            created=17,
            reused=3,
            deferred=0,
            batch_id="batch_1",
        )
    )
    monkeypatch.setattr(resume_cli, "_build_use_case", lambda: (fake_use_case, object()))
    monkeypatch.setattr(resume_cli, "_write_resume_manifest", lambda **_kwargs: None)

    assert resume_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "completed"
    assert body["liveExtractionAttemptsObserved"] == 17
    assert body["manualReviewReady"] is True
    assert body["furtherResumeRequired"] is False
    assert body["manualReviewUrl"].endswith("/evals/requirements/manual/batch_1")
    assert body["postReadiness"]["recommendedCommand"] is None


def test_execution_lease_loss_never_claims_zero_attempts(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    run = _run(completed_count=3)
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[(_readiness(requested=2), run)],
    )

    def raise_lost(**_kwargs):
        raise RequirementAcceptanceExecutionLeaseLostError(
            "lease expired after uncertain external work"
        )

    fake_use_case = SimpleNamespace(execute=raise_lost)
    monkeypatch.setattr(resume_cli, "_build_use_case", lambda: (fake_use_case, object()))
    monkeypatch.setattr(resume_cli, "_write_resume_manifest", lambda **_kwargs: None)

    assert resume_cli.main() == 1
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "completed_with_attention_required"
    assert body["liveExtractionAttemptsObserved"] is None
    assert body["postExecutionEvidenceError"]["type"] == (
        "execution_lease_lost_before_post_readback"
    )
    assert "may have occurred" in body["postExecutionEvidenceError"]["message"]


def test_execution_lease_conflict_is_rejected_without_post_evidence(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    private_root = tmp_path / "data" / "private" / "requirement-acceptance"
    dataset = private_root / "datasets" / f"formal-{'a' * 16}.json"
    args = _args(dataset=dataset, private_root=private_root, execute=True, confirmed=True)
    run = _run(completed_count=3)
    _patch_common(
        monkeypatch,
        args=args,
        readiness_sequence=[(_readiness(requested=2), run)],
    )

    def raise_conflict(**_kwargs):
        raise RequirementAcceptanceExecutionLeaseUnavailableError(
            "another execution already owns this identity"
        )

    fake_use_case = SimpleNamespace(execute=raise_conflict)
    monkeypatch.setattr(resume_cli, "_build_use_case", lambda: (fake_use_case, object()))
    monkeypatch.setattr(resume_cli, "_write_resume_manifest", lambda **_kwargs: None)

    assert resume_cli.main() == 2
    body = json.loads(capsys.readouterr().out)
    assert body["executionOutcome"] == "execution_rejected"
    assert body["executionError"]["type"] == (
        "RequirementAcceptanceExecutionLeaseUnavailableError"
    )
    assert body["preparation"] is None
    assert body["postReadiness"] is None
    assert body["liveExtractionAttemptsObserved"] == 0
