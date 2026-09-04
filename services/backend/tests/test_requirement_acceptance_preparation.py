"""Resumability and evidence tests for real Requirement acceptance preparation."""
from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import (
    get_requirement_acceptance_run_query_repository,
    get_review_requirement_acceptance_canary_use_case,
)
from app.application.job_imports import ImportJobsUseCase
from app.application.job_requirements import (
    RequirementExtractorFailedError,
    RequirementExtractorUnavailableError,
)
from app.application.job_requirements.use_cases import ExtractJobRequirementsUseCase
from app.application.requirement_acceptance import (
    InvalidRequirementAcceptanceCanaryReviewError,
    InvalidRequirementAcceptanceDatasetError,
    PrepareRequirementAcceptanceBatchUseCase,
    RequirementAcceptanceCanaryDecision,
    RequirementAcceptanceCanaryGateError,
    RequirementAcceptanceCanaryReviewAlreadyExistsError,
    RequirementAcceptanceCaseStatus,
    RequirementAcceptanceExecutionLeaseLostError,
    RequirementAcceptanceExecutionLeaseUnavailableError,
    RequirementAcceptanceImportError,
    RequirementAcceptanceRunStatus,
    preflight_requirement_acceptance_dataset,
)
from app.application.requirement_acceptance.execution_lease import (
    requirement_acceptance_execution_lease_key,
)
from app.application.requirement_acceptance.run_use_cases import (
    ReviewRequirementAcceptanceCanaryUseCase,
)
from app.application.requirement_reviews.use_cases import (
    CreateRequirementReviewBatchUseCase,
)
from app.db.base import Base
from app.db.models import (
    JobImportORM,
    JobORM,
    JobRequirementExtractionORM,
    RequirementAcceptanceCanaryReviewORM,
    RequirementAcceptanceExecutionLeaseORM,
    RequirementAcceptanceRunCaseORM,
    RequirementAcceptanceRunORM,
    RequirementReviewBatchORM,
    TraceSpanORM,
)
from app.llm.job_requirement_extractors import FixtureJobRequirementExtractor
from app.main import app
from app.repositories import (
    SqlAlchemyJobImportQueryRepository,
    SqlAlchemyJobQueryRepository,
    SqlAlchemyJobRequirementQueryRepository,
    SqlAlchemyJobRequirementUnitOfWork,
    SqlAlchemyRequirementAcceptanceRunQueryRepository,
    SqlAlchemyRequirementAcceptanceRunUnitOfWork,
    SqlAlchemyRequirementReviewQueryRepository,
    SqlAlchemyRequirementReviewUnitOfWork,
    SqlAlchemyTraceUnitOfWork,
    SqlAlchemyUnitOfWork,
)
import scripts.prepare_requirement_acceptance as acceptance_cli
from scripts.prepare_requirement_acceptance import _provider_guard_error
from app.workflows.job_requirement_extraction import (
    EXTRACTOR_VERSION,
    PROMPT_VERSION,
    SEMANTIC_POLICY_VERSION,
    ExtractJobRequirementsWorkflow,
)


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'acceptance-preparation.db'}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


class UnavailableFixtureJobRequirementExtractor(FixtureJobRequirementExtractor):
    def extract(self, description: str):
        raise RequirementExtractorUnavailableError("simulated unavailable provider")


class GatewayTimeoutOnceFixtureJobRequirementExtractor(FixtureJobRequirementExtractor):
    def __init__(self) -> None:
        self.call_count = 0

    def extract(self, description: str):
        self.call_count += 1
        if self.call_count == 1:
            raise RequirementExtractorUnavailableError(
                "simulated gateway timeout",
                status_code=504,
            )
        return super().extract(description)


class GatewayTimeoutFixtureJobRequirementExtractor(FixtureJobRequirementExtractor):
    def __init__(self) -> None:
        self.call_count = 0

    def extract(self, description: str):
        self.call_count += 1
        raise RequirementExtractorUnavailableError(
            "simulated gateway timeout",
            status_code=504,
        )


class InvalidStructuredJsonOnceFixtureJobRequirementExtractor(FixtureJobRequirementExtractor):
    def __init__(self) -> None:
        self.call_count = 0

    def extract(self, description: str):
        self.call_count += 1
        if self.call_count == 1:
            raise RequirementExtractorFailedError(
                "simulated invalid structured output json",
                failure_stage="structured_output_json",
            )
        return super().extract(description)


class InvalidStructuredJsonFixtureJobRequirementExtractor(FixtureJobRequirementExtractor):
    def __init__(self) -> None:
        self.call_count = 0

    def extract(self, description: str):
        self.call_count += 1
        raise RequirementExtractorFailedError(
            "simulated invalid structured output json",
            failure_stage="structured_output_json",
        )


class FlakyFixtureJobRequirementExtractor(FixtureJobRequirementExtractor):
    def __init__(self, marker: str) -> None:
        self._marker = marker

    def extract(self, description: str):
        if self._marker in description:
            raise RequirementExtractorFailedError("simulated provider failure")
        return super().extract(description)


class CountingFixtureJobRequirementExtractor(FixtureJobRequirementExtractor):
    def __init__(self) -> None:
        self.call_count = 0

    def extract(self, description: str):
        self.call_count += 1
        return super().extract(description)


class TwoProviderCallFixtureJobRequirementExtractor(FixtureJobRequirementExtractor):
    def __init__(self) -> None:
        self.call_count = 0

    @property
    def max_provider_calls_per_execution(self) -> int:
        return 2

    def extract(self, description: str):
        self.call_count += 1
        return replace(super().extract(description), provider_calls=2)


class MultiFlakyFixtureJobRequirementExtractor(FixtureJobRequirementExtractor):
    def __init__(self, markers: tuple[str, ...]) -> None:
        self._markers = markers

    def extract(self, description: str):
        if any(marker in description for marker in self._markers):
            raise RequirementExtractorFailedError("simulated provider failure")
        return super().extract(description)


def _stable_text_hash(value: str) -> str:
    hash_value = 0x811C9DC5
    encoded = value.encode("utf-16-le")
    for offset in range(0, len(encoded), 2):
        code_unit = encoded[offset] | (encoded[offset + 1] << 8)
        hash_value ^= code_unit
        hash_value = (hash_value * 0x01000193) & 0xFFFFFFFF
    return f"fnv1a32:{hash_value:08x}"


def _payload() -> dict:
    domains = [
        "制造设备预测维护与工单协同",
        "银行合规审查与风险材料核验",
        "跨境电商商品运营与广告分析",
        "医院知识问答与临床文档辅助",
        "物流路线异常定位与客户通知",
        "软件研发需求拆解与缺陷归因",
        "连锁门店培训与巡检任务管理",
        "汽车售后诊断与维修知识检索",
        "教育课程规划与学习反馈生成",
        "能源调度报告与安全事件分析",
        "政务政策检索与办事材料校验",
        "保险理赔材料识别与责任核对",
        "游戏内容审核与玩家反馈聚类",
        "法律合同条款抽取与风险提示",
        "工业视觉质检与异常复盘",
        "企业财务报销与发票合规检查",
        "供应链采购询价与交付风险追踪",
        "科研论文检索与实验记录整理",
        "房地产客户线索与项目资料问答",
        "音乐内容生产与版权资料管理",
    ]
    deliverables = [
        "时序数据工具、工单状态机和故障验证集",
        "审计证据链、规则引擎和敏感字段脱敏",
        "商品知识图谱、投放归因和多语言内容流水线",
        "医学术语检索、引用校验和人工复核界面",
        "地图服务接入、异常告警和消息幂等机制",
        "代码仓库检索、Issue 工具和回归评测基线",
        "门店权限过滤、课程版本管理和巡检看板",
        "维修手册切片、车型元数据和诊断工具编排",
        "课程知识库、学习画像和教师确认工作流",
        "实时指标采集、值班升级和事故审计记录",
        "政策版本追踪、材料清单和办理结果校验",
        "OCR 证据定位、责任规则和理赔人工审批",
        "多模态内容分类、申诉队列和安全评测集",
        "合同段落定位、义务主体识别和法务确认",
        "图像模型服务、缺陷样本管理和产线回放",
        "票据解析、审批权限和财务审计日志",
        "供应商工具、交付里程碑和风险评分解释",
        "向量检索、引用格式化和实验数据权限控制",
        "项目文档检索、客户跟进任务和数据隔离",
        "音频元数据、创作工具调用和版权审核流程",
    ]
    jobs = []
    for index, (domain, deliverable) in enumerate(zip(domains, deliverables, strict=True)):
        description = (
            "岗位职责：\n"
            f"1. 负责{domain}的 Agent 方案设计、服务开发与线上评测。\n"
            f"2. 建设{deliverable}，跟踪失败案例并推动业务验收。\n"
            "任职要求：\n"
            "1. 本科及以上学历，具备三年以上后端或 AI 应用工程经验。\n"
            f"2. 熟悉 Python、FastAPI 与结构化输出，能独立交付{domain}相关项目。"
        )
        jobs.append(
            {
                "scope": "武汉",
                "searchCities": ["武汉"],
                "searchKeyword": "AI Agent 工程师",
                "title": f"AI Agent 工程师 {index + 1}",
                "company": f"验收公司 {index + 1}",
                "salaryMinK": 15 + index,
                "salaryMaxK": 30 + index,
                "area": "武汉",
                "skills": ["Python", "FastAPI", "RAG", "Agent"],
                "remoteStatus": "unknown",
                "remoteConfidence": "low",
                "url": f"https://www.zhipin.com/job_detail/acceptance-{index + 1}.html",
                "description": description,
                "descriptionSource": "selector:.job-detail-section .job-sec-text",
                "descriptionSelectorTrust": "trusted",
                "descriptionSanitized": False,
                "descriptionQuality": "full_jd",
                "descriptionLength": len(description.encode("utf-16-le")) // 2,
                "descriptionHash": _stable_text_hash(description),
                "descriptionHasRoleEvidenceSignal": True,
                "descriptionResponsibilitySignalCount": 4,
                "descriptionRequirementSignalCount": 5,
                "descriptionNoiseCount": 0,
                "detailAttempted": True,
                "detailSucceeded": True,
                "requirementReviewEligible": True,
                "requirementReviewIneligibilityReasons": [],
                "sourceVersion": "1.4.6",
            }
        )
    return {
        "version": "1.4.6",
        "generatedAt": "2026-08-04T09:00:00.000Z",
        "purpose": "requirement_manual_quality_review",
        "qualityGate": {
            "requiredSampleSize": 20,
            "eligibleCount": 23,
            "distinctEligibleCount": 20,
            "nearDuplicateCount": 3,
            "selectedCount": 20,
            "status": "ready",
            "blockers": [],
        },
        "selectionPolicy": {
            "descriptionSimilarity": "nfkc_alphanumeric_5gram_jaccard",
            "nearDuplicateThreshold": 0.82,
        },
        "excludedNearDuplicates": [
            {
                "url": f"https://www.zhipin.com/job_detail/excluded-{index}.html",
                "duplicateOfUrl": "https://www.zhipin.com/job_detail/representative.html",
                "similarity": similarity,
            }
            for index, similarity in enumerate((0.91, 0.95, 1.0), start=1)
        ],
        "config": {"selectedCities": [{"name": "武汉", "code": "101200100"}]},
        "statistics": {},
        "jobs": jobs,
        "candidates": [],
    }


def _use_case(
    factory: sessionmaker[Session],
    *,
    extractor: FixtureJobRequirementExtractor | None = None,
    provider: str = "fixture",
    execution_lease_ttl_seconds: int = 30 * 60,
    clock=None,
) -> PrepareRequirementAcceptanceBatchUseCase:
    selected_extractor = extractor or FixtureJobRequirementExtractor()
    jobs = SqlAlchemyJobQueryRepository(factory)
    requirements = SqlAlchemyJobRequirementQueryRepository(factory)
    acceptance_runs = SqlAlchemyRequirementAcceptanceRunQueryRepository(factory)
    reviews = SqlAlchemyRequirementReviewQueryRepository(factory)
    workflow = ExtractJobRequirementsWorkflow(
        selected_extractor,
        lambda: SqlAlchemyTraceUnitOfWork(factory),
    )
    extract = ExtractJobRequirementsUseCase(
        jobs=jobs,
        workflow=workflow,
        uow_factory=lambda: SqlAlchemyJobRequirementUnitOfWork(factory),
        query_repository=requirements,
        provider=provider,
    )
    create_batch = CreateRequirementReviewBatchUseCase(
        reviews,
        lambda: SqlAlchemyRequirementReviewUnitOfWork(factory),
    )
    return PrepareRequirementAcceptanceBatchUseCase(
        import_jobs=ImportJobsUseCase(lambda: SqlAlchemyUnitOfWork(factory)),
        imports=SqlAlchemyJobImportQueryRepository(factory),
        jobs=jobs,
        requirements=requirements,
        extract_requirements=extract,
        acceptance_runs=acceptance_runs,
        acceptance_run_uow_factory=lambda: SqlAlchemyRequirementAcceptanceRunUnitOfWork(
            factory
        ),
        reviews=reviews,
        create_batch=create_batch,
        provider=provider,
        model=selected_extractor.model_name,
        extractor_version=EXTRACTOR_VERSION,
        prompt_version=PROMPT_VERSION,
        semantic_policy_version=SEMANTIC_POLICY_VERSION,
        execution_lease_ttl_seconds=execution_lease_ttl_seconds,
        clock=clock,
    )


def _canary_review_use_case(
    factory: sessionmaker[Session],
) -> ReviewRequirementAcceptanceCanaryUseCase:
    return ReviewRequirementAcceptanceCanaryUseCase(
        SqlAlchemyRequirementAcceptanceRunQueryRepository(factory),
        lambda: SqlAlchemyRequirementAcceptanceRunUnitOfWork(factory),
    )


def _count(factory: sessionmaker[Session], model: type) -> int:
    with factory() as session:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_cli_provider_guard_requires_explicit_fixture_opt_in_and_live_config() -> None:
    assert _provider_guard_error("disabled", allow_fixture=False)
    assert _provider_guard_error("fixture", allow_fixture=False)
    assert _provider_guard_error("fixture", allow_fixture=True) is None
    assert _provider_guard_error("openai", allow_fixture=False)
    assert _provider_guard_error(
        "openai",
        allow_fixture=False,
        model="gpt-test",
        api_key="test-key",
    )
    assert _provider_guard_error(
        "openai",
        allow_fixture=False,
        model="gpt-test",
        api_key="test-key",
        max_new_extractions=3,
    ) is None


def test_execution_lease_allows_one_owner_and_expired_owner_takeover(
    session_factory: sessionmaker[Session],
) -> None:
    identity_key = "a" * 64
    first_token = "reqacceptlease_first"
    second_token = "reqacceptlease_second"
    started_at = datetime(2026, 8, 5, 4, 0, tzinfo=timezone.utc)

    with SqlAlchemyRequirementAcceptanceRunUnitOfWork(session_factory) as uow:
        assert uow.runs.try_acquire_execution_lease(
            identity_key=identity_key,
            lease_token=first_token,
            acquired_at=started_at,
            expires_at=started_at + timedelta(minutes=30),
        ) is True
        uow.commit()

    with SqlAlchemyRequirementAcceptanceRunUnitOfWork(session_factory) as uow:
        assert uow.runs.try_acquire_execution_lease(
            identity_key=identity_key,
            lease_token=second_token,
            acquired_at=started_at + timedelta(minutes=1),
            expires_at=started_at + timedelta(minutes=31),
        ) is False
        uow.commit()

    with SqlAlchemyRequirementAcceptanceRunUnitOfWork(session_factory) as uow:
        renewed_at = started_at + timedelta(minutes=2)
        assert uow.runs.renew_execution_lease(
            identity_key=identity_key,
            lease_token=first_token,
            renewed_at=renewed_at,
            expires_at=renewed_at + timedelta(minutes=30),
        ) is True
        assert uow.runs.renew_execution_lease(
            identity_key=identity_key,
            lease_token=second_token,
            renewed_at=renewed_at,
            expires_at=renewed_at + timedelta(minutes=30),
        ) is False
        uow.commit()

    with session_factory() as session:
        lease = session.get(RequirementAcceptanceExecutionLeaseORM, identity_key)
        assert lease is not None
        assert lease.lease_token == first_token

    takeover_at = started_at + timedelta(minutes=33)
    with SqlAlchemyRequirementAcceptanceRunUnitOfWork(session_factory) as uow:
        assert uow.runs.try_acquire_execution_lease(
            identity_key=identity_key,
            lease_token=second_token,
            acquired_at=takeover_at,
            expires_at=takeover_at + timedelta(minutes=30),
        ) is True
        uow.commit()

    with SqlAlchemyRequirementAcceptanceRunUnitOfWork(session_factory) as uow:
        assert uow.runs.renew_execution_lease(
            identity_key=identity_key,
            lease_token=first_token,
            renewed_at=takeover_at + timedelta(minutes=1),
            expires_at=takeover_at + timedelta(minutes=31),
        ) is False
        assert uow.runs.renew_execution_lease(
            identity_key=identity_key,
            lease_token=second_token,
            renewed_at=takeover_at + timedelta(minutes=1),
            expires_at=takeover_at + timedelta(minutes=31),
        ) is True
        assert uow.runs.release_execution_lease(
            identity_key=identity_key,
            lease_token=first_token,
        ) is False
        assert uow.runs.release_execution_lease(
            identity_key=identity_key,
            lease_token=second_token,
        ) is True
        uow.commit()

    assert _count(session_factory, RequirementAcceptanceExecutionLeaseORM) == 0


def test_execution_lease_blocks_duplicate_provider_attempt_before_import(
    session_factory: sessionmaker[Session],
) -> None:
    payload = _payload()
    extractor = CountingFixtureJobRequirementExtractor()
    use_case = _use_case(session_factory, extractor=extractor, provider="openai")
    title = "execution lease integration"
    reviewer = "will"

    first = use_case.execute(
        payload=payload,
        title=title,
        reviewer=reviewer,
        max_new_extractions=1,
    )
    assert first.created_extractions == 1
    assert extractor.call_count == 1
    assert _count(session_factory, RequirementAcceptanceExecutionLeaseORM) == 0

    preflight = preflight_requirement_acceptance_dataset(payload)
    identity_key = requirement_acceptance_execution_lease_key(
        dataset_fingerprint=preflight.dataset_fingerprint,
        title=title,
        reviewer=reviewer,
        provider="openai",
        model=extractor.model_name,
        extractor_version=EXTRACTOR_VERSION,
        prompt_version=PROMPT_VERSION,
    )
    lease_token = "reqacceptlease_concurrent_owner"
    now = datetime.now(timezone.utc)
    with SqlAlchemyRequirementAcceptanceRunUnitOfWork(session_factory) as uow:
        assert uow.runs.try_acquire_execution_lease(
            identity_key=identity_key,
            lease_token=lease_token,
            acquired_at=now,
            expires_at=now + timedelta(minutes=30),
        ) is True
        uow.commit()

    imports_before = _count(session_factory, JobImportORM)
    traces_before = _count(session_factory, TraceSpanORM)
    with pytest.raises(
        RequirementAcceptanceExecutionLeaseUnavailableError,
        match="already owns",
    ):
        use_case.execute(
            payload=payload,
            title=title,
            reviewer=reviewer,
            max_new_extractions=1,
        )

    assert extractor.call_count == 1
    assert _count(session_factory, JobImportORM) == imports_before
    assert _count(session_factory, TraceSpanORM) == traces_before
    with session_factory() as session:
        run = session.get(RequirementAcceptanceRunORM, first.run_id)
        assert run is not None
        assert sum(case.attempt_count for case in run.cases) == 1
        lease = session.get(RequirementAcceptanceExecutionLeaseORM, identity_key)
        assert lease is not None
        assert lease.lease_token == lease_token

    with SqlAlchemyRequirementAcceptanceRunUnitOfWork(session_factory) as uow:
        assert uow.runs.release_execution_lease(
            identity_key=identity_key,
            lease_token=lease_token,
        ) is True
        uow.commit()


def test_provider_budget_accounts_for_primary_plus_fallback_capacity(
    session_factory: sessionmaker[Session],
) -> None:
    payload = _payload()

    blocked_extractor = TwoProviderCallFixtureJobRequirementExtractor()
    blocked = _use_case(
        session_factory,
        extractor=blocked_extractor,
        provider="openai",
    ).execute(
        payload=payload,
        title="Fallback provider budget blocked",
        reviewer="will",
        max_new_extractions=1,
    )

    assert blocked_extractor.call_count == 0
    assert blocked.created_extractions == 0
    blocked_run = SqlAlchemyRequirementAcceptanceRunQueryRepository(
        session_factory
    ).get_run(blocked.run_id)
    assert blocked_run is not None
    assert blocked_run.attempted_calls == 0

    allowed_extractor = TwoProviderCallFixtureJobRequirementExtractor()
    allowed = _use_case(
        session_factory,
        extractor=allowed_extractor,
        provider="openai",
    ).execute(
        payload=payload,
        title="Fallback provider budget allowed",
        reviewer="will",
        max_new_extractions=2,
    )

    assert allowed_extractor.call_count == 1
    assert allowed.created_extractions == 1
    allowed_run = SqlAlchemyRequirementAcceptanceRunQueryRepository(
        session_factory
    ).get_run(allowed.run_id)
    assert allowed_run is not None
    assert allowed_run.attempted_calls == 2


def test_expired_execution_lease_stops_before_provider_call(
    session_factory: sessionmaker[Session],
) -> None:
    started_at = datetime(2026, 8, 5, 5, 0, tzinfo=timezone.utc)
    times = iter((started_at, started_at + timedelta(seconds=61)))
    extractor = CountingFixtureJobRequirementExtractor()
    use_case = _use_case(
        session_factory,
        extractor=extractor,
        provider="openai",
        execution_lease_ttl_seconds=60,
        clock=lambda: next(times),
    )

    with pytest.raises(
        RequirementAcceptanceExecutionLeaseLostError,
        match="before Provider call",
    ):
        use_case.execute(
            payload=_payload(),
            title="expired lease before provider",
            reviewer="will",
            max_new_extractions=1,
        )

    assert extractor.call_count == 0
    assert _count(session_factory, JobImportORM) == 1
    assert _count(session_factory, TraceSpanORM) == 0
    assert _count(session_factory, JobRequirementExtractionORM) == 0
    assert _count(session_factory, RequirementAcceptanceExecutionLeaseORM) == 0
    with session_factory() as session:
        run = session.scalar(select(RequirementAcceptanceRunORM))
        assert run is not None
        assert sum(case.attempt_count for case in run.cases) == 0


def test_cli_preflight_returns_before_provider_or_repository_construction(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        acceptance_cli,
        "_arguments",
        lambda: SimpleNamespace(
            dataset=Path("formal-review.json"),
            reviewer=None,
            title=None,
            preflight=True,
            max_new_extractions=None,
            allow_fixture=False,
            json=True,
        ),
    )
    monkeypatch.setattr(acceptance_cli, "_load_payload", lambda _path: _payload())

    def unexpected_build():
        raise AssertionError("preflight must not build provider or repositories")

    monkeypatch.setattr(acceptance_cli, "_build_use_case", unexpected_build)

    assert acceptance_cli.main() == 0
    output = capsys.readouterr().out
    assert '"selectedCount": 20' in output
    assert '"dbWrites": 0' in output
    assert '"providerCalls": 0' in output


def test_preflight_is_stable_and_performs_no_writes_or_provider_calls(
    session_factory: sessionmaker[Session],
) -> None:
    payload = _payload()
    first = preflight_requirement_acceptance_dataset(payload)
    reexported = deepcopy(payload)
    reexported["generatedAt"] = "2026-08-04T12:00:00.000Z"
    second = preflight_requirement_acceptance_dataset(reexported)

    assert first.selected_count == 20
    assert first.dataset_fingerprint == second.dataset_fingerprint
    assert first.generated_at != second.generated_at
    assert first.total_description_characters > 0
    assert first.minimum_description_characters > 0
    assert first.maximum_description_characters >= first.minimum_description_characters
    assert _count(session_factory, JobImportORM) == 0
    assert _count(session_factory, JobORM) == 0
    assert _count(session_factory, TraceSpanORM) == 0
    assert _count(session_factory, RequirementAcceptanceRunORM) == 0


def test_selected_near_duplicate_is_rejected_before_any_import(
    session_factory: sessionmaker[Session],
) -> None:
    payload = _payload()
    duplicate_description = payload["jobs"][0]["description"]
    payload["jobs"][1]["description"] = duplicate_description
    payload["jobs"][1]["descriptionLength"] = (
        len(duplicate_description.encode("utf-16-le")) // 2
    )
    payload["jobs"][1]["descriptionHash"] = _stable_text_hash(
        duplicate_description
    )

    with pytest.raises(
        InvalidRequirementAcceptanceDatasetError,
        match="near-duplicate description",
    ):
        _use_case(session_factory).execute(
            payload=payload,
            title="duplicate selected input",
            reviewer="will",
        )

    assert _count(session_factory, JobImportORM) == 0
    assert _count(session_factory, JobORM) == 0


def test_two_selected_sources_cannot_collapse_to_one_internal_job(
    session_factory: sessionmaker[Session],
) -> None:
    payload = _payload()
    payload["jobs"][1]["url"] = payload["jobs"][0]["url"] + "?ka=search_list_2"

    with pytest.raises(RequirementAcceptanceImportError, match="unique persisted Job IDs"):
        _use_case(session_factory).execute(
            payload=payload,
            title="identity collision input",
            reviewer="will",
        )

    assert _count(session_factory, JobImportORM) == 1
    assert _count(session_factory, JobRequirementExtractionORM) == 0
    assert _count(session_factory, TraceSpanORM) == 0
    assert _count(session_factory, RequirementReviewBatchORM) == 0
    assert _count(session_factory, RequirementAcceptanceExecutionLeaseORM) == 0


def test_non_ready_dataset_is_rejected_before_any_import(
    session_factory: sessionmaker[Session],
) -> None:
    payload = _payload()
    payload["qualityGate"]["status"] = "blocked"
    payload["qualityGate"]["blockers"] = ["insufficient_distinct_full_jd_jobs"]

    with pytest.raises(InvalidRequirementAcceptanceDatasetError, match="must be ready"):
        _use_case(session_factory).execute(
            payload=payload,
            title="blocked input",
            reviewer="will",
        )

    assert _count(session_factory, JobImportORM) == 0
    assert _count(session_factory, JobORM) == 0
    assert _count(session_factory, TraceSpanORM) == 0


def test_first_run_creates_twenty_extractions_and_one_practice_batch(
    session_factory: sessionmaker[Session],
) -> None:
    result = _use_case(session_factory).execute(
        payload=_payload(),
        title="Real Requirement acceptance 2026-08-04",
        reviewer="will",
    )

    assert result.ready_for_manual_review is True
    assert result.created_jobs == 20
    assert result.updated_jobs == 0
    assert result.created_extractions == 20
    assert result.reused_extractions == 0
    assert result.failed_extractions == 0
    assert result.batch_id is not None
    assert result.batch_reused is False
    assert all(
        case.status is RequirementAcceptanceCaseStatus.EXTRACTED
        for case in result.cases
    )
    assert all(case.trace_run_id for case in result.cases)
    assert _count(session_factory, JobORM) == 20
    assert _count(session_factory, JobRequirementExtractionORM) == 20
    assert _count(session_factory, TraceSpanORM) == 20
    assert _count(session_factory, RequirementReviewBatchORM) == 1
    assert _count(session_factory, RequirementAcceptanceExecutionLeaseORM) == 0

    detail = SqlAlchemyRequirementReviewQueryRepository(session_factory).get_batch(
        result.batch_id
    )
    assert detail is not None
    assert detail.summary.sample_size == 20
    assert detail.summary.provider == "fixture"
    assert detail.summary.formal_evidence_eligible is False
    assert all(case.is_current for case in detail.cases)


def test_canary_limit_persists_partial_run_and_resume_creates_one_batch(
    session_factory: sessionmaker[Session],
) -> None:
    use_case = _use_case(session_factory)
    payload = _payload()
    first = use_case.execute(
        payload=payload,
        title="Controlled canary acceptance",
        reviewer="will",
        max_new_extractions=3,
    )

    assert first.ready_for_manual_review is False
    assert first.created_extractions == 3
    assert first.reused_extractions == 0
    assert first.failed_extractions == 0
    assert first.deferred_extractions == 17
    assert first.batch_id is None
    assert _count(session_factory, TraceSpanORM) == 3
    assert _count(session_factory, JobRequirementExtractionORM) == 3
    assert _count(session_factory, RequirementAcceptanceRunORM) == 1
    assert _count(session_factory, RequirementAcceptanceRunCaseORM) == 20
    run_repository = SqlAlchemyRequirementAcceptanceRunQueryRepository(session_factory)
    partial = run_repository.get_run(first.run_id)
    assert partial is not None
    assert partial.status is RequirementAcceptanceRunStatus.PARTIAL
    assert partial.extracted_count == 3
    assert partial.deferred_count == 17
    assert partial.attempted_calls == 3
    assert partial.batch_id is None

    resumed_payload = deepcopy(payload)
    resumed_payload["generatedAt"] = "2026-08-04T12:00:00.000Z"
    second = use_case.execute(
        payload=resumed_payload,
        title="Controlled canary acceptance",
        reviewer="will",
        max_new_extractions=17,
    )

    assert second.run_id == first.run_id
    assert second.reused_extractions == 3
    assert second.created_extractions == 17
    assert second.deferred_extractions == 0
    assert second.failed_extractions == 0
    assert second.ready_for_manual_review is True
    assert second.batch_id is not None
    assert _count(session_factory, TraceSpanORM) == 20
    assert _count(session_factory, JobRequirementExtractionORM) == 20
    assert _count(session_factory, RequirementReviewBatchORM) == 1
    ready = run_repository.get_run(first.run_id)
    assert ready is not None
    assert ready.status is RequirementAcceptanceRunStatus.READY
    assert ready.reused_count == 0
    assert ready.extracted_count == 20
    assert ready.deferred_count == 0
    assert ready.attempted_calls == 20
    assert ready.batch_id == second.batch_id
    assert ready.first_import_id != ready.last_import_id
    assert ready.dataset_generated_at == "2026-08-04T12:00:00.000Z"

    repeated = use_case.execute(
        payload=payload,
        title="Controlled canary acceptance",
        reviewer="will",
        max_new_extractions=1,
    )
    assert repeated.run_id == first.run_id
    assert repeated.reused_extractions == 20
    assert repeated.created_extractions == 0
    assert repeated.batch_id == second.batch_id
    assert repeated.batch_reused is True
    assert _count(session_factory, TraceSpanORM) == 20
    assert _count(session_factory, RequirementReviewBatchORM) == 1


def test_openai_fourth_call_requires_immutable_human_canary_approval(
    session_factory: sessionmaker[Session],
) -> None:
    use_case = _use_case(session_factory, provider="openai")
    payload = _payload()
    first = use_case.execute(
        payload=payload,
        title="Live Canary approval gate",
        reviewer="will",
        max_new_extractions=3,
    )

    repository = SqlAlchemyRequirementAcceptanceRunQueryRepository(session_factory)
    awaiting = repository.get_run(first.run_id)
    assert awaiting is not None
    assert awaiting.status is RequirementAcceptanceRunStatus.AWAITING_CANARY_REVIEW
    assert awaiting.canary_review_required is True
    assert awaiting.canary_review is None
    assert awaiting.attempted_calls == 3

    with pytest.raises(RequirementAcceptanceCanaryGateError, match="approval"):
        use_case.execute(
            payload=payload,
            title="Live Canary approval gate",
            reviewer="will",
            max_new_extractions=1,
        )
    assert _count(session_factory, JobImportORM) == 1
    assert _count(session_factory, TraceSpanORM) == 3

    review = _canary_review_use_case(session_factory).execute(
        run_id=first.run_id,
        reviewer="will",
        decision=RequirementAcceptanceCanaryDecision.CONTINUE,
        notes=(
            "I inspected all three Canary JDs, Requirements and Trace outputs; "
            "the evidence grounding is sufficient to continue this controlled run."
        ),
    )
    assert review.decision is RequirementAcceptanceCanaryDecision.CONTINUE
    assert len(review.reviewed_case_ids) == 3
    assert len(review.reviewed_extraction_ids) == 3
    assert len(review.reviewed_trace_run_ids) == 3
    assert _count(session_factory, RequirementAcceptanceCanaryReviewORM) == 1

    resumed = use_case.execute(
        payload=payload,
        title="Live Canary approval gate",
        reviewer="will",
        max_new_extractions=17,
    )
    assert resumed.run_id == first.run_id
    assert resumed.ready_for_manual_review is True
    assert resumed.created_extractions == 17
    assert resumed.reused_extractions == 3
    ready = repository.get_run(first.run_id)
    assert ready is not None
    assert ready.status is RequirementAcceptanceRunStatus.READY
    assert ready.canary_review is not None
    assert ready.canary_review.decision is RequirementAcceptanceCanaryDecision.CONTINUE
    assert ready.attempted_calls == 20
    assert _count(session_factory, TraceSpanORM) == 20
    assert _count(session_factory, RequirementReviewBatchORM) == 1
    assert _count(session_factory, RequirementAcceptanceExecutionLeaseORM) == 0


def test_stop_canary_decision_blocks_future_calls_and_cannot_be_overwritten(
    session_factory: sessionmaker[Session],
) -> None:
    use_case = _use_case(session_factory, provider="openai")
    payload = _payload()
    first = use_case.execute(
        payload=payload,
        title="Stopped live Canary",
        reviewer="will",
        max_new_extractions=1,
    )
    review_use_case = _canary_review_use_case(session_factory)
    review_use_case.execute(
        run_id=first.run_id,
        reviewer="will",
        decision=RequirementAcceptanceCanaryDecision.STOP,
        notes=(
            "The first Canary output contains unacceptable omissions, so this "
            "specific frozen run must stop before any wider provider spend."
        ),
    )

    stopped = SqlAlchemyRequirementAcceptanceRunQueryRepository(
        session_factory
    ).get_run(first.run_id)
    assert stopped is not None
    assert stopped.status is RequirementAcceptanceRunStatus.STOPPED
    assert stopped.canary_review is not None
    assert stopped.canary_review.decision is RequirementAcceptanceCanaryDecision.STOP

    with pytest.raises(RequirementAcceptanceCanaryGateError, match="stopped"):
        use_case.execute(
            payload=payload,
            title="Stopped live Canary",
            reviewer="will",
            max_new_extractions=1,
        )
    assert _count(session_factory, JobImportORM) == 1
    assert _count(session_factory, TraceSpanORM) == 1

    with pytest.raises(RequirementAcceptanceCanaryReviewAlreadyExistsError):
        review_use_case.execute(
            run_id=first.run_id,
            reviewer="will",
            decision=RequirementAcceptanceCanaryDecision.CONTINUE,
            notes="A second decision must never overwrite the immutable stop evidence.",
        )


def test_canary_review_requires_owner_notes_and_live_evidence(
    session_factory: sessionmaker[Session],
) -> None:
    first = _use_case(session_factory, provider="openai").execute(
        payload=_payload(),
        title="Canary validation rules",
        reviewer="will",
        max_new_extractions=1,
    )
    use_case = _canary_review_use_case(session_factory)

    with pytest.raises(InvalidRequirementAcceptanceCanaryReviewError, match="match"):
        use_case.execute(
            run_id=first.run_id,
            reviewer="another-reviewer",
            decision=RequirementAcceptanceCanaryDecision.CONTINUE,
            notes="This otherwise long note cannot be submitted by another reviewer.",
        )
    with pytest.raises(InvalidRequirementAcceptanceCanaryReviewError, match="at least"):
        use_case.execute(
            run_id=first.run_id,
            reviewer="will",
            decision=RequirementAcceptanceCanaryDecision.CONTINUE,
            notes="too short",
        )

    with session_factory() as session:
        case = session.scalar(
            select(RequirementAcceptanceRunCaseORM).where(
                RequirementAcceptanceRunCaseORM.run_id == first.run_id,
                RequirementAcceptanceRunCaseORM.case_index == 0,
            )
        )
        assert case is not None
        case.attempt_count = 4
        session.commit()
    with pytest.raises(InvalidRequirementAcceptanceCanaryReviewError, match="cumulative"):
        use_case.execute(
            run_id=first.run_id,
            reviewer="will",
            decision=RequirementAcceptanceCanaryDecision.CONTINUE,
            notes="Four cumulative calls are outside the frozen Canary review boundary.",
        )


def test_run_progress_is_available_through_read_only_api(
    session_factory: sessionmaker[Session],
) -> None:
    result = _use_case(session_factory, provider="openai").execute(
        payload=_payload(),
        title="API-visible canary",
        reviewer="will",
        max_new_extractions=2,
    )
    repository = SqlAlchemyRequirementAcceptanceRunQueryRepository(session_factory)
    app.dependency_overrides[get_requirement_acceptance_run_query_repository] = (
        lambda: repository
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            page_response = client.get(
                "/api/v1/requirement-acceptance-runs?limit=20&offset=0"
            )
            response = client.get(
                f"/api/v1/requirement-acceptance-runs/{result.run_id}"
            )
            missing = client.get(
                "/api/v1/requirement-acceptance-runs/reqacceptrun_missing"
            )
            openapi = client.get("/openapi.json")
    finally:
        app.dependency_overrides.pop(
            get_requirement_acceptance_run_query_repository,
            None,
        )

    assert page_response.status_code == 200
    page_body = page_response.json()
    assert page_body["total"] == 1
    assert page_body["items"][0]["id"] == result.run_id
    assert page_body["items"][0]["attemptedCalls"] == 2
    assert page_body["items"][0]["completedCaseCount"] == 2
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == result.run_id
    assert body["status"] == "partial"
    assert body["extractedCount"] == 2
    assert body["deferredCount"] == 18
    assert body["attemptedCalls"] == 2
    assert body["completedCaseCount"] == 2
    assert body["canaryReviewRequired"] is False
    assert body["canaryContinueAllowed"] is True
    assert body["canaryStopAllowed"] is True
    assert body["canaryReviewBlockReason"] is None
    assert body["canaryReview"] is None
    assert body["batchId"] is None
    assert len(body["cases"]) == 20
    assert body["cases"][0]["traceRunId"]
    assert body["cases"][0]["isCanaryEvidence"] is True
    assert body["cases"][0]["descriptionSnapshot"]
    assert body["cases"][0]["descriptionIsCurrent"] is True
    assert body["cases"][0]["currentDescriptionHash"] == body["cases"][0]["descriptionHash"]
    assert body["cases"][0]["traceCapability"] == "requirement_extraction"
    assert body["cases"][0]["traceModel"] == "fixture-requirement-extractor"
    assert body["cases"][0]["traceLatencyMs"] >= 0
    assert body["cases"][0]["traceError"] is None
    assert body["cases"][0]["traceCreatedAt"]
    assert body["cases"][2]["status"] == "deferred"
    assert body["cases"][2]["isCanaryEvidence"] is False
    assert body["cases"][2]["descriptionSnapshot"] is None
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "requirement_acceptance_run_not_found"
    paths = openapi.json()["paths"]
    list_path = paths["/api/v1/requirement-acceptance-runs"]
    assert "get" in list_path
    assert "post" not in list_path
    detail_path = paths["/api/v1/requirement-acceptance-runs/{run_id}"]
    assert "get" in detail_path
    assert "post" not in detail_path


def test_run_case_preserves_frozen_jd_when_current_job_changes(
    session_factory: sessionmaker[Session],
) -> None:
    payload = _payload()
    result = _use_case(session_factory, provider="openai").execute(
        payload=payload,
        title="Frozen JD evidence",
        reviewer="will",
        max_new_extractions=1,
    )

    repository = SqlAlchemyRequirementAcceptanceRunQueryRepository(session_factory)
    before = repository.get_run(result.run_id)
    assert before is not None
    original_description = before.cases[0].description_snapshot
    assert original_description
    assert before.cases[0].description_is_current is True

    with session_factory() as session:
        job = session.get(JobORM, before.cases[0].job_id)
        assert job is not None
        job.description = f"{job.description}\n岗位已在 Canary 后更新。"
        session.commit()

    after = repository.get_run(result.run_id)
    assert after is not None
    assert after.cases[0].description_snapshot == original_description
    assert after.cases[0].description_is_current is False
    assert after.cases[0].current_description_hash != after.cases[0].description_hash


def test_canary_review_api_freezes_evidence_and_rejects_duplicate_decision(
    session_factory: sessionmaker[Session],
) -> None:
    result = _use_case(session_factory, provider="openai").execute(
        payload=_payload(),
        title="API Canary decision",
        reviewer="will",
        max_new_extractions=2,
    )
    repository = SqlAlchemyRequirementAcceptanceRunQueryRepository(session_factory)
    review_use_case = _canary_review_use_case(session_factory)
    app.dependency_overrides[get_requirement_acceptance_run_query_repository] = (
        lambda: repository
    )
    app.dependency_overrides[get_review_requirement_acceptance_canary_use_case] = (
        lambda: review_use_case
    )
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            created = client.post(
                f"/api/v1/requirement-acceptance-runs/{result.run_id}/canary-review",
                json={
                    "reviewer": "will",
                    "decision": "continue",
                    "notes": (
                        "I inspected both Canary extraction outputs and their Trace evidence; "
                        "the observed quality is sufficient for controlled continuation."
                    ),
                },
            )
            resumed = _use_case(session_factory, provider="openai").execute(
                payload=_payload(),
                title="API Canary decision",
                reviewer="will",
                max_new_extractions=18,
            )
            assert resumed.ready_for_manual_review is True
            refreshed = client.get(
                f"/api/v1/requirement-acceptance-runs/{result.run_id}"
            )
            duplicate = client.post(
                f"/api/v1/requirement-acceptance-runs/{result.run_id}/canary-review",
                json={
                    "reviewer": "will",
                    "decision": "stop",
                    "notes": "A later request must not overwrite the frozen human decision.",
                },
            )
            openapi = client.get("/openapi.json")
    finally:
        app.dependency_overrides.pop(
            get_requirement_acceptance_run_query_repository,
            None,
        )
        app.dependency_overrides.pop(
            get_review_requirement_acceptance_canary_use_case,
            None,
        )

    assert created.status_code == 201
    created_body = created.json()
    assert created_body["decision"] == "continue"
    assert len(created_body["reviewedCaseIds"]) == 2
    assert len(created_body["reviewedExtractionIds"]) == 2
    assert len(created_body["reviewedTraceRunIds"]) == 2
    assert refreshed.status_code == 200
    refreshed_body = refreshed.json()
    assert refreshed_body["canaryReview"]["id"] == created_body["id"]
    assert sum(case["isCanaryEvidence"] for case in refreshed_body["cases"]) == 2
    assert refreshed_body["cases"][2]["attemptCount"] == 1
    assert refreshed_body["cases"][2]["isCanaryEvidence"] is False
    assert refreshed_body["cases"][2]["descriptionSnapshot"] is None
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == (
        "requirement_acceptance_canary_review_already_exists"
    )
    review_path = openapi.json()["paths"][
        "/api/v1/requirement-acceptance-runs/{run_id}/canary-review"
    ]
    assert "post" in review_path
    assert "get" not in review_path


def test_application_rejects_unbounded_openai_execution_before_import(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(
        InvalidRequirementAcceptanceDatasetError,
        match="explicit maxNewExtractions",
    ):
        _use_case(session_factory, provider="openai").execute(
            payload=_payload(),
            title="Unbounded OpenAI run",
            reviewer="will",
        )
    assert _count(session_factory, JobImportORM) == 0
    assert _count(session_factory, TraceSpanORM) == 0
    assert _count(session_factory, RequirementAcceptanceRunORM) == 0


def test_invalid_canary_limit_is_rejected_before_import(
    session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(InvalidRequirementAcceptanceDatasetError, match="between 1 and 20"):
        _use_case(session_factory).execute(
            payload=_payload(),
            title="Invalid canary",
            reviewer="will",
            max_new_extractions=0,
        )
    assert _count(session_factory, JobImportORM) == 0
    assert _count(session_factory, RequirementAcceptanceRunORM) == 0


def test_second_identical_run_reuses_extractions_and_exact_batch(
    session_factory: sessionmaker[Session],
) -> None:
    use_case = _use_case(session_factory)
    first = use_case.execute(
        payload=_payload(),
        title="Idempotent acceptance batch",
        reviewer="will",
    )
    second = use_case.execute(
        payload=_payload(),
        title="Idempotent acceptance batch",
        reviewer="will",
    )

    assert second.created_jobs == 0
    assert second.updated_jobs == 20
    assert second.created_extractions == 0
    assert second.reused_extractions == 20
    assert second.failed_extractions == 0
    assert second.batch_id == first.batch_id
    assert second.batch_reused is True
    assert _count(session_factory, JobImportORM) == 2
    assert _count(session_factory, JobRequirementExtractionORM) == 20
    assert _count(session_factory, TraceSpanORM) == 20
    assert _count(session_factory, RequirementReviewBatchORM) == 1


def test_new_semantic_policy_does_not_reuse_older_semantic_extractions(
    session_factory: sessionmaker[Session],
) -> None:
    first_extractor = CountingFixtureJobRequirementExtractor()
    first = _use_case(session_factory, extractor=first_extractor).execute(
        payload=_payload(),
        title="v42.95 semantic baseline",
        reviewer="will",
    )
    assert first.created_extractions == 20
    assert first_extractor.call_count == 20

    with session_factory() as session:
        traces = session.scalars(select(TraceSpanORM)).all()
        assert len(traces) == 20
        for trace in traces:
            output = dict(trace.output or {})
            output["semanticPolicyVersion"] = "requirement-semantics-v42.95"
            trace.output = output
        session.commit()

    second_extractor = CountingFixtureJobRequirementExtractor()
    second = _use_case(session_factory, extractor=second_extractor).execute(
        payload=_payload(),
        title="v42.96 semantic revalidation",
        reviewer="will",
    )

    assert second.created_extractions == 20
    assert second.reused_extractions == 0
    assert second_extractor.call_count == 20
    assert _count(session_factory, JobRequirementExtractionORM) == 40
    assert _count(session_factory, RequirementReviewBatchORM) == 2


def test_existing_run_cannot_cross_semantic_policy_boundary(
    session_factory: sessionmaker[Session],
) -> None:
    first = _use_case(session_factory).execute(
        payload=_payload(),
        title="semantic-bound-run",
        reviewer="will",
    )
    assert first.created_extractions == 20

    with session_factory() as session:
        traces = session.scalars(select(TraceSpanORM)).all()
        assert len(traces) == 20
        for trace in traces:
            output = dict(trace.output or {})
            output["semanticPolicyVersion"] = "requirement-semantics-v42.95"
            trace.output = output
        session.commit()

    with pytest.raises(InvalidRequirementAcceptanceDatasetError, match="semantic policy"):
        _use_case(session_factory).execute(
            payload=_payload(),
            title="semantic-bound-run",
            reviewer="will",
        )

    assert _count(session_factory, JobImportORM) == 1
    assert _count(session_factory, JobRequirementExtractionORM) == 20
    assert _count(session_factory, RequirementAcceptanceRunORM) == 1
    assert _count(session_factory, RequirementReviewBatchORM) == 1


def test_provider_unavailable_fails_fast_after_one_traced_attempt(
    session_factory: sessionmaker[Session],
) -> None:
    result = _use_case(
        session_factory,
        extractor=UnavailableFixtureJobRequirementExtractor(),
    ).execute(
        payload=_payload(),
        title="Unavailable provider batch",
        reviewer="will",
    )

    assert result.ready_for_manual_review is False
    assert result.created_extractions == 0
    assert result.reused_extractions == 0
    assert result.failed_extractions == 1
    assert result.deferred_extractions == 19
    assert result.cases[0].error_code == "RequirementExtractorUnavailableError"
    assert all(
        case.status is RequirementAcceptanceCaseStatus.DEFERRED
        and case.error_code == "provider_unavailable_not_attempted"
        for case in result.cases[1:]
    )
    assert _count(session_factory, TraceSpanORM) == 1
    assert _count(session_factory, JobRequirementExtractionORM) == 0
    assert _count(session_factory, RequirementReviewBatchORM) == 0
    assert _count(session_factory, RequirementAcceptanceRunORM) == 1
    assert _count(session_factory, RequirementAcceptanceRunCaseORM) == 20


def test_gateway_timeout_retries_same_case_once_within_explicit_budget(
    session_factory: sessionmaker[Session],
) -> None:
    extractor = GatewayTimeoutOnceFixtureJobRequirementExtractor()
    result = _use_case(session_factory, extractor=extractor).execute(
        payload=_payload(),
        title="Gateway timeout recovery batch",
        reviewer="will",
        max_new_extractions=2,
    )

    assert extractor.call_count == 2
    assert result.created_extractions == 1
    assert result.failed_extractions == 0
    assert result.deferred_extractions == 19
    assert result.cases[0].status is RequirementAcceptanceCaseStatus.EXTRACTED
    assert result.cases[0].extraction_id is not None
    assert all(
        case.status is RequirementAcceptanceCaseStatus.DEFERRED
        and case.error_code == "new_extraction_limit_reached"
        for case in result.cases[1:]
    )
    run = SqlAlchemyRequirementAcceptanceRunQueryRepository(session_factory).get_run(
        result.run_id
    )
    assert run is not None
    assert run.cases[0].attempt_count == 2
    assert _count(session_factory, TraceSpanORM) == 2


def test_invalid_structured_json_retries_same_case_once_within_explicit_budget(
    session_factory: sessionmaker[Session],
) -> None:
    extractor = InvalidStructuredJsonOnceFixtureJobRequirementExtractor()
    result = _use_case(session_factory, extractor=extractor).execute(
        payload=_payload(),
        title="Invalid structured JSON recovery batch",
        reviewer="will",
        max_new_extractions=2,
    )

    assert extractor.call_count == 2
    assert result.created_extractions == 1
    assert result.failed_extractions == 0
    assert result.deferred_extractions == 19
    assert result.cases[0].status is RequirementAcceptanceCaseStatus.EXTRACTED
    run = SqlAlchemyRequirementAcceptanceRunQueryRepository(session_factory).get_run(
        result.run_id
    )
    assert run is not None
    assert run.cases[0].attempt_count == 2
    assert _count(session_factory, TraceSpanORM) == 2


def test_repeated_invalid_structured_json_retries_only_once_then_fails(
    session_factory: sessionmaker[Session],
) -> None:
    extractor = InvalidStructuredJsonFixtureJobRequirementExtractor()
    result = _use_case(session_factory, extractor=extractor).execute(
        payload=_payload(),
        title="Repeated invalid structured JSON batch",
        reviewer="will",
        max_new_extractions=2,
    )

    assert extractor.call_count == 2
    assert result.created_extractions == 0
    assert result.failed_extractions == 1
    assert result.deferred_extractions == 19
    assert result.cases[0].error_code == "RequirementExtractorFailedError"
    run = SqlAlchemyRequirementAcceptanceRunQueryRepository(session_factory).get_run(
        result.run_id
    )
    assert run is not None
    assert run.cases[0].attempt_count == 2
    assert _count(session_factory, TraceSpanORM) == 2


def test_repeated_gateway_timeout_retries_only_once_then_fails_fast(
    session_factory: sessionmaker[Session],
) -> None:
    extractor = GatewayTimeoutFixtureJobRequirementExtractor()
    result = _use_case(session_factory, extractor=extractor).execute(
        payload=_payload(),
        title="Repeated gateway timeout batch",
        reviewer="will",
        max_new_extractions=3,
    )

    assert extractor.call_count == 2
    assert result.created_extractions == 0
    assert result.failed_extractions == 1
    assert result.deferred_extractions == 19
    assert result.cases[0].error_code == "RequirementExtractorUnavailableError"
    assert all(
        case.status is RequirementAcceptanceCaseStatus.DEFERRED
        and case.error_code == "provider_unavailable_not_attempted"
        for case in result.cases[1:]
    )
    run = SqlAlchemyRequirementAcceptanceRunQueryRepository(session_factory).get_run(
        result.run_id
    )
    assert run is not None
    assert run.cases[0].attempt_count == 2
    assert _count(session_factory, TraceSpanORM) == 2


def test_gateway_timeout_never_retries_past_explicit_single_call_budget(
    session_factory: sessionmaker[Session],
) -> None:
    extractor = GatewayTimeoutFixtureJobRequirementExtractor()
    result = _use_case(session_factory, extractor=extractor).execute(
        payload=_payload(),
        title="Single-call gateway timeout batch",
        reviewer="will",
        max_new_extractions=1,
    )

    assert extractor.call_count == 1
    assert result.created_extractions == 0
    assert result.failed_extractions == 1
    assert result.deferred_extractions == 19
    run = SqlAlchemyRequirementAcceptanceRunQueryRepository(session_factory).get_run(
        result.run_id
    )
    assert run is not None
    assert run.cases[0].attempt_count == 1
    assert _count(session_factory, TraceSpanORM) == 1


def test_deferred_invocation_does_not_erase_a_prior_failure_trace(
    session_factory: sessionmaker[Session],
) -> None:
    payload = _payload()
    markers = (
        "物流路线异常定位与客户通知",
        "保险理赔材料识别与责任核对",
    )
    first = _use_case(
        session_factory,
        extractor=MultiFlakyFixtureJobRequirementExtractor(markers),
    ).execute(
        payload=payload,
        title="Preserve failed evidence",
        reviewer="will",
    )
    assert first.failed_extractions == 2
    first_run = SqlAlchemyRequirementAcceptanceRunQueryRepository(
        session_factory
    ).get_run(first.run_id)
    assert first_run is not None
    later_failed = first_run.cases[11]
    assert later_failed.status.value == "failed"
    assert later_failed.attempt_count == 1
    assert later_failed.trace_run_id is not None
    original_trace_id = later_failed.trace_run_id
    original_error = later_failed.error_message

    second = _use_case(
        session_factory,
        extractor=MultiFlakyFixtureJobRequirementExtractor(markers),
    ).execute(
        payload=payload,
        title="Preserve failed evidence",
        reviewer="will",
        max_new_extractions=1,
    )
    assert second.failed_extractions == 1
    assert second.deferred_extractions == 1
    persisted = SqlAlchemyRequirementAcceptanceRunQueryRepository(
        session_factory
    ).get_run(first.run_id)
    assert persisted is not None
    assert persisted.failed_count == 2
    assert persisted.deferred_count == 0
    still_failed = persisted.cases[11]
    assert still_failed.status.value == "failed"
    assert still_failed.attempt_count == 1
    assert still_failed.trace_run_id == original_trace_id
    assert still_failed.error_message == original_error


def test_partial_failure_keeps_progress_and_rerun_resumes_without_duplicate_calls(
    session_factory: sessionmaker[Session],
) -> None:
    payload = _payload()
    marker = "保险理赔材料识别与责任核对"
    failed = _use_case(
        session_factory,
        extractor=FlakyFixtureJobRequirementExtractor(marker),
    ).execute(
        payload=payload,
        title="Resumable acceptance batch",
        reviewer="will",
    )

    assert failed.ready_for_manual_review is False
    assert failed.created_extractions == 19
    assert failed.reused_extractions == 0
    assert failed.failed_extractions == 1
    assert failed.batch_id is None
    failed_case = failed.cases[11]
    assert failed_case.status is RequirementAcceptanceCaseStatus.FAILED
    assert failed_case.trace_run_id is not None
    assert _count(session_factory, JobRequirementExtractionORM) == 19
    assert _count(session_factory, TraceSpanORM) == 20
    assert _count(session_factory, RequirementReviewBatchORM) == 0

    resumed = _use_case(session_factory).execute(
        payload=payload,
        title="Resumable acceptance batch",
        reviewer="will",
    )

    assert resumed.ready_for_manual_review is True
    assert resumed.reused_extractions == 19
    assert resumed.created_extractions == 1
    assert resumed.failed_extractions == 0
    assert resumed.batch_id is not None
    assert _count(session_factory, JobRequirementExtractionORM) == 20
    assert _count(session_factory, TraceSpanORM) == 21
    assert _count(session_factory, RequirementReviewBatchORM) == 1

    repeated = _use_case(session_factory).execute(
        payload=payload,
        title="Resumable acceptance batch",
        reviewer="will",
    )
    assert repeated.reused_extractions == 20
    assert repeated.created_extractions == 0
    assert repeated.batch_id == resumed.batch_id
    assert repeated.batch_reused is True
    assert _count(session_factory, TraceSpanORM) == 21
    assert _count(session_factory, RequirementReviewBatchORM) == 1


def test_changed_jd_creates_one_new_extraction_and_makes_old_batch_stale(
    session_factory: sessionmaker[Session],
) -> None:
    use_case = _use_case(session_factory)
    first = use_case.execute(
        payload=_payload(),
        title="Acceptance batch before JD update",
        reviewer="will",
    )
    changed_payload = deepcopy(_payload())
    changed_payload["generatedAt"] = "2026-08-04T10:00:00.000Z"
    changed_payload["jobs"][0]["description"] += "\n3. 需要具备生产级 Agent 可观测性经验。"
    changed_description = changed_payload["jobs"][0]["description"]
    changed_payload["jobs"][0]["descriptionLength"] = (
        len(changed_description.encode("utf-16-le")) // 2
    )
    changed_payload["jobs"][0]["descriptionHash"] = _stable_text_hash(
        changed_description
    )
    second = use_case.execute(
        payload=changed_payload,
        title="Acceptance batch after JD update",
        reviewer="will",
    )

    assert second.reused_extractions == 19
    assert second.created_extractions == 1
    assert second.batch_id is not None
    assert second.batch_id != first.batch_id
    assert _count(session_factory, JobRequirementExtractionORM) == 21
    assert _count(session_factory, TraceSpanORM) == 21
    assert _count(session_factory, RequirementReviewBatchORM) == 2

    reviews = SqlAlchemyRequirementReviewQueryRepository(session_factory)
    old_batch = reviews.get_batch(first.batch_id or "")
    new_batch = reviews.get_batch(second.batch_id)
    assert old_batch is not None
    assert new_batch is not None
    assert old_batch.summary.stale_case_count == 1
    assert new_batch.summary.stale_case_count == 0
