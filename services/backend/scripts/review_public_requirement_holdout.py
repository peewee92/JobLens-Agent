"""Inspect an isolated public-posting holdout database; never dispatch or write results."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from hashlib import sha256
from pathlib import Path

from app.evals.job_requirement_extraction import (
    JobRequirementEvalCase,
    read_job_requirement_eval_cases,
)

DATASET = (
    Path(__file__).resolve().parents[3]
    / "data/evals/requirement-extraction/public-source-holdout-v1.jsonl"
)


def _hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _check_manifest(
    manifest: list[dict], cases: tuple[JobRequirementEvalCase, ...],
) -> dict[str, str]:
    if not isinstance(manifest, list) or len(manifest) != len(cases):
        raise ValueError("manifest must cover every holdout case exactly once")
    lookup = {case.case_id: case for case in cases}
    bindings: dict[str, str] = {}
    for entry in manifest:
        if not isinstance(entry, dict):
            raise ValueError("invalid holdout manifest entry")
        case_id, job_id = entry.get("caseId"), entry.get("jobId")
        if not isinstance(case_id, str) or case_id in bindings or case_id not in lookup:
            raise ValueError("invalid, duplicate, or unknown caseId")
        if not isinstance(job_id, str) or not job_id or len(job_id) > 40 or job_id in bindings.values():
            raise ValueError("invalid or duplicate jobId")
        if entry.get("descriptionSha256") != _hash(lookup[case_id].description):
            raise ValueError("manifest source hash does not match the holdout text")
        bindings[case_id] = job_id
    return bindings


def _score(case: JobRequirementEvalCase, requirements: list[sqlite3.Row]) -> dict:
    observed = {}
    unanchored, unpaired = [], []
    for row in requirements:
        key = (row["type"], (row["normalized_capability"] or "").casefold())
        observed.setdefault(key, set()).add(row["importance"])
        original, evidence = row["original_text"], row["evidence_span"]
        if not original or not evidence or original not in case.description or evidence not in case.description:
            unanchored.append(row["requirement_index"])
        elif original not in evidence:
            unpaired.append(row["requirement_index"])

    missing, wrong, conflicting = [], [], []
    for expected in case.expected_requirements:
        capability = expected.normalized_capability or ""
        key = (expected.type.value, capability.casefold())
        label = f"{expected.type.value}:{capability or '-'}:{expected.importance.value}"
        seen = observed.get(key, set())
        if not seen:
            missing.append(label)
        elif expected.importance.value not in seen:
            wrong.append({"expected": label, "observed": sorted(seen)})
        elif seen != {expected.importance.value}:
            # A correct preferred row must not hide an additional hard gate.
            conflicting.append({"expected": label, "observed": sorted(seen)})
    names = {key[1] for key in observed}
    forbidden = [name for name in case.forbidden_capabilities if name.casefold() in names]
    return {
        "status": "label_checks_failed" if any((missing, wrong, conflicting, forbidden, unanchored, unpaired))
        else "label_checks_passed",
        "missing": missing,
        "wrongImportance": wrong,
        "conflictingImportance": conflicting,
        "forbidden": forbidden,
        "unanchoredIndexes": unanchored,
        "evidenceMismatchIndexes": unpaired,
    }


def _read_case(connection: sqlite3.Connection, case: JobRequirementEvalCase, job_id: str) -> dict:
    report = {"caseId": case.case_id}
    job = connection.execute("SELECT description FROM jobs WHERE id = ?", (job_id,)).fetchone()
    digest = _hash(case.description)
    if job is None or job["description"] != case.description:
        return {**report, "status": "source_mismatch"}

    receipts = connection.execute(
        """SELECT snapshot, status, response_status, attempts, extraction_id, input_tokens, output_tokens
        FROM requirement_calls WHERE job_id = ?""", (job_id,),
    ).fetchall()
    if not receipts:
        return {**report, "status": "not_run"}
    if len(receipts) != 1:
        return {**report, "status": "ambiguous_receipts"}
    receipt = receipts[0]
    try:
        snapshot = json.loads(receipt["snapshot"])
    except (ValueError, TypeError):
        return {**report, "status": "receipt_mismatch"}
    if not isinstance(snapshot, dict) or snapshot.get("jobId") != job_id or snapshot.get("inputHash") != digest:
        return {**report, "status": "receipt_mismatch"}
    report["attempts"] = receipt["attempts"]
    report["inputTokens"] = receipt["input_tokens"]
    report["outputTokens"] = receipt["output_tokens"]
    if receipt["status"] in {"running", "uncertain"}:
        return {**report, "status": "request_unsettled"}
    if receipt["status"] == "failed":
        return {**report, "status": "request_failed"}
    if receipt["status"] != "completed" or receipt["attempts"] != 1 or receipt["response_status"] != 200:
        return {**report, "status": "receipt_mismatch"}

    extraction = connection.execute(
        """SELECT e.id, e.model, e.input_hash, e.extractor_version, e.prompt_version,
           e.provider, e.requirement_count, t.input_refs, t.error
        FROM job_requirement_extractions e
        JOIN trace_spans t ON t.id = e.trace_run_id AND t.capability = 'requirement_extraction'
        WHERE e.job_id = ? AND e.id = ?""", (job_id, receipt["extraction_id"]),
    ).fetchone()
    if (
        not extraction or extraction["input_hash"] != digest or extraction["error"] is not None
        or extraction["provider"] != "openai" or extraction["model"] != snapshot.get("model")
    ):
        return {**report, "status": "artifact_mismatch"}
    policy = snapshot.get("extractionPolicy")
    if not isinstance(policy, list) or policy[:2] != [extraction["extractor_version"], extraction["prompt_version"]]:
        return {**report, "status": "artifact_mismatch"}
    try:
        trace_input = json.loads(extraction["input_refs"])
    except (ValueError, TypeError):
        return {**report, "status": "artifact_mismatch"}
    if (
        not isinstance(trace_input, dict) or trace_input.get("jobId") != job_id
        or trace_input.get("descriptionSha256") != digest or trace_input.get("providerCalls") != 1
    ):
        return {**report, "status": "artifact_mismatch"}
    requirements = connection.execute(
        """SELECT requirement_index, type, normalized_capability, importance, original_text, evidence_span
        FROM job_requirements WHERE job_id = ? AND extraction_id = ? ORDER BY requirement_index""",
        (job_id, extraction["id"]),
    ).fetchall()
    if not requirements or len(requirements) != extraction["requirement_count"]:
        return {**report, "status": "artifact_mismatch"}
    return {
        **report,
        "model": extraction["model"],
        "extractorVersion": extraction["extractor_version"],
        "promptVersion": extraction["prompt_version"],
        "requirements": len(requirements),
        **_score(case, requirements),
    }


def review(database: Path, manifest: Path, *, dataset: Path = DATASET) -> dict:
    cases = read_job_requirement_eval_cases(dataset)
    if not cases:
        raise ValueError("empty holdout")
    bindings = _check_manifest(json.loads(manifest.read_text(encoding="utf-8")), cases)
    with closing(sqlite3.connect(f"{database.resolve(strict=True).as_uri()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN")
        if connection.execute("SELECT EXISTS(SELECT 1 FROM user_profiles)").fetchone()[0]:
            raise ValueError("only a separate, profile-free holdout database is supported")
        if connection.execute("SELECT count(*) FROM jobs").fetchone()[0] != len(cases):
            raise ValueError("only a database containing exactly this holdout is supported")
        results = [_read_case(connection, case, bindings[case.case_id]) for case in cases]
    return {
        "dataset": dataset.stem,
        "labelChecks": dict(sorted(Counter(item["status"] for item in results).items())),
        "transportProvenance": "not_verified_by_database",
        "requiresManualReview": True,
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="SQLite file in the isolated holdout")
    parser.add_argument("--manifest", type=Path, required=True, help="Case, JobLens ID, exact source hash bindings")
    args = parser.parse_args()
    try:
        report = review(args.db, args.manifest)
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.exit(2, f"Holdout not reviewed: {error}\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if all(item["status"] == "label_checks_passed" for item in report["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
