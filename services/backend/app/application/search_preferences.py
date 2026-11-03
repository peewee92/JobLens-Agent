"""Conservative preference checks against structured job facts, without a model."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
import hashlib
import json
import math
import re

from app.application.career_context.models import SearchIntentDetail
from app.application.job_queries.models import JobDetail, JobListItem
from app.domain.jobs import RemoteStatus


class PreferenceFitStatus(StrEnum):
    MATCHED = "matched"
    CONDITIONAL = "conditional"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class PreferenceCheck:
    key: str
    status: PreferenceFitStatus
    code: str
    reason: str
    intent_fields: tuple[str, ...]
    job_fields: tuple[str, ...]


def preference_input_fingerprint(intent: SearchIntentDetail, job: JobDetail | JobListItem) -> str:
    # Only fields used by these rules; no raw JD or career evidence.
    payload = {"intent": asdict(intent), "job": {
        "id": job.id, "title": job.title, "company": job.company, "area": job.area,
        "salaryMinK": job.salary_min_k, "salaryMaxK": job.salary_max_k,
        "remoteStatus": job.remote_status.value,
    }}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     default=str).encode()).hexdigest()


def _city(area: str | None) -> str | None:
    if not area:
        return None
    # A slash/comma may denote multiple cities, not a city/district boundary.
    if any(separator in area for separator in ("/", ",", "，", "或", "省")):
        return None
    first = re.split(r"[·•\s]", area.strip())[0]
    if any(word in first for word in ("全国", "不限", "海外", "中国", "多地", "待定", "省", "区", "县")):
        # A city followed by 市 is still usable in e.g. 北京市朝阳区.
        match = re.match(r"^([\u4e00-\u9fff]{2,5})市", first)
        return match.group(1) if match else None
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,6}", first):
        return None
    return first.removesuffix("市")


def _contains_keyword(text: str, keyword: str) -> bool:
    if not keyword.strip():
        return False
    if keyword.isascii():
        return re.search(r"(?<![\w])" + re.escape(keyword) + r"(?![\w])", text, re.I) is not None
    return keyword.casefold() in text.casefold()


def evaluate_search_preferences(intent: SearchIntentDetail, job: JobDetail | JobListItem) -> tuple[PreferenceCheck, ...]:
    checks: list[PreferenceCheck] = []
    def add(key: str, status: PreferenceFitStatus, code: str, reason: str,
            intent_fields: tuple[str, ...], job_fields: tuple[str, ...] = ()) -> None:
        checks.append(PreferenceCheck(key, status, code, reason, tuple(intent_fields), tuple(job_fields)))
    supported = PreferenceFitStatus.MATCHED
    unknown = PreferenceFitStatus.CONDITIONAL
    conflict = PreferenceFitStatus.MISSING

    if intent.cities:
        city = _city(job.area)
        targets = {
            _city(value) if re.fullmatch(r"[\u4e00-\u9fff]{2,6}", value.strip())
            and not any(mark in value for mark in ("区", "县", "省")) else None
            for value in intent.cities
        }
        if city is not None and city in targets:
            add("cities", supported, "city_supported", f"岗位城市 {city} 位于已确认目标城市中。", ("cities",), ("area",))
        elif intent.remote_accepted is True and job.remote_status is RemoteStatus.CONFIRMED:
            add("cities", supported, "remote_alternative_supported", "你接受远程，岗位已标明远程；无需同时满足目标城市。", ("cities", "remoteAccepted"), ("area", "remoteStatus"))
        elif city is None or None in targets or (intent.remote_accepted is True and job.remote_status is RemoteStatus.UNKNOWN):
            add("cities", unknown, "location_unverified", "城市或异地远程安排尚不能可靠核实，请确认地点与远程安排。", ("cities", "remoteAccepted"), ("area", "remoteStatus"))
        else:
            add("cities", conflict, "city_conflict", f"岗位城市 {city} 不在目标城市中，且没有可用的远程替代条件。", ("cities", "remoteAccepted"), ("area", "remoteStatus"))

    if intent.remote_accepted is False:
        if job.remote_status is RemoteStatus.CONFIRMED:
            add("remote", conflict, "remote_conflict", "你明确不接受远程岗位，但该岗位标明远程。", ("remoteAccepted",), ("remoteStatus",))
        elif job.remote_status is RemoteStatus.UNKNOWN:
            add("remote", unknown, "remote_unverified", "你不接受远程岗位，岗位远程信息尚未明确，请核实工作安排。", ("remoteAccepted",), ("remoteStatus",))
        else:
            add("remote", supported, "onsite_supported", "岗位明确不远程，符合不接受远程的设置。", ("remoteAccepted",), ("remoteStatus",))
    elif intent.remote_accepted is True:
        add("remote", supported, "remote_optional", "接受远程不是只接受远程；线下岗位仍可进入判断。", ("remoteAccepted",), ())

    if intent.minimum_salary_k is not None:
        low, high, minimum = job.salary_min_k, job.salary_max_k, intent.minimum_salary_k
        valid = all(math.isfinite(value) and value >= 0
                    for value in (low, high, minimum) if value is not None)
        if not valid or (low is not None and high is not None and low > high):
            status, code, reason = unknown, "salary_unverified", "岗位薪资缺失或区间异常，不能判定是否达到最低月薪。"
        elif high is not None and high < minimum:
            status, code, reason = conflict, "salary_conflict", f"岗位月薪上限 {high:g}K 低于已确认底线 {minimum:g}K。"
        elif low is not None and low >= minimum:
            status, code, reason = supported, "salary_supported", f"岗位月薪下限 {low:g}K 达到已确认底线 {minimum:g}K。"
        elif low is None or high is None:
            status, code, reason = unknown, "salary_unverified", "薪资边界不足以确认是否达到最低月薪，请核实实际报价。"
        else:
            status, code, reason = unknown, "salary_negotiation_required", f"岗位月薪 {low:g}–{high:g}K 跨越底线 {minimum:g}K，需确认实际报价。"
        add("salary", status, code, reason, ("minimumSalaryK",), ("salaryMinK", "salaryMaxK"))

    if intent.exclude_keywords:
        found = [word for word in intent.exclude_keywords if _contains_keyword(job.title + " " + job.company, word)]
        add("excludeKeywords", conflict if found else supported,
            "excluded_keyword_found" if found else "excluded_keywords_not_found",
            "岗位名称或公司命中排除词：" + "、".join(found) if found else "岗位名称与公司未命中排除词；此检查不扫描原始岗位正文。",
            ("excludeKeywords",), ("title", "company"))
    if intent.target_roles:
        direct = any(_contains_keyword(job.title, role) for role in intent.target_roles)
        add("targetRoles", supported if direct else unknown, "role_title_supported" if direct else "role_unverified",
            "岗位名称直接包含目标角色。" if direct else "岗位名称未直接对应目标角色，不能仅凭名称断言不适合，请确认角色范围。", ("targetRoles",), ("title",))
    for key, value, label in (("seniority", intent.seniority, "目标级别"), ("employmentTypes", intent.employment_types, "工作形式")):
        if value:
            add(key, unknown, "structured_job_fact_missing", f"已设置{label}，但岗位没有可比较的结构化字段，请人工确认。", (key,), ())
    for index, text in enumerate(intent.hard_constraints):
        add(f"hardConstraints:{index}", unknown, "hard_constraint_requires_confirmation",
            f"待确认限制：{text}。本轮不自动解释自由文本，也不会视作已经满足。", (f"hardConstraints[{index}]",), ())
    return tuple(checks)
