"""Readiness policy tests for the first credential-backed Requirement run."""
from __future__ import annotations

from dataclasses import replace
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessNextAction,
    evaluate_requirement_acceptance_readiness,
)
from app.application.requirement_acceptance.session_manifest import (
    SESSION_MANIFEST_SCHEMA_VERSION,
    build_requirement_acceptance_session_manifest,
    requirement_acceptance_session_id,
    write_requirement_acceptance_session_manifest,
)
from app.application.requirement_acceptance.runs import (
    RequirementAcceptanceCanaryDecision,
    RequirementAcceptanceCanaryReviewDetail,
    RequirementAcceptancePreflight,
    RequirementAcceptanceRunCaseDetail,
    RequirementAcceptanceRunCaseStatus,
    RequirementAcceptanceRunDetail,
    RequirementAcceptanceRunStatus,
)
import scripts.check_requirement_acceptance_readiness as readiness_cli
from scripts.check_requirement_acceptance_readiness import _database_revision

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)


def _preflight() -> RequirementAcceptancePreflight:
    return RequirementAcceptancePreflight(
        dataset_fingerprint="a" * 64,
        source_version="1.4.6",
        generated_at="2026-08-04T12:00:00Z",
        selected_count=20,
        total_description_characters=20_000,
        minimum_description_characters=500,
        maximum_description_characters=1_500,
        average_description_characters=1_000.0,
    )


def _case(index: int, *, attempted: bool = False) -> RequirementAcceptanceRunCaseDetail:
    return RequirementAcceptanceRunCaseDetail(
        id=f"case_{index}",
        case_index=index,
        source_url=f"https://example.com/{index}",
        title=f"Job {index}",
        company="Example",
        description_hash=f"{index:064x}"[-64:],
        description_snapshot=f"JD {index}",
        current_description_hash=f"{index:064x}"[-64:],
        description_is_current=True,
        job_id=f"job_{index}",
        status=(
            RequirementAcceptanceRunCaseStatus.EXTRACTED
            if attempted
            else RequirementAcceptanceRunCaseStatus.DEFERRED
        ),
        attempt_count=1 if attempted else 0,
        extraction_id=f"extraction_{index}" if attempted else None,
        trace_run_id=f"trace_{index}" if attempted else None,
        trace_capability="job_requirement_extraction" if attempted else None,
        trace_model="gpt-test" if attempted else None,
        trace_prompt_version="prompt-v1" if attempted else None,
        trace_latency_ms=100 if attempted else None,
        trace_input_tokens=10 if attempted else None,
        trace_output_tokens=20 if attempted else None,
        trace_error=None,
        trace_created_at=NOW if attempted else None,
        error_code=None,
        error_message=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _review(decision: RequirementAcceptanceCanaryDecision) -> RequirementAcceptanceCanaryReviewDetail:
    return RequirementAcceptanceCanaryReviewDetail(
        id="review_1",
        run_id="run_1",
        reviewer="will",
        decision=decision,
        notes="I inspected the exact frozen evidence before making this decision.",
        reviewed_case_ids=("case_0", "case_1"),
        reviewed_extraction_ids=("extraction_0", "extraction_1"),
        reviewed_trace_run_ids=("trace_0", "trace_1"),
        reviewed_at=NOW,
    )


def _run(
    *,
    attempted_calls: int = 2,
    review: RequirementAcceptanceCanaryReviewDetail | None = None,
    batch_id: str | None = None,
) -> RequirementAcceptanceRunDetail:
    cases = tuple(
        _case(index, attempted=index < attempted_calls)
        for index in range(20)
    )
    if batch_id is not None:
        status = RequirementAcceptanceRunStatus.READY
    elif review is not None and review.decision is RequirementAcceptanceCanaryDecision.STOP:
        status = RequirementAcceptanceRunStatus.STOPPED
    elif attempted_calls >= 3 and review is None:
        status = RequirementAcceptanceRunStatus.AWAITING_CANARY_REVIEW
    else:
        status = RequirementAcceptanceRunStatus.PARTIAL
    return RequirementAcceptanceRunDetail(
        id="run_1",
        dataset_fingerprint="a" * 64,
        source_version="1.4.6",
        dataset_generated_at="2026-08-04T12:00:00Z",
        title="Real Requirement acceptance",
        reviewer="will",
        provider="openai",
        model="gpt-test",
        extractor_version="requirement-extractor-v1",
        prompt_version="requirement-extraction-v1",
        first_import_id="import_1",
        last_import_id="import_1",
        batch_id=batch_id,
        status=status,
        canary_review_required=(attempted_calls >= 3 and review is None and batch_id is None),
        canary_review=review,
        pending_count=0,
        reused_count=0,
        extracted_count=attempted_calls,
        failed_count=0,
        deferred_count=20 - attempted_calls,
        attempted_calls=attempted_calls,
        created_at=NOW,
        updated_at=NOW,
        cases=cases,
    )


def _evaluate(
    *,
    existing_run: RequirementAcceptanceRunDetail | None = None,
    provider: str = "openai",
    model: str = "gpt-test",
    api_key_configured: bool = True,
    max_new_extractions: int | None = 3,
    database_reachable: bool = True,
    database_revision: str | None = "head",
):
    return evaluate_requirement_acceptance_readiness(
        preflight=_preflight(),
        provider=provider,
        model=model,
        api_key_configured=api_key_configured,
        reviewer="will",
        title="Real Requirement acceptance",
        max_new_extractions=max_new_extractions,
        database_reachable=database_reachable,
        database_revision=database_revision,
        migration_head="head",
        existing_run=existing_run,
        web_base_url="http://localhost:3000/",
    )


def test_readiness_command_preview_routes_to_explicit_operator_plan_modes() -> None:
    dataset = Path("/private/formal-review.json")
    canary = readiness_cli._command_preview(
        dataset=dataset,
        reviewer="will",
        title="Real Requirement acceptance",
        max_new_extractions=3,
        next_action=RequirementAcceptanceReadinessNextAction.RUN_CANARY,
        existing_run=None,
    )
    assert canary is not None
    assert "scripts.operate_requirement_acceptance_canary" in canary
    assert "--execute-canary" not in canary

    run = _run(
        attempted_calls=3,
        review=_review(RequirementAcceptanceCanaryDecision.CONTINUE),
    )
    resume = readiness_cli._command_preview(
        dataset=dataset,
        reviewer="will",
        title="Real Requirement acceptance",
        max_new_extractions=17,
        next_action=RequirementAcceptanceReadinessNextAction.RESUME_RUN,
        existing_run=run,
    )
    assert resume is not None
    assert "scripts.operate_requirement_acceptance_resume" in resume
    assert "--expected-run-id run_1" in resume
    assert "--expected-canary-review-id review_1" in resume
    assert "--execute-resume" not in resume


def test_new_live_run_allows_only_an_explicit_one_to_three_case_canary() -> None:
    ready = _evaluate(max_new_extractions=3)
    assert ready.workflow_ready is True
    assert ready.provider_execution_allowed is True
    assert ready.ready_for_next_action is True
    assert ready.next_action is RequirementAcceptanceReadinessNextAction.RUN_CANARY
    assert ready.blockers == ()

    blocked = _evaluate(max_new_extractions=4)
    assert blocked.provider_execution_allowed is False
    assert {item.code for item in blocked.blockers} == {"initial_canary_limit_exceeded"}


def test_missing_live_configuration_is_reported_without_exposing_a_key() -> None:
    result = _evaluate(
        provider="disabled",
        model="",
        api_key_configured=False,
    )
    assert result.workflow_ready is False
    assert result.next_action is RequirementAcceptanceReadinessNextAction.FIX_BLOCKERS
    assert result.api_key_configured is False
    assert {item.code for item in result.blockers} == {
        "live_provider_not_configured",
        "live_model_not_configured",
    }
    assert all("sk-" not in item.message for item in result.blockers)


def test_missing_key_blocks_provider_execution_but_not_dataset_identity() -> None:
    result = _evaluate(api_key_configured=False)
    assert result.workflow_ready is True
    assert result.provider_execution_allowed is False
    assert {item.code for item in result.blockers} == {"openai_api_key_missing"}


def test_partial_unreviewed_run_enforces_remaining_cumulative_canary_budget() -> None:
    run = _run(attempted_calls=2)
    ready = _evaluate(existing_run=run, max_new_extractions=1)
    assert ready.next_action is RequirementAcceptanceReadinessNextAction.RUN_CANARY
    assert ready.provider_execution_allowed is True
    assert ready.workbench_url == "http://localhost:3000/evals/requirements/canary/run_1"

    blocked = _evaluate(existing_run=run, max_new_extractions=2)
    assert blocked.provider_execution_allowed is False
    assert {item.code for item in blocked.blockers} == {
        "remaining_canary_limit_exceeded"
    }


def test_three_attempts_require_human_workbench_action_not_an_api_key() -> None:
    result = _evaluate(
        existing_run=_run(attempted_calls=3),
        api_key_configured=False,
        max_new_extractions=17,
    )
    assert result.next_action is RequirementAcceptanceReadinessNextAction.REVIEW_CANARY
    assert result.provider_execution_allowed is False
    assert result.ready_for_next_action is True
    assert result.blockers == ()
    assert result.workbench_url is not None


def test_continue_allows_resumable_explicit_budget_while_stop_is_terminal() -> None:
    continued = _evaluate(
        existing_run=_run(
            attempted_calls=2,
            review=_review(RequirementAcceptanceCanaryDecision.CONTINUE),
        ),
        max_new_extractions=18,
    )
    assert continued.next_action is RequirementAcceptanceReadinessNextAction.RESUME_RUN
    assert continued.provider_execution_allowed is True
    assert continued.canary_decision is RequirementAcceptanceCanaryDecision.CONTINUE

    stopped = _evaluate(
        existing_run=_run(
            attempted_calls=2,
            review=_review(RequirementAcceptanceCanaryDecision.STOP),
        ),
        max_new_extractions=1,
    )
    assert stopped.next_action is RequirementAcceptanceReadinessNextAction.STOPPED
    assert stopped.provider_execution_allowed is False
    assert stopped.ready_for_next_action is False


def test_ready_batch_points_to_manual_review_instead_of_more_provider_calls() -> None:
    result = _evaluate(
        existing_run=_run(attempted_calls=20, batch_id="batch_1"),
        max_new_extractions=1,
    )
    assert result.next_action is RequirementAcceptanceReadinessNextAction.OPEN_MANUAL_REVIEW
    assert result.provider_execution_allowed is False
    assert result.ready_for_next_action is True
    assert result.manual_review_url == (
        "http://localhost:3000/evals/requirements/manual/batch_1"
    )


def test_database_revision_is_a_workflow_blocker() -> None:
    result = _evaluate(database_revision="old")
    assert result.workflow_ready is False
    assert {item.code for item in result.blockers} == {
        "database_migration_not_current"
    }


def test_cli_reports_structured_blockers_without_printing_secret(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        readiness_cli,
        "_arguments",
        lambda: SimpleNamespace(
            dataset=Path("formal.json"),
            reviewer="will",
            title="Real Requirement acceptance",
            max_new_extractions=3,
            web_base_url="http://localhost:3000",
            session_manifest=None,
            json=True,
        ),
    )
    monkeypatch.setattr(readiness_cli, "_load_payload", lambda _path: {"formal": True})
    monkeypatch.setattr(
        readiness_cli,
        "preflight_requirement_acceptance_dataset",
        lambda _payload: _preflight(),
    )
    monkeypatch.setattr(readiness_cli, "_migration_head", lambda: "head")
    monkeypatch.setattr(
        readiness_cli,
        "_database_revision",
        lambda _url: (True, "head", None),
    )
    monkeypatch.setattr(
        readiness_cli,
        "get_settings",
        lambda: SimpleNamespace(
            requirement_extractor_provider="openai",
            requirement_extractor_model="gpt-test",
            openai_api_key=None,
            database_url="sqlite:///unused.db",
        ),
    )
    monkeypatch.setattr(readiness_cli, "_existing_run", lambda **_kwargs: None)

    assert readiness_cli.main() == 1
    body = json.loads(capsys.readouterr().out)
    assert body["workflowReady"] is True
    assert body["providerExecutionAllowed"] is False
    assert body["apiKeyConfigured"] is False
    assert body["providerCalls"] == 0
    assert body["dbWrites"] == 0
    assert body["recommendedCommand"] is None
    assert {item["code"] for item in body["blockers"]} == {
        "openai_api_key_missing"
    }
    assert "sk-" not in json.dumps(body)


def test_sqlite_database_revision_check_is_read_only(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    reachable, revision, error = _database_revision(f"sqlite:///{missing}")
    assert reachable is False
    assert revision is None
    assert error is not None
    assert missing.exists() is False

    database = tmp_path / "ready.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        connection.execute("INSERT INTO alembic_version VALUES ('revision_1')")
    before = database.stat().st_size
    reachable, revision, error = _database_revision(f"sqlite:///{database}")
    assert reachable is True
    assert revision == "revision_1"
    assert error is None
    assert database.stat().st_size == before


def test_session_identity_is_stable_across_budget_and_export_time() -> None:
    first = requirement_acceptance_session_id(
        dataset_fingerprint="a" * 64,
        reviewer="will",
        title="Real Requirement acceptance",
        provider="openai",
        model="gpt-test",
        extractor_version="requirement-extractor-v1",
        prompt_version="requirement-extraction-v1",
    )
    second = requirement_acceptance_session_id(
        dataset_fingerprint="a" * 64,
        reviewer="will",
        title="Real Requirement acceptance",
        provider="OPENAI",
        model="gpt-test",
        extractor_version="requirement-extractor-v1",
        prompt_version="requirement-extraction-v1",
    )
    changed_model = requirement_acceptance_session_id(
        dataset_fingerprint="a" * 64,
        reviewer="will",
        title="Real Requirement acceptance",
        provider="openai",
        model="gpt-other",
        extractor_version="requirement-extractor-v1",
        prompt_version="requirement-extraction-v1",
    )
    assert first == second
    assert first.startswith("reqacceptsession_")
    assert changed_model != first


def test_session_manifest_rejects_datasetless_dashboard_readiness() -> None:
    readiness = replace(
        _evaluate(existing_run=None, max_new_extractions=1),
        dataset_fingerprint=None,
        source_version=None,
    )

    with pytest.raises(ValueError, match="validated formal dataset"):
        build_requirement_acceptance_session_manifest(
            readiness=readiness,
            existing_run=None,
            dataset_path=Path("formal-review.json"),
            extractor_version="requirement-extractor-v1",
            prompt_version="requirement-extraction-v1",
            recommended_command=None,
            generated_at=NOW,
        )


def test_session_manifest_contains_references_not_raw_sensitive_evidence() -> None:
    run = _run(
        attempted_calls=4,
        review=_review(RequirementAcceptanceCanaryDecision.CONTINUE),
    )
    readiness = _evaluate(
        existing_run=run,
        max_new_extractions=16,
    )
    manifest = build_requirement_acceptance_session_manifest(
        readiness=readiness,
        existing_run=run,
        dataset_path=Path("/private/formal-review.json"),
        extractor_version="requirement-extractor-v1",
        prompt_version="requirement-extraction-v1",
        recommended_command=".venv/bin/python -m scripts.prepare_requirement_acceptance formal-review.json",
        generated_at=NOW,
    )

    assert manifest["schemaVersion"] == SESSION_MANIFEST_SCHEMA_VERSION
    assert manifest["state"] == "ready_for_provider_execution"
    assert manifest["evidence"]["runId"] == "run_1"
    assert manifest["evidence"]["canaryReview"]["decision"] == "continue"
    assert manifest["evidence"]["canaryReview"]["reviewedCaseIds"] == [
        "case_0",
        "case_1",
    ]
    assert manifest["evidence"]["cases"][0]["isPendingCanaryReviewEvidence"] is False
    assert manifest["evidence"]["cases"][0]["isFrozenCanaryEvidence"] is True
    assert manifest["evidence"]["cases"][2]["isFrozenCanaryEvidence"] is False
    serialized = json.dumps(manifest, ensure_ascii=False)
    assert "I inspected the exact frozen evidence" not in serialized
    assert "JD 0" not in serialized
    assert "sk-" not in serialized
    assert manifest["privacy"]["containsApiKey"] is False
    assert manifest["completionChecklist"]["modelQualityApproved"] is None
    assert manifest["completionChecklist"]["matchPhaseAllowed"] is False


def test_session_manifest_marks_only_unreviewed_attempts_as_pending_canary_evidence() -> None:
    run = _run(attempted_calls=2)
    readiness = _evaluate(existing_run=run, max_new_extractions=1)
    manifest = build_requirement_acceptance_session_manifest(
        readiness=readiness,
        existing_run=run,
        dataset_path=Path("formal-review.json"),
        extractor_version="requirement-extractor-v1",
        prompt_version="requirement-extraction-v1",
        recommended_command="safe-command",
        generated_at=NOW,
    )
    cases = manifest["evidence"]["cases"]
    assert [item["isPendingCanaryReviewEvidence"] for item in cases[:3]] == [
        True,
        True,
        False,
    ]
    assert all(item["isFrozenCanaryEvidence"] is False for item in cases)


def test_session_manifest_drops_provider_command_for_human_or_stopped_actions() -> None:
    human_run = _run(attempted_calls=3)
    stopped_run = _run(
        attempted_calls=2,
        review=_review(RequirementAcceptanceCanaryDecision.STOP),
    )
    for readiness, run in (
        (_evaluate(existing_run=human_run, max_new_extractions=17), human_run),
        (_evaluate(existing_run=stopped_run, max_new_extractions=1), stopped_run),
    ):
        manifest = build_requirement_acceptance_session_manifest(
            readiness=readiness,
            existing_run=run,
            dataset_path=Path("formal-review.json"),
            extractor_version="requirement-extractor-v1",
            prompt_version="requirement-extraction-v1",
            recommended_command="unsafe-provider-command",
            generated_at=NOW,
        )
        assert manifest["execution"]["recommendedCommand"] is None
        assert manifest["execution"]["recommendedCommandSha256"] is None


def test_session_manifest_writer_is_atomic_and_leaves_no_temp_file(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "session.json"
    manifest = {"schemaVersion": SESSION_MANIFEST_SCHEMA_VERSION, "sessionId": "session_1"}
    write_requirement_acceptance_session_manifest(output, manifest)
    assert json.loads(output.read_text(encoding="utf-8")) == manifest
    assert list(output.parent.glob(f".{output.name}.*.tmp")) == []


def test_cli_writes_secret_free_session_manifest(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    output = tmp_path / "session.json"
    monkeypatch.setattr(
        readiness_cli,
        "_arguments",
        lambda: SimpleNamespace(
            dataset=Path("formal.json"),
            reviewer="will",
            title="Real Requirement acceptance",
            max_new_extractions=3,
            web_base_url="http://localhost:3000",
            session_manifest=output,
            json=True,
        ),
    )
    monkeypatch.setattr(readiness_cli, "_load_payload", lambda _path: {"formal": True})
    monkeypatch.setattr(
        readiness_cli,
        "preflight_requirement_acceptance_dataset",
        lambda _payload: _preflight(),
    )
    monkeypatch.setattr(readiness_cli, "_migration_head", lambda: "head")
    monkeypatch.setattr(
        readiness_cli,
        "_database_revision",
        lambda _url: (True, "head", None),
    )
    monkeypatch.setattr(
        readiness_cli,
        "get_settings",
        lambda: SimpleNamespace(
            requirement_extractor_provider="openai",
            requirement_extractor_model="gpt-test",
            openai_api_key="sk-super-secret",
            database_url="sqlite:///unused.db",
        ),
    )
    monkeypatch.setattr(readiness_cli, "_existing_run", lambda **_kwargs: None)

    assert readiness_cli.main() == 0
    body = json.loads(capsys.readouterr().out)
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert body["sessionId"] == manifest["sessionId"]
    assert body["sessionManifestPath"] == str(output.resolve())
    assert manifest["state"] == "ready_for_provider_execution"
    assert manifest["execution"]["providerCallsDuringManifestExport"] == 0
    assert "sk-super-secret" not in json.dumps(body)
    assert "sk-super-secret" not in json.dumps(manifest)
