"""Synthetic descriptions from the first-use audit, exercising real SQLite and offline extraction."""
from hashlib import sha256
from unittest.mock import Mock

from app.db.models import TraceSpanORM
from app.repositories.sqlalchemy_trace_repository import SqlAlchemyTraceRepository
from app.application.tracing import TraceWrite
from app.workflows.job_requirement_extraction import ExtractJobRequirementsWorkflow

from .test_analysis_update_plan import _dump
from .test_first_job_journey import first_user, save_inputs
from .test_three_job_journey import prepare

HARDWARE = (
    "任职要求：至少5年以上工作经验，能够以实际从业记录说明。\n"
    "任职要求：熟练掌握数字电路测试，能独立完成板级调试和信号完整性验证。"
)
INCOMPLETE = "协助团队推进新产品；工作地点、岗位要求和任职条件待补充。"
FAILING = "任职要求：熟练掌握光刻机校准，能独立完成板级调试和信号完整性验证。\n任职要求：至少5年以上工作经验，能够以实际从业记录说明。"
PYTHON = "任职要求：熟练掌握 Python，能够以实际项目说明服务开发经验。\n加分项：熟悉 Docker 部署，能够说明一次容器化上线过程。"


def manual_job(client, title, description):
    result = client.post("/api/v1/job-imports/manual", json={
        "title": title, "company": "合成 UX 验收公司", "description": description,
    })
    assert result.status_code == 201, result.text
    return result.json()["jobId"]


def preflight(client, ids):
    response = client.get("/api/v1/match-ranking/preflight", params=[("jobId", item) for item in ids])
    assert response.status_code == 200, response.text
    return response.json()


def test_hardware_preserves_original_fact_confirmation_and_hard_experience_conflict(first_user):
    client, factory = first_user
    save_inputs(client, supported=True)
    job = manual_job(client, "高级硬件验证工程师", HARDWARE)
    path = f"/api/v1/jobs/{job}"
    extracted = client.post(path + "/requirement-extractions")
    assert extracted.status_code == 201, extracted.text
    facts = extracted.json()
    skill = next(item for item in facts["requirements"] if item["normalizedCapability"] == "数字电路测试")
    assert skill["evidenceSpan"] in HARDWARE and skill["originalText"] in HARDWARE
    with factory() as session:
        trace = session.get(TraceSpanORM, facts["traceRunId"])
        assert trace.input_refs["providerCalls"] == 0 and trace.error is None
    assert preflight(client, [job])["omissions"][0]["recoveryCode"] == "requirements_need_review"
    assert client.get(path + "/match-input-readiness").json()["inputsReleaseEligible"] is False
    confirmed = client.post(path + "/requirement-confirmations", json={
        "actionId": "hardware-confirm", "extractionId": facts["extractionId"], "inputHash": facts["inputHash"],
        "factsDigest": facts["factsDigest"], "confirmed": True,
    })
    assert confirmed.status_code == 200, confirmed.text
    assert preflight(client, [job])["omissions"][0]["recoveryCode"] is None
    match = client.post(path + "/match-report")
    assert match.status_code == 200, match.text
    report = match.json()
    assert report["recommendation"] == report["eligibility"] == "blocked"
    years = next(item for item in report["requirementResults"] if "yearsOfExperience" in item["profileFactRefs"])
    assert years["eligibilityStatus"] == "missing"
    assert "2 年" in years["reason"] and "5 年" in years["reason"]
    assert preflight(client, [job])["omissions"] == [
        {"jobId": job, "reason": "hard_conflict", "staleReasons": [], "recoveryCode": None},
    ]


def test_preflight_distinguishes_incomplete_unanalyzed_and_failed_with_no_writes(first_user, monkeypatch):
    client, factory = first_user
    save_inputs(client, supported=True)
    ranked, _ = prepare(client, "应用工程师", PYTHON)
    short = manual_job(client, "信息残缺的岗位", INCOMPLETE)
    failed = manual_job(client, "未识别能力的岗位", FAILING)
    untouched = manual_job(client, "待分析岗位", FAILING)
    ids = [ranked, short, failed, untouched]
    response = client.post(f"/api/v1/jobs/{failed}/requirement-extractions")
    assert response.status_code == 502, response.text
    assert response.json()["error"]["code"] == "invalid_requirement_extractor_output"
    original = _dump(factory)
    forbidden = Mock(side_effect=AssertionError("preflight must not extract job requirements"))
    monkeypatch.setattr(ExtractJobRequirementsWorkflow, "execute", forbidden)
    body = preflight(client, ids)
    assert [item["jobId"] for item in body["items"]] == [ranked]
    assert [(item["jobId"], item["recoveryCode"]) for item in body["omissions"]] == [
        (short, "description_incomplete"), (failed, "requirement_analysis_failed"),
        (untouched, "requirements_not_analyzed"),
    ]
    assert "normalizedCapability" not in str(body)
    assert _dump(factory) == original
    forbidden.assert_not_called()

    # Stable response distinguishes same job & exact trimmed source revision, not just job id.
    with factory() as session:
        read = SqlAlchemyTraceRepository(session).failed_offline_requirement_jobs
        old_hash = sha256(FAILING.encode()).hexdigest()
        assert read({failed: old_hash, untouched: old_hash}) == {failed}
        assert read({failed: sha256((FAILING + "!").encode()).hexdigest()}) == set()
    with factory.begin() as session:
        SqlAlchemyTraceRepository(session).add(TraceWrite(
            run_id="later-attempt", capability="requirement_extraction", version="test", model="fixture-requirement-extractor",
            prompt_version="test", input_refs={"jobId": failed, "descriptionSha256": old_hash, "providerCalls": 0},
            output=None, error=None, latency_ms=0, input_tokens=None, output_tokens=None,
        ))
    assert preflight(client, [failed])["omissions"][0]["recoveryCode"] == "requirements_not_analyzed"


def test_personal_gap_uses_the_same_confirmed_job_gate_and_still_blocks_stale_or_unchecked(first_user):
    client, factory = first_user
    save_inputs(client, supported=True)
    job = manual_job(client, "应用工程师", PYTHON)
    base = f"/api/v1/jobs/{job}"
    facts = client.post(base + "/requirement-extractions").json()
    def gap():
        result = client.post("/api/v1/target-cohort/gaps", json={
            "cohortId": "personal-gap", "name": "个人目标", "selectedJobIds": [job]})
        assert result.status_code == 200, result.text
        return result.json()
    assert not gap()["factsUsable"]
    confirmed = client.post(base + "/requirement-confirmations", json={
        "actionId": "personal-gap-check", "extractionId": facts["extractionId"],
        "inputHash": facts["inputHash"], "factsDigest": facts["factsDigest"], "confirmed": True})
    assert confirmed.status_code == 200
    assert gap()["factsUsable"], gap()
    from app.application.job_queries.manual_description import description_digest
    changed = client.put(base + "/manual-description", json={
        "description": PYTHON + "\n工作职责：维护应用服务。", "expectedSha256": description_digest(PYTHON)})
    assert changed.status_code == 200
    assert not gap()["factsUsable"]
    with factory() as session:
        from sqlalchemy import text
        assert session.execute(text("SELECT count(*) FROM requirement_review_batch_final_decisions")).scalar_one() == 0
