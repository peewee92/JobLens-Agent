from copy import deepcopy
from decimal import Decimal

import httpx
import pytest

from scripts import eval_real_jds as eval_jds


@pytest.fixture()
def manifest():
    return {
        "profile": {"synthetic": True, "evidence": [{"key": "python", "summary": "合成 Python 项目"}]},
        "samples": [
            {"id": f"fixture-{i}", "sourceId": f"src-{i}", "source": "BOSS直聘",
             "description": f"岗位 {i} 的合成数据。熟悉 Python，能够设计、开发、测试和维护线上接口服务。",
             "sourceReadiness": "complete",
             "gold": [{"anchor": "熟悉 Python", "importance": "must_have", "evidenceKeys": ["python"]}]}
            for i in range(12)
        ],
    }


def test_model_execution_requires_confirm_flag(monkeypatch):
    monkeypatch.setattr(eval_jds, "evaluate", lambda *args: pytest.fail("execution must not start"))
    with pytest.raises(SystemExit) as error:
        eval_jds.main(["--samples", "unused.json", "--round", "V1"])
    assert error.value.code == 2


@pytest.mark.parametrize("invalid", ["count", "duplicate", "private", "false-truncation"])
def test_manifest_rejects_unusable_inputs(manifest, invalid):
    assert eval_jds.validate_manifest(manifest) is manifest
    case = manifest["samples"][0]
    if invalid == "count":
        manifest["samples"].pop()
    elif invalid == "duplicate":
        manifest["samples"][1]["sourceId"] = case["sourceId"]
    elif invalid == "private":
        case["description"] += "联系 someone@example.com"
    else:
        case.update(sourceReadiness="truncated", referenceDescription="不同岗位" * 100)
    with pytest.raises(ValueError):
        eval_jds.validate_manifest(manifest)


def test_missing_retrieval_is_not_missing_extraction(manifest):
    case = manifest["samples"][0]
    item = dict(id="req", originalText="熟悉 Python", evidenceSpan="熟悉 Python", importance="must_have")
    result = eval_jds.check_gold(case, [item], {"req": []}, {"ev": "python"}, [])
    assert result[0]["found"] is True
    assert result[0]["recall"] is False
    assert eval_jds.check_gold(case, [item], {"req": ["ev"]}, {"ev": "python"}, [])[0]["recall"] is True
    assert eval_jds.check_gold(case, [], {}, {"ev": "python"}, [])[0]["found"] is False


def test_prefer_exact_clause_over_adjacent_clause_in_same_citation(manifest):
    case = manifest["samples"][0]
    items = [dict(id="wanted", originalText="熟悉 Python", evidenceSpan="熟悉 Python 或 Java", importance="must_have"),
             dict(id="neighbor", originalText="熟悉 Java 优先", evidenceSpan="熟悉 Python 或 Java", importance="preferred")]
    result = eval_jds.check_gold(case, items, {"wanted": [], "neighbor": ["py"]}, {"py": "python"}, [])
    assert result == [{"found": True, "importance": True, "recall": False, "ruleConflict": False}]


@pytest.mark.parametrize("candidate", [[], ["made_up"], ["real"]])
def test_citations_must_be_in_the_pool_and_candidates(candidate):
    report = {"requirementResults": [{"requirementId": "r", "evidenceIds": ["real"]}]}
    passed, count = eval_jds.check_citations(report, {"real": "python"}, {"r": candidate})
    assert passed is (candidate == ["real"])
    assert count == 1
    assert eval_jds.check_citations(report, {"other": "python"}, {"r": ["real"]})[0] is False


@pytest.mark.parametrize("status,usage,stop", [
    (402, None, "provider_http_402"),
    (429, None, "provider_http_429"),
    (200, {}, "usage_unknown_or_outside_bound"),
])
def test_live_transport_stops_on_http_error_or_unknown_usage(tmp_path, status, usage, stop):
    budget = eval_jds.ArkBudget(tmp_path / "dispatch.json")
    sends = []

    def dispatch(request):
        sends.append(request)
        return httpx.Response(status, json={"usage": usage}, request=request)

    budget.send(ark_request(), dispatch)
    assert budget.stop == stop
    assert budget.entries[0]["inputTokens"] is None
    assert budget.held > 0
    with pytest.raises(httpx.TransportError):
        budget.send(ark_request(), dispatch)
    assert len(sends) == 1


def ark_request(**updates):
    return httpx.Request("POST", eval_jds.ARK + "/chat/completions", json={
        "model": eval_jds.MODEL, "thinking": {"type": "disabled"},
        "max_completion_tokens": eval_jds.OUTPUT_LIMIT, "messages": [{"role": "user", "content": "fixture"}],
        **updates,
    })


def test_budget_precedes_physical_send(tmp_path, monkeypatch):
    ledger = tmp_path / "dispatch.json"
    budget = eval_jds.ArkBudget(ledger)

    def dispatch(request):
        assert eval_jds.load(ledger)[0]["status"] is None
        return httpx.Response(200, json={"usage": {"prompt_tokens": 1000, "completion_tokens": 100}}, request=request)

    budget.send(ark_request(), dispatch)
    assert budget.held == Decimal("0.0064")
    monkeypatch.setattr(eval_jds, "LIMIT", Decimal("0.01"))
    with pytest.raises(httpx.TransportError):
        budget.send(ark_request(), lambda _: pytest.fail("must not dispatch above envelope"))
    assert budget.stop == "budget_limit"


def test_unpriced_request_rejected_before_send(tmp_path):
    budget = eval_jds.ArkBudget(tmp_path / "dispatch.json")
    with pytest.raises(httpx.TransportError):
        budget.send(ark_request(max_completion_tokens=10000), lambda _: pytest.fail("must not send"))
    assert budget.stop == "unpriced_request"
    assert budget.entries == []


def test_rounds_refuse_mismatched_input_or_fixture_results(manifest):
    good = {"mode": "live", "round": "V1", "inputSha256": eval_jds.digest(manifest),
            "rows": [{"id": x["id"]} for x in manifest["samples"]]}
    eval_jds.verify_rounds(manifest, good, None)
    wrong = deepcopy(manifest)
    wrong["samples"][0]["description"] += " changed"
    with pytest.raises(ValueError):
        eval_jds.verify_rounds(wrong, good, None)
    with pytest.raises(ValueError):
        eval_jds.verify_rounds(manifest, {**good, "mode": "offline"}, None)


def test_rejection_does_not_pretend_to_be_a_hallucination():
    cause, _ = eval_jds.finding({"outcome": "blocked", "citationsRejected": True}, None)
    assert cause is None


def test_isolated_dry_run_uses_real_routes_without_touching_configured_db(tmp_path, manifest):
    import os
    import sqlite3
    import subprocess
    import sys
    from contextlib import closing

    formal = tmp_path / "formal.db"
    with closing(sqlite3.connect(formal)) as cx:
        cx.execute("CREATE TABLE keep_me(value TEXT)")
        cx.execute("INSERT INTO keep_me VALUES ('formal data')")
        cx.commit()
    before = formal.read_bytes()
    manifest["profile"].update(headline="合成资料", yearsOfExperience=2, skills=[])
    manifest["profile"]["evidence"][0].update(
        type="project", source="合成", summary="使用 Python 开发和维护内部 Flask 接口"
    )
    for i, case in enumerate(manifest["samples"]):
        case.update(title=f"合成测试岗位 {i}", company="合成公司")
    last = manifest["samples"][-1]
    last.update(sourceReadiness="truncated", referenceDescription=last["description"] + "独立后半段" * 20,
                gold=[])
    input_file = tmp_path / "manifest.json"
    eval_jds.store(input_file, manifest)
    run_dir = tmp_path / "offline"
    result = subprocess.run(
        [sys.executable, "-c", """from pathlib import Path
from scripts import eval_real_jds as e
import sys
e.evaluate(e.validate_manifest(e.load(Path(sys.argv[1]))), Path.cwd(), Path(sys.argv[2]), None, 'Dry-run')
""", str(input_file), str(run_dir)],
        cwd=eval_jds.ROOT / "services/backend",
        env={**os.environ, "DATABASE_URL": f"sqlite:///{formal}", "OPENAI_API_KEY": "must-not-use",
             "REQUIREMENT_EXTRACTOR_PROVIDER": "openai", "SEMANTIC_MATCH_PROVIDER": "openai"},
        text=True, capture_output=True, check=True, timeout=50,
    )
    assert "completed" in result.stdout
    offline = eval_jds.load(run_dir / "result.json")
    assert not offline["actualRequests"] and not (run_dir / "dispatch.json").exists()
    assert [row["outcome"] for row in offline["rows"]] == ["completed"] * 11 + ["truncated"]
    assert formal.read_bytes() == before
    with closing(sqlite3.connect(run_dir / "local.db")) as cx:
        for table in ("requirement_calls", "semantic_calls"):
            assert cx.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)
        assert cx.execute("SELECT count(*) FROM match_reports").fetchone() == (11,)
    before_rescore = (run_dir / "local.db").read_bytes()
    subprocess.run(
        [sys.executable, "-c", """from pathlib import Path
from scripts import eval_real_jds as e
import sys
e.rescore(e.validate_manifest(e.load(Path(sys.argv[1]))), Path.cwd(), Path(sys.argv[2]))
""", str(input_file), str(run_dir)], cwd=eval_jds.ROOT / "services/backend",
        capture_output=True, check=True, timeout=50,
    )
    assert eval_jds.load(run_dir / "rescored.json")["readOnlyRescore"] is True
    assert (run_dir / "local.db").read_bytes() == before_rescore
    assert not (run_dir / "dispatch.json").exists()
