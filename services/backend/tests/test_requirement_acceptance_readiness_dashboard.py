"""Read-only dashboard tests for formal Requirement acceptance readiness."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from unittest.mock import Mock

from app.application.requirement_acceptance.local_bootstrap import private_dataset_path
from app.application.requirement_acceptance.readiness import (
    RequirementAcceptanceReadinessNextAction,
)
from app.application.requirement_acceptance.readiness_dashboard import (
    GetRequirementAcceptanceReadinessDashboardUseCase,
    RequirementAcceptanceDatasetState,
)
from app.application.requirement_acceptance.runtime_environment import (
    read_requirement_acceptance_database_revision,
)
from app.application.requirement_acceptance.use_case import (
    preflight_requirement_acceptance_dataset,
)


def _stable_text_hash(value: str) -> str:
    hash_value = 0x811C9DC5
    encoded = value.encode("utf-16-le")
    for offset in range(0, len(encoded), 2):
        code_unit = encoded[offset] | (encoded[offset + 1] << 8)
        hash_value ^= code_unit
        hash_value = (hash_value * 0x01000193) & 0xFFFFFFFF
    return f"fnv1a32:{hash_value:08x}"


def _formal_payload() -> dict:
    jobs = []
    for index in range(20):
        description = (
            f"岗位 {index + 1}：负责独特业务域 token-{index + 1} 的系统设计。\n"
            f"要求掌握技能 capability-{index + 1}，并具备独立交付经验。"
        )
        jobs.append(
            {
                "url": f"https://example.com/jobs/formal-{index + 1}",
                "title": f"AI Engineer {index + 1}",
                "company": f"Company {index + 1}",
                "sourceVersion": "1.4.6",
                "detailSucceeded": True,
                "descriptionQuality": "full_jd",
                "descriptionHasRoleEvidenceSignal": True,
                "descriptionNoiseCount": 0,
                "requirementReviewEligible": True,
                "requirementReviewIneligibilityReasons": [],
                "description": description,
                "descriptionLength": len(description.encode("utf-16-le")) // 2,
                "descriptionHash": _stable_text_hash(description),
            }
        )
    return {
        "version": "1.4.6",
        "generatedAt": "2026-08-05T09:00:00.000Z",
        "purpose": "requirement_manual_quality_review",
        "qualityGate": {
            "requiredSampleSize": 20,
            "eligibleCount": 20,
            "distinctEligibleCount": 20,
            "nearDuplicateCount": 0,
            "selectedCount": 20,
            "status": "ready",
            "blockers": [],
        },
        "selectionPolicy": {
            "descriptionSimilarity": "nfkc_alphanumeric_5gram_jaccard",
            "nearDuplicateThreshold": 1.0,
        },
        "excludedNearDuplicates": [],
        "jobs": jobs,
    }


def _use_case(
    tmp_path: Path,
    *,
    provider: str = "openai",
    model: str = "gpt-test",
    api_key_configured: bool = True,
    database_revision: str = "head",
):
    runs = Mock()
    runs.get_by_identity.return_value = None
    use_case = GetRequirementAcceptanceReadinessDashboardUseCase(
        runs=runs,
        private_root=tmp_path / "private",
        backend_root=tmp_path / "backend",
        database_url="sqlite:///ignored.db",
        provider=provider,
        model=model,
        api_key_configured=api_key_configured,
        extractor_version="requirement-extractor-v1",
        prompt_version="requirement-extractor-prompt-v1",
        web_base_url="http://localhost:3000",
        database_revision_reader=lambda _url, _root: (
            True,
            database_revision,
            None,
        ),
        migration_head_reader=lambda _root: "head",
    )
    return use_case, runs


def _stage_canonical_dataset(tmp_path: Path) -> Path:
    payload = _formal_payload()
    preflight = preflight_requirement_acceptance_dataset(payload)
    destination = private_dataset_path(
        private_root=tmp_path / "private",
        dataset_fingerprint=preflight.dataset_fingerprint,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return destination


def test_database_revision_reader_does_not_create_missing_sqlite(
    tmp_path: Path,
) -> None:
    database = tmp_path / "missing.db"

    reachable, revision, error = read_requirement_acceptance_database_revision(
        f"sqlite:///{database}",
        backend_root=tmp_path,
    )

    assert reachable is False
    assert revision is None
    assert "does not exist" in (error or "")
    assert database.exists() is False


def test_database_revision_reader_preserves_sqlite_bytes(tmp_path: Path) -> None:
    database = tmp_path / "read-only.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE alembic_version (version_num TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO alembic_version(version_num) VALUES ('20260805_0015')"
        )
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel(value) VALUES ('unchanged')")
    before = sha256(database.read_bytes()).hexdigest()

    reachable, revision, error = read_requirement_acceptance_database_revision(
        f"sqlite:///{database}",
        backend_root=tmp_path,
    )

    assert reachable is True
    assert revision == "20260805_0015"
    assert error is None
    assert sha256(database.read_bytes()).hexdigest() == before


def test_missing_dataset_fails_closed_without_querying_runs(tmp_path: Path) -> None:
    use_case, runs = _use_case(
        tmp_path,
        provider="disabled",
        model="",
        api_key_configured=False,
        database_revision="old",
    )

    result = use_case.execute(
        reviewer="will",
        title="2026-08 acceptance",
        max_new_extractions=1,
    )

    assert result.dataset_state is RequirementAcceptanceDatasetState.MISSING
    assert result.dataset_candidate_count == 0
    assert result.readiness.next_action is RequirementAcceptanceReadinessNextAction.FIX_BLOCKERS
    assert result.readiness.provider_execution_allowed is False
    assert {item.code for item in result.readiness.blockers} >= {
        "formal_dataset_missing",
        "database_migration_not_current",
        "live_provider_not_configured",
        "live_model_not_configured",
    }
    runs.get_by_identity.assert_not_called()


def test_multiple_datasets_require_explicit_selection(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "private" / "datasets"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "formal-aaaaaaaaaaaaaaaa.json").write_text("{}", encoding="utf-8")
    (dataset_dir / "formal-bbbbbbbbbbbbbbbb.json").write_text("{}", encoding="utf-8")
    use_case, runs = _use_case(tmp_path)

    result = use_case.execute(reviewer="will", title="acceptance", max_new_extractions=1)

    assert result.dataset_state is RequirementAcceptanceDatasetState.SELECTION_REQUIRED
    assert result.dataset_candidate_count == 2
    assert [item.code for item in result.readiness.blockers] == [
        "formal_dataset_selection_required"
    ]
    runs.get_by_identity.assert_not_called()


def test_invalid_dataset_is_reported_without_leaking_file_contents(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "private" / "datasets"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "formal-aaaaaaaaaaaaaaaa.json").write_text("not-json", encoding="utf-8")
    use_case, runs = _use_case(tmp_path)

    result = use_case.execute(reviewer="will", title="acceptance", max_new_extractions=1)

    assert result.dataset_state is RequirementAcceptanceDatasetState.INVALID
    assert result.dataset_file_name == "formal-aaaaaaaaaaaaaaaa.json"
    blocker = result.readiness.blockers[0]
    assert blocker.code == "formal_dataset_invalid"
    assert "JSONDecodeError" in blocker.message
    assert "not-json" not in blocker.message
    runs.get_by_identity.assert_not_called()


def test_noncanonical_file_name_is_rejected(tmp_path: Path) -> None:
    payload = _formal_payload()
    dataset_dir = tmp_path / "private" / "datasets"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "formal-aaaaaaaaaaaaaaaa.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    use_case, runs = _use_case(tmp_path)

    result = use_case.execute(reviewer="will", title="acceptance", max_new_extractions=1)

    assert result.dataset_state is RequirementAcceptanceDatasetState.INVALID
    assert result.readiness.next_action is RequirementAcceptanceReadinessNextAction.FIX_BLOCKERS
    assert result.readiness.blockers[0].code == "formal_dataset_invalid"
    assert "Dataset Fingerprint" in result.readiness.blockers[0].message
    runs.get_by_identity.assert_not_called()


def test_valid_dataset_does_not_query_runs_before_database_reaches_head(
    tmp_path: Path,
) -> None:
    _stage_canonical_dataset(tmp_path)
    use_case, runs = _use_case(tmp_path, database_revision="old")

    result = use_case.execute(
        reviewer="will",
        title="acceptance",
        max_new_extractions=1,
    )

    assert result.dataset_state is RequirementAcceptanceDatasetState.READY
    assert result.readiness.next_action is RequirementAcceptanceReadinessNextAction.FIX_BLOCKERS
    assert "database_migration_not_current" in {
        item.code for item in result.readiness.blockers
    }
    runs.get_by_identity.assert_not_called()


def test_one_canonical_dataset_can_reach_run_canary_without_side_effects(
    tmp_path: Path,
) -> None:
    destination = _stage_canonical_dataset(tmp_path)
    use_case, runs = _use_case(tmp_path)

    result = use_case.execute(
        reviewer="will",
        title=None,
        max_new_extractions=1,
    )

    assert result.dataset_state is RequirementAcceptanceDatasetState.READY
    assert result.dataset_candidate_count == 1
    assert result.dataset_file_name == destination.name
    assert result.readiness.dataset_fingerprint is not None
    assert result.readiness.selected_count == 20
    assert result.readiness.title == "Requirement acceptance 2026-08-05T09:00:00.000Z"
    assert result.readiness.next_action is RequirementAcceptanceReadinessNextAction.RUN_CANARY
    assert result.readiness.provider_execution_allowed is True
    assert result.readiness.ready_for_next_action is True
    assert result.readiness.blockers == ()
    runs.get_by_identity.assert_called_once()
