"""Run a paired JD evaluation through the existing local HTTP routes."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from time import perf_counter
from unittest.mock import patch
from urllib.parse import quote

import httpx

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = ROOT / "data/private"
REPORT = ROOT / "docs/evals/REAL-MODEL-BAD-CASE-EVAL.md"
MODEL = "doubao-seed-2-0-lite-260428"
ARK = "https://ark.cn-beijing.volces.com/api/v3"
PRICE = "https://docs.volcengine.com/docs/ark/model-pricing?lang=zh"
MODEL_LIMITS = "https://docs.volcengine.com/docs/ark/model-list?lang=zh"
INPUT_LIMIT, OUTPUT_LIMIT, SEND_LIMIT = 256 * 1024, 4096, 27
# Rates conservatively exceed the top public text-only tier.
INPUT_RATE, OUTPUT_RATE = Decimal("4"), Decimal("24")
LIMIT = Decimal("5")
CONTACT = re.compile(
    r"https?://|www\.|[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?<!\d)(?:\+?86[ -]?)?1[3-9]\d{9}(?!\d)"
    r"|(?:微信号|手机号|联系电话|wechat\s*id|securityId|sessionid|cookie|access_token)\s*[:：=]", re.I
)
ID = re.compile(r"[A-Za-z0-9_-]{1,64}")
CAUSES = {
    "truncation": ("① 上游截断", "补采详情；短版进入待补采状态"),
    "retrieval": ("② 召回缺失", "核对检索词和证据键，补召回回归"),
    "rule": ("③ 规则口径误伤", "对照原文约束，修正规则并固定回归"),
    "hallucination": ("④ 模型幻觉", "针对错误依据加约束，保留拒绝保存回归"),
}


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def store(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def normalize(s):
    return re.sub(r"\s+", "", s).casefold()


def validate_manifest(data):
    samples, profile = data["samples"], data["profile"]
    if not 12 <= len(samples) <= 15:
        raise ValueError("样本必须为 12–15 条")
    if profile.get("synthetic") is not True or not profile.get("evidence"):
        raise ValueError("仅允许标记为合成的非空评测证据池")
    keys = [e["key"] for e in profile["evidence"]]
    if len(set(keys)) != len(keys) or any(CONTACT.search(e["summary"]) for e in profile["evidence"]):
        raise ValueError("证据键重复或存在不允许发送的联系信息")
    ids, bodies, sources = set(), set(), set()
    for case in samples:
        case_id, body, source_id = case["id"], case["description"], case["sourceId"]
        normalized = normalize(body)
        if (not ID.fullmatch(case_id) or case_id in ids or not normalized or normalized in bodies
                or not ID.fullmatch(source_id) or source_id in sources):
            raise ValueError("样本 ID、来源或正文为空／重复")
        ids.add(case_id)
        bodies.add(normalized)
        sources.add(source_id)
        if case["source"] != "BOSS直聘" or CONTACT.search(body):
            raise ValueError("只接受去除链接、会话参数与联系方式的 BOSS 正文")
        if case["sourceReadiness"] == "truncated":
            reference = normalize(case["referenceDescription"])
            if normalized not in reference or len(reference) - len(normalized) < 80:
                raise ValueError("截断样本缺少同岗长版对照")
        elif case["sourceReadiness"] != "complete" or not case["gold"]:
            raise ValueError("可评测样本必须有预先冻结的参考条款")
        for gold in case["gold"]:
            if (gold["importance"] not in {"must_have", "preferred", "bonus"}
                    or len(normalize(gold["anchor"])) < 4 or normalize(gold["anchor"]) not in normalized
                    or not set(gold.get("evidenceKeys", [])) <= set(keys)):
                raise ValueError("参考条款必须锚定原文且只引用合成证据键")
    return data


def private_path(path):
    resolved = path.resolve()
    if not resolved.is_relative_to(PRIVATE.resolve()) or not PRIVATE.resolve().is_relative_to(ROOT):
        raise ValueError("样本、评测数据和私有配置必须位于 Git 忽略的 data/private 下")
    return resolved


def cost(prompt, completion):
    return (INPUT_RATE * prompt + OUTPUT_RATE * completion) / 1_000_000


class ArkBudget:
    """Keep one worst-case reservation in-flight before physical dispatch."""

    def __init__(self, path):
        self.path = path
        self.entries = []
        self.stop = None

    @property
    def held(self):
        return sum(Decimal(item["heldCny"]) for item in self.entries)

    def send(self, request, dispatch):
        body = json.loads(request.content)
        # The compatible adapter uses a generic flag; Ark documents the thinking object.
        disabled = body.get("thinking") == {"type": "disabled"} or (
            "thinking" not in body and body.get("enable_thinking") is False
        )
        if (request.method != "POST" or str(request.url) != ARK + "/chat/completions"
                or body.get("model") != MODEL or not disabled
                or body.get("max_completion_tokens") != OUTPUT_LIMIT or not body.get("messages")
                or set(body) - {"model", "messages", "stream", "temperature", "response_format",
                                "max_completion_tokens", "thinking", "enable_thinking"}
                or body.get("stream", False) is not False
                or any(not isinstance(item.get("content"), str)
                       or (item.get("role") == "user" and CONTACT.search(item["content"]))
                       for item in body["messages"])):
            self.stop = "unpriced_request"
            raise httpx.TransportError("Ark request outside priced envelope")
        body.pop("enable_thinking", None)
        body["thinking"] = {"type": "disabled"}
        headers = request.headers.copy()
        headers.pop("content-length", None)
        request = httpx.Request(request.method, request.url, headers=headers, json=body,
                                extensions=request.extensions)
        reserve = cost(INPUT_LIMIT, OUTPUT_LIMIT)
        if self.stop or len(self.entries) >= SEND_LIMIT or self.held + reserve > LIMIT:
            self.stop = self.stop or "budget_limit"
            raise httpx.TransportError("Ark budget closed before dispatch")
        entry = {"heldCny": str(reserve), "status": None, "inputTokens": None, "outputTokens": None}
        self.entries.append(entry)
        store(self.path, self.entries)
        try:
            response = dispatch(request)
            response.read()
        except (httpx.HTTPError, OSError):
            self.stop = "transport_uncertain"
            raise
        entry["status"] = response.status_code
        if response.is_success:
            try:
                payload = response.json()
                usage = payload.get("usage") if isinstance(payload, dict) else None
            except ValueError:
                usage = None
            usage = usage if isinstance(usage, dict) else {}
            prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
            if (type(prompt) is int and 0 < prompt <= INPUT_LIMIT
                    and type(completion) is int and 0 <= completion <= OUTPUT_LIMIT):
                entry.update(inputTokens=prompt, outputTokens=completion, heldCny=str(cost(prompt, completion)))
            else:
                self.stop = "usage_unknown_or_outside_bound"
        else:
            self.stop = f"provider_http_{response.status_code}"
        store(self.path, self.entries)
        return response

    def transport(self):
        budget = self

        class Guard(httpx.HTTPTransport):
            sent = False

            def handle_request(self, request):
                if self.sent:
                    budget.stop = "duplicate_dispatch"
                    raise httpx.TransportError("No second send for one authorization")
                self.sent = True
                return budget.send(request, super().handle_request)

        return Guard(retries=0, trust_env=False)


def configure(backend, directory, model_config, *, read_only=False):
    if "app.core.config" in sys.modules:
        raise RuntimeError("评测后端必须在独立脚本进程启动")
    prefixes = ("OPENAI_", "JOBLENS_", "REQUIREMENT_", "SEMANTIC_", "PROFILE_", "CAREER_")
    env = {key: value for key, value in os.environ.items() if not key.startswith(prefixes)}
    database = directory / "local.db"
    db_url = f"sqlite:///{database}"
    if read_only:
        if not database.is_file() or database.is_symlink():
            raise ValueError("只允许重算已经存在的隔离库")
        db_url = f"sqlite:///file:{quote(str(database), safe='/')}?mode=ro&uri=true"
    env.update(
        DATABASE_URL=db_url,
        APP_ENV="local", JOBLENS_LOCAL_PRODUCT="1" if model_config else "0",
        JOBLENS_LOCAL_CONFIG=str(model_config or ""),
        CAREER_AGENT_CHECKPOINT_PATH=str(directory / "checkpoint.db"),
        REQUIREMENT_ACCEPTANCE_PRIVATE_ROOT=str(directory / "acceptance"),
        REQUIREMENT_EXTRACTOR_FALLBACK_PROVIDER="disabled",
        CAREER_INTENT_PROVIDER="disabled", PROFILE_EXTRACTOR_PROVIDER="disabled",
    )
    if model_config:
        for family in ("REQUIREMENT_EXTRACTOR", "SEMANTIC_MATCH"):
            env[f"{family}_ENABLE_THINKING"] = "false"
            env[f"{family}_MAX_COMPLETION_TOKENS"] = str(OUTPUT_LIMIT)
    else:
        env.update(OPENAI_API_KEY="", OPENAI_BASE_URL="http://127.0.0.1:1",
                   REQUIREMENT_EXTRACTOR_PROVIDER="fixture", SEMANTIC_MATCH_PROVIDER="fixture")
    os.environ.clear()
    os.environ.update(env)
    sys.path.insert(0, str(backend))
    os.chdir(directory)  # Never auto-load the checkout's normal .env.
    from app.core.config import get_settings

    cfg = get_settings()
    if model_config and (
        cfg.openai_base_url.rstrip("/") != ARK or not cfg.openai_api_key or any(
            getattr(cfg, f"{family}_provider") != "openai"
            or getattr(cfg, f"{family}_model") != MODEL
            or getattr(cfg, f"{family}_api_style") != "chat_completions"
            for family in ("requirement_extractor", "semantic_match")
        )
    ):
        raise ValueError("方舟配置与已核定的北京区 Seed 2.0 Lite 文本计价范围不一致")
    if read_only:
        return
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    command.upgrade(cfg, "head")


@contextmanager
def backend_client(budget):
    from app.main import create_app
    from fastapi.testclient import TestClient

    with ExitStack() as stack:
        if budget:
            stack.enter_context(patch("app.byok.calls.transport_factory", return_value=budget.transport))
        else:
            from app.domain.job_requirements import RequirementType
            from app.llm.job_requirement_extractors import FixtureJobRequirementExtractor

            class GroundedFixture(FixtureJobRequirementExtractor):
                def extract(self, description):
                    result = super().extract(description)
                    # The stock fixture leaves unknown skills without a label and the real validator
                    # rejects them. Supply only their own exact text, never the frozen answers.
                    items = tuple(replace(item, normalized_capability=item.original_text)
                                  if item.type is RequirementType.SKILL and not item.normalized_capability else item
                                  for item in result.output.requirements)
                    return replace(result, output=replace(result.output, requirements=items))

            stack.enter_context(patch("app.api.deps.build_job_requirement_extractor", return_value=GroundedFixture()))
            stack.enter_context(patch.object(httpx.HTTPTransport, "handle_request",
                                            side_effect=AssertionError("offline transport is disabled")))
        yield stack.enter_context(TestClient(create_app(enable_local_capture=False), follow_redirects=False))


class StageError(Exception):
    pass


def api(client, method, path, payload=None):
    response = client.request(method, "/api/v1" + path, **({"json": payload} if payload is not None else {}))
    try:
        data = response.json()
    except ValueError:
        raise StageError(f"local_http_{response.status_code}") from None
    if not response.is_success:
        code = (data.get("error") or {}).get("code") if isinstance(data, dict) else None
        raise StageError(code if isinstance(code, str) and ID.fullmatch(code) else f"local_http_{response.status_code}")
    return data


def seed(client, synthetic):
    profile = api(client, "PUT", "/profile", {**{k: v for k, v in synthetic.items() if k != "synthetic"},
                                              "expectedVersion": 0})
    api(client, "PUT", "/search-intent", dict(expectedVersion=0, targetRoles=["软件工程师"],
        cities=[], remoteAccepted=None, minimumSalaryK=None, seniority=None,
        employmentTypes=[], excludeKeywords=[], hardConstraints=[], softPreferences=[]))
    return {item["id"]: item["key"] for item in profile["evidence"]}


def auth_call(client, path, kind, plan):
    return api(client, "POST", path + f"/{kind}-calls", {
        "actionId": f"eval-{kind}-{plan['jobId']}", "planDigest": plan["planDigest"],
        "confirmed": True, "maxProviderCalls": 1,
    })


def check_citations(report, pool, candidates):
    references = 0
    for field in ("requirementResults", "evidenceLinks", "strengths", "risks"):
        for row in report.get(field, []):
            for ref in row["evidenceIds"]:
                references += field == "requirementResults"
                if ref not in pool or ref not in candidates.get(row["requirementId"], ()):
                    return False, references
    return True, references


def check_gold(case, requirements, candidates, pool, eligible):
    facts = {item["requirementId"]: item["status"] for item in eligible}
    output = []
    for gold in case["gold"]:
        anchor = normalize(gold["anchor"])
        found = [item for item in requirements if anchor in normalize(item["originalText"])]
        if not found:
            found = [item for item in requirements if anchor in normalize(item["evidenceSpan"])]
        retrieved = {pool.get(k) for item in found for k in candidates.get(item["id"], [])}
        output.append({
            "found": bool(found),
            "importance": bool(found) and {item["importance"] for item in found} == {gold["importance"]},
            "recall": bool(retrieved & set(gold["evidenceKeys"])) if gold.get("evidenceKeys") else None,
            "ruleConflict": gold["importance"] != "must_have" and any(
                facts.get(item["id"]) == "missing" for item in found if item["importance"] == "must_have"
            ),
        })
    return output


def candidate_ids(evidence):
    return {item["requirementId"]: {c["evidenceId"] for c in item["candidates"]}
            for item in evidence["requirements"]}


def run_case(client, case, pool, budget):
    from app.application.job_requirements.description_readiness import description_length_blocker

    stage, started = "原文", perf_counter()
    row = {"id": case["id"], "source": case["source"], "readiness": case["sourceReadiness"],
           "readinessBlocker": description_length_blocker(case["description"]), "calls": []}
    try:
        if row["readiness"] == "truncated":
            # Offline only: retain both views for browser inspection without extraction.
            if not budget:
                for key, label in (("description", "短版"), ("referenceDescription", "长版对照")):
                    row[key + "JobId"] = api(client, "POST", "/job-imports/manual", {
                        "title": case["title"] + f"（{label}）", "company": case["company"], "description": case[key],
                    })["jobId"]
            row.update(stage=stage, outcome="truncated")
            return row
        if row["readinessBlocker"]:
            raise StageError(row["readinessBlocker"])
        stage = "导入"
        job = api(client, "POST", "/job-imports/manual", {
            k: case[k] for k in ("title", "company", "description")
        })["jobId"]
        row["jobId"] = job
        path = f"/jobs/{job}"
        stage = "提取"
        if budget:
            plan = api(client, "GET", path + "/requirement-call-plan")
            if not plan["available"]:
                raise StageError(plan["blockerCode"])
            receipt = auth_call(client, path, "requirement", plan)
            row["calls"].append(receipt)
            if receipt["status"] != "completed":
                raise StageError(receipt["errorCode"] or receipt["status"])
            result = api(client, "GET", path + "/requirement-extractions/" + receipt["extractionId"])
        else:
            result = api(client, "POST", path + "/requirement-extractions")
        row["extraction"] = {k: result[k] for k in ("extractorVersion", "promptVersion", "requirementCount")}
        stage = "评测确认"
        api(client, "POST", path + "/requirement-confirmations", {
            **{k: result[k] for k in ("extractionId", "inputHash", "factsDigest")},
            "actionId": f"eval-check-{job}", "confirmed": True,
        })
        stage = "召回"
        evidence = api(client, "GET", path + "/evidence-candidates")
        eligible = api(client, "GET", path + "/eligibility")
        candidates = candidate_ids(evidence)
        row.update(candidateCount=evidence["candidateCount"], eligibility=eligible["eligibility"])
        row["gold"] = check_gold(case, result["requirements"], candidates, pool, eligible["requirements"])
        stage = "匹配"
        if budget:
            if budget.stop:
                raise StageError(budget.stop)
            plan = api(client, "GET", path + "/semantic-call-plan")
            if plan["available"]:
                receipt = auth_call(client, path, "semantic", plan)
                row["calls"].append(receipt)
                if receipt["status"] != "completed":
                    raise StageError(receipt["errorCode"] or receipt["status"])
                row["reportId"] = receipt["reportId"]
            elif plan["blockerCode"] != "semantic_model_not_needed":
                raise StageError(plan["blockerCode"])
        if "reportId" not in row:
            report = api(client, "POST", path + "/match-report")
            if budget and report["providerCalls"] != 0:
                raise StageError("unexpected_legacy_provider_call")
        history = api(client, "GET", path + "/match-reports")
        reports = [item for item in history["items"] if item["isCurrent"]
                   and item["reportId"] == row.get("reportId", item["reportId"])]
        if len(reports) != 1:
            raise StageError("saved_report_not_found")
        report = reports[0]["report"]
        row["reportId"] = reports[0]["reportId"]
        row["citationsOk"], row["citationCount"] = check_citations(report, pool, candidates)
        row.update(outcome="completed", stage="完成", recommendation=report["recommendation"],
                   versions={k: report[k] for k in ("policyVersion", "retrievalVersion", "promptVersion")})
    except StageError as error:
        row.update(outcome="blocked", stage=stage, error=str(error))
        if stage == "匹配" and str(error) == "semantic_output_not_grounded":
            row["citationsRejected"] = True
    finally:
        row["elapsedMs"] = round((perf_counter() - started) * 1000)
    return row


def provenance(backend):
    top = backend.parents[1]
    revision = subprocess.check_output(["git", "-C", str(top), "rev-parse", "HEAD"], text=True).strip()
    files = sorted([*backend.joinpath("app").rglob("*.py"), *backend.joinpath("alembic").rglob("*.py"),
                    backend / "uv.lock", backend / "pyproject.toml"])
    fingerprint = sha256()
    for path in files:
        fingerprint.update(str(path.relative_to(backend)).encode() + b"\0" + sha256(path.read_bytes()).digest())
    return {"revision": revision, "codeSha256": fingerprint.hexdigest()}


def evaluate(manifest, backend, directory, model_config, label):
    trace = {"round": label, "mode": "live" if model_config else "offline", "rows": [],
             "inputSha256": digest(manifest), **provenance(backend)}
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    result_path = directory / "result.json"
    store(result_path, trace)
    budget = ArkBudget(directory / "dispatch.json") if model_config else None
    try:
        configure(backend, directory, model_config)
        with backend_client(budget) as client:
            pool = seed(client, manifest["profile"])
            for case in manifest["samples"]:
                if budget and budget.stop and case["sourceReadiness"] != "truncated":
                    row = {"id": case["id"], "source": case["source"], "readiness": case["sourceReadiness"],
                           "outcome": "not_run", "stage": "未运行", "error": budget.stop, "calls": []}
                else:
                    row = run_case(client, case, pool, budget)
                    if budget and row.get("error") in {"live_provider_not_configured", "uncertain", "running",
                                                       "semantic_call_save_uncertain", "local_http_503"}:
                        budget.stop = budget.stop or row["error"]
                trace["rows"].append(row)
                trace.update(actualRequests=len(budget.entries) if budget else 0,
                             heldCny=str(budget.held) if budget else "0", stop=budget.stop if budget else None)
                store(result_path, trace)
                print(row["id"], row["stage"], row["outcome"], row.get("error", ""), flush=True)
    finally:
        store(result_path, trace)
    return trace


def verify_rounds(manifest, v1, v2):
    ids = [case["id"] for case in manifest["samples"]]
    for trace, label in ((v1, "V1"), (v2, "V2")):
        if trace and (trace["mode"] != "live" or trace["round"] != label
                      or trace["inputSha256"] != digest(manifest) or [r["id"] for r in trace["rows"]] != ids):
            raise ValueError("仅可汇总使用同一冻结输入的真实 V1/V2")


def rescore(manifest, backend, directory):
    """Re-score references from saved facts over read-only routes, without new inference."""
    trace = load(directory / "result.json")
    facts = provenance(backend)
    if trace["inputSha256"] != digest(manifest) or any(trace[k] != v for k, v in facts.items()):
        raise ValueError("重算必须使用原评测的输入和后端版本")
    cases = {case["id"]: case for case in manifest["samples"]}
    if [row["id"] for row in trace["rows"]] != list(cases):
        raise ValueError("评测运行尚未完整写出台账")
    configure(backend, directory, None, read_only=True)
    with backend_client(None) as client:
        profile = api(client, "GET", "/profile")
        pool = {item["id"]: item["key"] for item in profile["evidence"]}
        for row in trace["rows"]:
            if "gold" not in row:
                continue
            path = "/jobs/" + row["jobId"]
            requirements = api(client, "GET", path + "/requirements")
            evidence = api(client, "GET", path + "/evidence-candidates")
            eligible = api(client, "GET", path + "/eligibility")
            extraction_ids = {c["extractionId"] for c in row["calls"] if c.get("extractionId")}
            extraction_ids.update([requirements["extractionId"], evidence["extractionId"], eligible["extractionId"]])
            if len(extraction_ids) != 1 or evidence["profileVersion"] != profile["version"]:
                raise ValueError("重算输入和已保存的评测事实不一致")
            row["gold"] = check_gold(cases[row["id"]], requirements["requirements"],
                                     candidate_ids(evidence), pool, eligible["requirements"])
    trace["readOnlyRescore"] = True
    path = directory / "rescored.json"
    store(path, trace)
    print(path)


def ratio(num, den):
    return f"{num}/{den}（{num / den:.1%}）" if den else "—（0 可核验）"


def metrics(manifest, trace):
    rows = {row["id"]: row for row in trace["rows"]}
    expected = [case for case in manifest["samples"] if case["sourceReadiness"] == "complete"]
    checked = [rows[case["id"]]["gold"] for case in expected if "gold" in rows[case["id"]]]
    clauses = [item for row in checked for item in row]
    recall = [item["recall"] for item in clauses if item["recall"] is not None]
    citation = [row for row in rows.values() if row.get("citationCount", 0)
                or row.get("citationsRejected") or row.get("citationsOk") is False]
    elapsed = [row["elapsedMs"] for row in rows.values() if row["outcome"] == "completed"]
    received = [row for row in rows.values() if row["outcome"] == "completed" and row["calls"]
                and all(call["inputTokens"] is not None and call["outputTokens"] is not None for call in row["calls"])]
    totals = [sum(c["inputTokens"] + c["outputTokens"] for c in row["calls"]) for row in received]
    return [
        ratio(sum(all(item["found"] for item in r) for r in checked), len(rows))
        + f"（已核对提取 {len(checked)}/{len(expected)}）",
        ratio(sum(recall), sum(bool(g.get("evidenceKeys")) for c in expected for g in c["gold"]))
        + f"（可核对 {len(recall)}）",
        ratio(sum(item["importance"] for item in clauses), sum(len(c["gold"]) for c in expected))
        + f"（可核对 {len(clauses)}）",
        ratio(sum(bool(row.get("citationsOk")) for row in citation), len(citation))
        + f"（有引用可验或校验拒绝 {len(citation)}/{len(expected)}）",
        f"{sum(elapsed) / len(elapsed):.0f} ms（n={len(elapsed)}）" if elapsed else "—",
        f"{sum(totals) / len(totals):.1f}（n={len(totals)}）" if totals else "—",
    ]


def finding(row, manual):
    if manual and manual.get("phenomenon") and manual.get("verified") is True:
        return manual.get("cause"), manual["phenomenon"]
    if row["outcome"] == "truncated":
        return "truncation", "同岗短版是长版的子集；评测脚本拦下，未发模型"
    if row.get("citationsOk") is False:
        return "hallucination", "报告包含不在原池或对应候选集的证据 ID"
    if row.get("citationsRejected"):
        return None, "匹配输出被校验拒绝，未保存；单凭错误码不能定性"
    if row["outcome"] != "completed":
        return None, row.get("error", "未完成")
    if any(item["recall"] is False and item["found"] and item["importance"] for item in row.get("gold", [])):
        return None, "条款与口径可定位，但未召回预期证据；待人工区分检索或参考设定"
    if any(item["recall"] is False for item in row.get("gold", [])):
        return None, "冻结参考条款有证据，自动检查未召回；待区分提取与检索"
    if not all(item["importance"] for item in row.get("gold", [])):
        return None, "条款缺失或口径与冻结参考不同，待抽检"
    if not row["candidateCount"]:
        return None, "候选为零；没有已知漏召回证据"
    return None, "自动检查未见缺口；待抽检"


def safe_cell(value):
    return str(value).replace("|", "｜").replace("\n", " ").replace("\r", " ")


def markdown(manifest, offline=None, v1=None, v2=None, review=None):
    verify_rounds(manifest, v1, v2)
    if offline and (offline["mode"] != "offline" or offline["inputSha256"] != digest(manifest)):
        raise ValueError("离线回执与冻结输入不一致")
    review = review or {}
    ids = {case["id"] for case in manifest["samples"]}
    for sample_id, note in review.items():
        if (sample_id not in ids or note.get("cause") not in {*CAUSES, None}
                or any(not isinstance(note.get(field, ""), str) or CONTACT.search(note.get(field, ""))
                       for field in ("phenomenon", "repair"))
                or note.get("stage") not in {None, "原文", "提取", "召回", "资格规则", "匹配"}):
            raise ValueError("人工复核只能引用样本 ID、四象限主因和脱敏短描述")
    tracks = {tr["round"]: {row["id"]: row for row in tr["rows"]} for tr in (offline, v1, v2) if tr}
    version1, version2 = tracks.get("V1", {}), tracks.get("V2", {})
    lines = ["# 真实模型 Bad Case 评测：BOSS 直聘", "",
             "> 本报告只含脱敏台账。离线结果不计入 V1/V2；冻结参考和本轮辅助走查不等于独立人工抽检。", "",
             f"- 冻结样本：{len(manifest['samples'])} 条；输入指纹：{digest(manifest)}。",
             "- 两轮均复用产品接口和独立 SQLite；脚本内确认不算人工验收。",
             "- 提取、召回和口径是冻结定向参考的覆盖检查，不等于覆盖原文全部要求。",
             "- 条款比对优先使用要求原句，仅在原句未命中时回看引用段，避免混入相邻条款。",
             "- 事实引用合规仅自动校验 ID 的集合归属；有引用不等于文字结论正确，无引用不当成通过。",
             "- 平均耗时、Token 只统计完成对应链路且数据已知的样本。", ""]
    for trace in (offline, v1, v2):
        if trace:
            lines.append(f"- {trace['round']}：提交 {trace['revision']}，代码指纹 {trace['codeSha256']}，"
                         f"实际请求 {trace.get('actualRequests', 0)} 次，停止原因 {trace.get('stop') or '无'}。")
            if trace["mode"] == "live":
                lines.append(f"  按保守上界保留 ¥{trace.get('heldCny', '未知')}；不是实际账单。")
            if trace.get("readOnlyRescore"):
                lines.append("  引文归属使用已保存事实只读重算；未重发请求。")
    if v1 or v2:
        lines.extend([f"- 方舟：[官方价格]({PRICE})、[模型上限]({MODEL_LIMITS})；实际账单未核对。", ""])
    lines.extend(["## 逐条台账", "",
                  "| 样本 | 来源 | 离线状态 | V1 故障环节／业务现象 | 主因 | 修复建议 | V1 候选数／耗时／输入+输出 Token | V2 复测 |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"])
    for case in manifest["samples"]:
        key = case["id"]
        off = tracks.get("Dry-run", {}).get(key, {})
        row = version1.get(key)
        note = review.get(key, {})
        cause, phenomenon = (finding(row, note) if row else
                             finding(off, None) if off else (None, "未运行"))
        category, repair = CAUSES.get(cause, ("待核实", "对照参考和接口回执"))
        if note.get("verified") is True and note.get("repair"):
            repair = note["repair"]
        tokens = "—"
        if row and row["outcome"] != "not_run":
            calls = row["calls"]
            tokens = "+".join(str(sum(c[k] for c in calls)) if all(c[k] is not None for c in calls) else "未知"
                              for k in ("inputTokens", "outputTokens"))
            tokens = f"{row.get('candidateCount', '—')}／{row.get('elapsedMs', '—')} ms／{tokens}"
        stage_name = note.get("stage") or (row["stage"] if row else None)
        stage = f"{stage_name}：{phenomenon}" if row else f"未运行（离线：{phenomenon}）"
        values = (key, case["source"], off.get("outcome", "—"), stage, category, repair, tokens,
                  version2.get(key, {}).get("outcome", "待复测"))
        lines.append("| " + " | ".join(safe_cell(v) for v in values) + " |")
    lines.extend(["", "## V1 / V2 量化汇总", "", "| 指标 | V1 | V2 |", "| --- | --- | --- |"])
    labels = ["有效提取完整率（冻结参考）", "核心要求召回率", "P0／优先／加分项口径准确率",
              "事实引用合规率", "单条平均耗时", "单条平均 Token（输入＋输出）"]
    for label, a, b in zip(labels, metrics(manifest, v1) if v1 else ["待运行"] * len(labels),
                           metrics(manifest, v2) if v2 else ["待复测"] * len(labels)):
        lines.append(f"| {label} | {a} | {b} |")
    causes = [note.get("cause") for note in review.values() if note.get("verified") is True and note.get("cause")]
    reviewed = {sample_id for sample_id, note in review.items() if note.get("verified") is True}
    if v1 and v2 and reviewed == ids and all(row["outcome"] != "not_run" for row in v1["rows"] + v2["rows"]):
        non_prompt = ratio(sum(cause != "hallucination" for cause in causes), len(causes))
    else:
        non_prompt = "待双轮与人工抽检齐备"
    lines.extend(["", f"**非 Prompt 根因占比：** {non_prompt}。仅统计人工确认的 V1 主因："
                  "（①＋②＋③）÷（①＋②＋③＋④）；没有分母不计算。", ""])
    lines.extend([
        "## 复现与人工抽检", "",
        "从仓库根目录运行：", "",
        "~~~sh",
        "PY=services/backend/.venv/bin/python",
        "EVAL=services/backend/scripts/eval_real_jds.py",
        "DATA=data/private/real-jd-eval",
        '$PY $EVAL --dry-run --samples "$DATA/samples.json" --run-dir "$DATA/new-offline"',
        '$PY $EVAL --render-report --samples "$DATA/samples.json" \\',
        '  --offline-result "$DATA/offline-final/rescored.json" --v1-result "$DATA/V1/rescored.json" \\',
        '  --review "$DATA/assisted-review.json"',
        "~~~", "",
        "真实模式需同时提供 `--confirm-live-llm`、`--round V1|V2`、私有 `--model-config` 和新的 `--run-dir`。",
        "可用 `--backend-dir` 选择待验收代码；只读复核用 `--rescore`，不会重新发请求。",
        "独立复核者在私有 JSON 按样本 ID 记录 `verified`、`cause`（四象限键或 `null`）、`phenomenon`，",
        "可选填 `stage`、`repair`。V2 保存后用 `--v2-result` 合并；在双轮与人工抽检齐备前不更新 README 质量结论。", "",
    ])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--confirm-live-llm", action="store_true")
    modes.add_argument("--render-report", action="store_true")
    modes.add_argument("--rescore", action="store_true", help="从已有评测库只读重算引文指标，不发送请求")
    parser.add_argument("--samples", required=True, type=Path)
    parser.add_argument("--round", choices=("V1", "V2"))
    parser.add_argument("--backend-dir", default=ROOT / "services/backend", type=Path)
    parser.add_argument("--run-dir", type=Path, help="data/private 中尚不存在的新目录")
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--offline-result", type=Path)
    parser.add_argument("--v1-result", type=Path)
    parser.add_argument("--v2-result", type=Path)
    parser.add_argument("--review", type=Path, help="脱敏抽检 JSON：样本 ID → verified、cause、phenomenon")
    args = parser.parse_args(argv)
    try:
        manifest = validate_manifest(load(private_path(args.samples)))
        if args.render_report:
            if args.model_config or args.run_dir or args.round:
                parser.error("生成报告时不得提供模型配置或运行参数")
            def get(path):
                return load(private_path(path)) if path else None
            output = markdown(manifest, get(args.offline_result), get(args.v1_result), get(args.v2_result), get(args.review))
            REPORT.parent.mkdir(parents=True, exist_ok=True)
            REPORT.write_text(output)
            print(REPORT)
            return 0
        if not args.run_dir:
            parser.error("运行必须指定 --run-dir")
        if args.rescore:
            if args.model_config or args.round:
                parser.error("只读重算不得提供模型配置或新一轮运行参数")
            rescore(manifest, args.backend_dir.resolve(strict=True), private_path(args.run_dir))
            return 0
        if args.confirm_live_llm != bool(args.model_config and args.round) or (
            args.dry_run and (args.model_config or args.round)
        ):
            parser.error("真实模型必须同时指定 --confirm-live-llm、--model-config 和 --round")
        directory = private_path(args.run_dir)
        trace = evaluate(manifest, args.backend_dir.resolve(strict=True), directory,
                         private_path(args.model_config) if args.model_config else None, args.round or "Dry-run")
        if args.dry_run:
            (directory / "report.md").write_text(markdown(manifest, offline=trace))
        return int(bool(trace.get("stop")))
    except (OSError, KeyError, TypeError, ValueError, RuntimeError, StageError) as error:
        print(f"评测未完成：{error}" if isinstance(error, (ValueError, StageError)) else
              f"评测未完成：{type(error).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
