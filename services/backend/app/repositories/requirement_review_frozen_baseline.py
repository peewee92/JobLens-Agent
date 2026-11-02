"""Validate frozen review evidence before using it as a model-cohort baseline.

The checksum detects accidental changes, not a malicious database administrator.
Target-job release checks remain independent of this cohort-level evidence.
"""
from collections import Counter
from hashlib import sha256
import hmac
import json


def frozen_baseline_policy(record, batch) -> str | None:
    snapshot = record.evidence_snapshot
    digest = record.evidence_snapshot_sha256
    if not isinstance(snapshot, dict) or not isinstance(digest, str):
        return None
    try:
        encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if not hmac.compare_digest(sha256(encoded).hexdigest(), digest):
            return None
        if snapshot["schemaVersion"] != 2 or snapshot.get("baselinePolicy") != "frozen_cohort_v1":
            return None
        detail = snapshot["batch"]
        summary, cases, traces = detail["summary"], detail["cases"], snapshot["traces"]
        if not isinstance(cases, list) or not isinstance(traces, dict):
            return None
        policy = summary["semantic_policy_version"]
        if not isinstance(policy, str) or not policy.strip():
            return None
        if (summary["id"] != record.batch_id or summary["id"] != batch.id
            or summary["reviewer"] != record.reviewer or summary["reviewer"] != batch.reviewer
            or summary["provider"] != batch.provider or summary["provider"].casefold() == "fixture"
            or summary["model"] != batch.model
            or summary["extractor_version"] != batch.extractor_version
            or summary["prompt_version"] != batch.prompt_version
            or summary["sample_size"] != 20 or batch.sample_size != 20
            or summary["sample_size"] != record.sample_size
            or summary["reviewed_count"] != record.reviewed_count
            or summary["accepted_count"] != record.accepted_count
            or summary["rejected_count"] != record.rejected_count
            or summary["stale_case_count"] != record.stale_case_count
            or summary["stale_case_count"] != 0
            or summary["reviewed_count"] != 20
            or summary["accepted_count"] + summary["rejected_count"] != 20
            or summary["completed"] is not True
            or summary["formal_evidence_eligible"] is not True
            or detail["final_decision"] is not None
            or detail["issue_code_counts"] != record.issue_code_counts
            or len(cases) != 20):
            return None
        counts: Counter[str] = Counter()
        fingerprint_cases = []
        seen_case, seen_job, seen_extraction = set(), set(), set()
        accepted = rejected = 0
        for expected_index, case in enumerate(cases):
            review = case["review"]
            trace = traces[case["trace_run_id"]]
            if (case["case_index"] != expected_index or case["is_current"] is not True
                or case["provider"] != summary["provider"] or case["model"] != summary["model"]
                or case["extractor_version"] != summary["extractor_version"]
                or case["prompt_version"] != summary["prompt_version"]
                or case["semantic_policy_version"] != policy
                or not isinstance(case["description"], str)
                or not isinstance(case["requirements"], list)
                or not isinstance(review, dict) or not isinstance(review["notes"], str)
                or not isinstance(review["issue_codes"], list)
                or trace["capability"] != "requirement_extraction"
                or trace["version"] != summary["extractor_version"]
                or trace["model"] != summary["model"]
                or trace["promptVersion"] != summary["prompt_version"]
                or not isinstance(trace["output"], dict)
                or trace["output"].get("semanticPolicyVersion") != policy):
                return None
            seen_case.add(case["id"]); seen_job.add(case["job_id"]); seen_extraction.add(case["extraction_id"])
            if review["decision"] == "accepted": accepted += 1
            elif review["decision"] == "rejected": rejected += 1
            else: return None
            counts.update(review["issue_codes"])
            fingerprint_cases.append({
                "caseId": case["id"], "caseIndex": case["case_index"], "jobId": case["job_id"],
                "extractionId": case["extraction_id"], "traceRunId": case["trace_run_id"],
                "descriptionSha256": sha256(case["description"].encode("utf-8")).hexdigest(),
                "isCurrent": True, "reviewId": review["id"], "reviewDecision": review["decision"],
                "issueCodes": review["issue_codes"], "reviewNotesSha256": sha256(review["notes"].encode("utf-8")).hexdigest(),
                "reviewedAt": review["reviewed_at"],
            })
        if (len(seen_case) != 20 or len(seen_job) != 20 or len(seen_extraction) != 20
            or accepted != record.accepted_count or rejected != record.rejected_count
            or dict(sorted(counts.items())) != record.issue_code_counts):
            return None
        fingerprint_payload = {
            "schemaVersion": "requirement-review-batch-evidence-v1", "batchId": summary["id"],
            "cohort": {"provider": summary["provider"], "model": summary["model"],
                "extractorVersion": summary["extractor_version"], "promptVersion": summary["prompt_version"],
                "semanticPolicyVersion": policy},
            "summary": {"sampleSize": summary["sample_size"], "reviewedCount": summary["reviewed_count"],
                "acceptedCount": summary["accepted_count"], "rejectedCount": summary["rejected_count"],
                "staleCaseCount": summary["stale_case_count"], "issueCodeCounts": dict(sorted(counts.items()))},
            "cases": fingerprint_cases,
        }
        fingerprint = sha256(json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest()
        return policy if hmac.compare_digest(fingerprint, record.evidence_fingerprint) else None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def intact_legacy_snapshot(record) -> bool:
    """Version 1 was collected before frozen-baseline semantics were announced."""
    snapshot, digest = record.evidence_snapshot, record.evidence_snapshot_sha256
    if not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != 1 or not isinstance(digest, str):
        return False
    try:
        encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hmac.compare_digest(sha256(encoded).hexdigest(), digest)
    except (TypeError, ValueError):
        return False
