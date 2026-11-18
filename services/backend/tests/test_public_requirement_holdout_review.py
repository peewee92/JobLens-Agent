import hashlib
import json
import sqlite3

import pytest

from app.evals.job_requirement_extraction import load_job_requirement_eval_cases
from scripts.review_public_requirement_holdout import review

JD = "Required: Python. Optional tools: FreeRTOS is useful but not mandatory. Preferred: familiarity with FreeRTOS."
DIGEST = hashlib.sha256(JD.encode()).hexdigest()
VERSION = "local-test-v1"


@pytest.fixture
def run_files(tmp_path):
    db = tmp_path / "isolated.db"
    with sqlite3.connect(db) as c:
        c.executescript("""
            CREATE TABLE user_profiles (id TEXT);
            CREATE TABLE jobs (id TEXT, description TEXT);
            CREATE TABLE requirement_calls (job_id TEXT, snapshot TEXT, status TEXT,
                response_status INTEGER, attempts INTEGER, extraction_id TEXT, input_tokens INTEGER, output_tokens INTEGER);
            CREATE TABLE job_requirement_extractions (id TEXT, job_id TEXT, model TEXT, input_hash TEXT,
                extractor_version TEXT, prompt_version TEXT, provider TEXT, requirement_count INTEGER, trace_run_id TEXT);
            CREATE TABLE trace_spans (id TEXT, capability TEXT, input_refs TEXT, error TEXT);
            CREATE TABLE job_requirements (job_id TEXT, extraction_id TEXT, requirement_index INTEGER, type TEXT,
                normalized_capability TEXT, importance TEXT, original_text TEXT, evidence_span TEXT);
        """)
        c.execute("INSERT INTO jobs VALUES (?, ?)", ("j", JD))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([{"caseId": "only", "jobId": "j", "descriptionSha256": DIGEST}]))
    dataset = tmp_path / "tiny.jsonl"
    dataset.write_text(json.dumps({
        "caseId": "only", "jobId": "eval-j", "description": JD,
        "expectedRequirements": [
            {"type": "skill", "normalizedCapability": "Python", "importance": "must_have"},
            {"type": "skill", "normalizedCapability": "FreeRTOS", "importance": "preferred"},
        ],
        "forbiddenCapabilities": ["Kubernetes"],
    }))
    return db, manifest, dataset


def read(run_files):
    db, manifest, dataset = run_files
    return review(db, manifest, dataset=dataset)


def populate(db, *, status="completed", extraction_hash=DIGEST, attempts=1, extraction_id="e"):
    snapshot = json.dumps({
        "jobId": "j", "inputHash": DIGEST, "model": "fixture", "extractionPolicy": [VERSION, "prompt-1", "semantics-1"],
    })
    refs = json.dumps({"jobId": "j", "descriptionSha256": DIGEST, "providerCalls": 1})
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO requirement_calls VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  ("j", snapshot, status, 200, attempts, extraction_id, 100, 50))
        c.execute("INSERT INTO job_requirement_extractions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  ("e", "j", "fixture", extraction_hash, VERSION, "prompt-1", "openai", 2, "trace"))
        c.execute("INSERT INTO trace_spans VALUES (?, ?, ?, ?)", ("trace", "requirement_extraction", refs, None))
        c.executemany("INSERT INTO job_requirements VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            ("j", "e", 0, "skill", "Python", "must_have", "Python", "Required: Python."),
            ("j", "e", 1, "skill", "FreeRTOS", "preferred", "FreeRTOS is useful but not mandatory",
             "Optional tools: FreeRTOS is useful but not mandatory."),
        ])


def test_not_run_is_never_counted_as_pass_and_reviewer_is_read_only(run_files):
    db, _, dataset = run_files
    before = db.read_bytes()
    assert read(run_files)["labelChecks"] == {"not_run": 1}
    assert db.read_bytes() == before
    with pytest.raises(ValueError, match="at least 10"):
        load_job_requirement_eval_cases(dataset)


def test_correct_labels_do_not_claim_external_provenance_or_full_semantic_pass(run_files):
    populate(run_files[0])
    result = read(run_files)
    assert result["labelChecks"] == {"label_checks_passed": 1}
    assert result["transportProvenance"] == "not_verified_by_database"
    assert result["requiresManualReview"] is True


def test_extra_hard_gate_is_not_hidden_behind_a_correct_preferred_row(run_files):
    db = run_files[0]
    populate(db)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE job_requirement_extractions SET requirement_count=3")
        c.execute("INSERT INTO job_requirements VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                  ("j", "e", 2, "skill", "FreeRTOS", "must_have", "FreeRTOS",
                   "Preferred: familiarity with FreeRTOS."))
    result = read(run_files)["cases"][0]
    assert result["status"] == "label_checks_failed"
    assert result["conflictingImportance"] == [{
        "expected": "skill:FreeRTOS:preferred", "observed": ["must_have", "preferred"],
    }]


def test_reports_missing_wrong_forbidden_and_evidence_independently(run_files):
    db = run_files[0]
    populate(db)
    with sqlite3.connect(db) as c:
        c.execute("UPDATE job_requirements SET importance='must_have', evidence_span='invented quote' WHERE requirement_index=1")
        c.execute("UPDATE job_requirements SET normalized_capability='Kubernetes', evidence_span='Optional tools:' WHERE requirement_index=0")
    case = read(run_files)["cases"][0]
    assert case["missing"] == ["skill:Python:must_have"]
    assert case["wrongImportance"] == [{"expected": "skill:FreeRTOS:preferred", "observed": ["must_have"]}]
    assert case["forbidden"] == ["Kubernetes"]
    assert case["unanchoredIndexes"] == [1]
    assert case["evidenceMismatchIndexes"] == [0]


@pytest.mark.parametrize(("changes", "expected"), [
    ({"status": "failed"}, "request_failed"),
    ({"status": "running"}, "request_unsettled"),
    ({"status": "uncertain"}, "request_unsettled"),
    ({"attempts": 2}, "receipt_mismatch"),
    ({"extraction_id": "not-the-record"}, "artifact_mismatch"),
    ({"extraction_hash": "stale-hash"}, "artifact_mismatch"),
])
def test_never_falls_back_to_a_different_extraction(run_files, changes, expected):
    populate(run_files[0], **changes)
    assert read(run_files)["labelChecks"] == {expected: 1}


def test_rejects_personal_data_and_detects_changed_or_ambiguous_inputs(run_files):
    db, manifest, _ = run_files
    populate(db)
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO requirement_calls SELECT * FROM requirement_calls")
    assert read(run_files)["labelChecks"] == {"ambiguous_receipts": 1}
    with sqlite3.connect(db) as c:
        c.execute("UPDATE jobs SET description='replacement'")
    assert read(run_files)["labelChecks"] == {"source_mismatch": 1}
    with sqlite3.connect(db) as c:
        c.execute("INSERT INTO user_profiles VALUES ('do-not-read')")
    with pytest.raises(ValueError, match="profile-free"):
        read(run_files)
    manifest.write_text(json.dumps([{"caseId": "only", "jobId": "j", "descriptionSha256": "d"}]))
    with pytest.raises(ValueError, match="source hash"):
        read(run_files)
