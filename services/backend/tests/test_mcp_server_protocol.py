from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest

try:
    import mcp  # noqa: F401
except ImportError as exc:  # pragma: no cover - only when SDK installation is incomplete
    pytest.skip(f"MCP SDK is unavailable: {exc}", allow_module_level=True)

from app.agent.context import CareerAgentContext
from app.mcp.adapter import JobLensMcpAdapter
from app.mcp.schemas import McpToolEnvelope
from app.mcp.server import create_mcp_server
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters
from scripts.seed_mcp_demo import seed


BACKEND_ROOT = Path(__file__).resolve().parents[1]


class _ContextBuilder:
    def build(self, **_kwargs):
        return CareerAgentContext(
            usable=False,
            confirmation_boundary="blocked",
            profile=None,
            search_intent=None,
            current_job=None,
            relevant_evidence=(),
            blockers=(),
            blocker_messages=("Synthetic protocol test context is unavailable.",),
        )


class _Registry:
    def invoke(self, **_kwargs):  # pragma: no cover - context must stop this path
        raise AssertionError("registry must not run for unavailable context")


class _SuccessfulAdapter:
    """Small transport-double: SDK tests do not duplicate workflow tests."""

    def rank_match_reports(self, _request):
        return McpToolEnvelope.success(
            tool="rank_match_reports",
            trace_id="mcp_protocol_test",
            data={"kind": "ranking"},
        )

    def target_cohort_gaps(self, _request):
        return McpToolEnvelope.success(
            tool="target_cohort_gaps",
            trace_id="mcp_protocol_test",
            data={"kind": "gaps"},
        )

    def job_preparation(self, _request):
        return McpToolEnvelope.success(
            tool="job_preparation",
            trace_id="mcp_protocol_test",
            data={"kind": "preparation"},
        )


def test_sdk_discovery_exposes_only_three_flat_read_only_tools() -> None:
    adapter = JobLensMcpAdapter(
        context_builder=_ContextBuilder(),
        tool_registry=_Registry(),
        trace_id_factory=lambda: "mcp_protocol_test",
    )
    server = create_mcp_server(adapter)

    tools = asyncio.run(server.list_tools())
    by_name = {tool.name: tool for tool in tools}

    assert set(by_name) == {
        "rank_match_reports",
        "target_cohort_gaps",
        "job_preparation",
    }
    assert "job_ids" in by_name["rank_match_reports"].input_schema["properties"]
    assert "selected_job_ids" in by_name["target_cohort_gaps"].input_schema["properties"]
    assert "cohort_id" not in by_name["target_cohort_gaps"].input_schema["properties"]
    assert by_name["job_preparation"].annotations.read_only_hint is True
    assert by_name["job_preparation"].meta["joblens"]["requiresCurrentJob"] is True


def test_in_memory_sdk_client_discovers_and_calls_all_three_tools() -> None:
    async def exercise_protocol() -> dict[str, dict]:
        async with Client(create_mcp_server(_SuccessfulAdapter())) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {
                "rank_match_reports",
                "target_cohort_gaps",
                "job_preparation",
            }
            ranking = await client.call_tool(
                "rank_match_reports", {"job_ids": ["job_1"], "top_n": 1}
            )
            gaps = await client.call_tool(
                "target_cohort_gaps", {"selected_job_ids": ["job_1"]}
            )
            preparation = await client.call_tool("job_preparation", {"job_id": "job_1"})
            return {
                "ranking": ranking.structured_content,
                "gaps": gaps.structured_content,
                "preparation": preparation.structured_content,
            }

    results = asyncio.run(exercise_protocol())

    assert results == {
        "ranking": {
            "ok": True,
            "data": {"kind": "ranking"},
            "error": None,
            "meta": {
                "tool": "rank_match_reports",
                "schemaVersion": "1",
                "traceId": "mcp_protocol_test",
                "providerCalls": 0,
                "businessWrites": 0,
            },
        },
        "gaps": {
            "ok": True,
            "data": {"kind": "gaps"},
            "error": None,
            "meta": {
                "tool": "target_cohort_gaps",
                "schemaVersion": "1",
                "traceId": "mcp_protocol_test",
                "providerCalls": 0,
                "businessWrites": 0,
            },
        },
        "preparation": {
            "ok": True,
            "data": {"kind": "preparation"},
            "error": None,
            "meta": {
                "tool": "job_preparation",
                "schemaVersion": "1",
                "traceId": "mcp_protocol_test",
                "providerCalls": 0,
                "businessWrites": 0,
            },
        },
    }


def test_sdk_client_receives_sanitized_error_when_context_storage_fails() -> None:
    class FailingContextBuilder:
        def build(self, **_kwargs):
            raise OSError("local database connection failed")

    adapter = JobLensMcpAdapter(
        context_builder=FailingContextBuilder(),
        tool_registry=_Registry(),
        trace_id_factory=lambda: "mcp_protocol_failure",
    )

    async def call() -> dict:
        async with Client(create_mcp_server(adapter)) as client:
            result = await client.call_tool("job_preparation", {"job_id": "job_1"})
            return result.structured_content

    result = asyncio.run(call())
    assert result["ok"] is False
    assert result["data"] is None
    assert result["error"] == {
        "code": "backend_unavailable",
        "message": "JobLens local storage is temporarily unavailable.",
        "retryable": True,
    }
    assert result["meta"]["providerCalls"] == 0
    assert result["meta"]["businessWrites"] == 0


def test_sdk_client_context_rejection_uses_public_error_message() -> None:
    class UnavailableContextBuilder(_ContextBuilder):
        def build(self, **kwargs):
            return replace(
                super().build(**kwargs), blocker_messages=("internal_marker_123",)
            )

    adapter = JobLensMcpAdapter(
        context_builder=UnavailableContextBuilder(),
        tool_registry=_Registry(),
        trace_id_factory=lambda: "mcp_protocol_rejection",
    )

    async def call() -> dict:
        async with Client(create_mcp_server(adapter)) as client:
            result = await client.call_tool("rank_match_reports", {"job_ids": ["job_1"]})
            return result.structured_content

    result = asyncio.run(call())
    assert result["ok"] is False
    assert result["error"]["code"] == "business_invariant"
    assert result["error"]["message"] == "JobLens context cannot be used for this request."
    assert "internal_marker_123" not in str(result)
    assert result["meta"]["providerCalls"] == 0
    assert result["meta"]["businessWrites"] == 0


def test_stdio_sdk_client_calls_all_tools_and_reconnects_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "mcp-demo.db"
    seed(database)
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "scripts.run_mcp_server"],
        cwd=BACKEND_ROOT,
        env={**os.environ, "DATABASE_URL": f"sqlite:///{database}"},
    )

    async def call_all_tools() -> dict[str, dict]:
        async with Client(server) as client:
            discovered = await client.list_tools()
            assert {tool.name for tool in discovered.tools} == {
                "rank_match_reports",
                "target_cohort_gaps",
                "job_preparation",
            }
            ranking = await client.call_tool(
                "rank_match_reports",
                {"job_ids": ["job_mcp_demo_01", "job_mcp_demo_02"], "top_n": 2},
            )
            gaps = await client.call_tool(
                "target_cohort_gaps",
                {"selected_job_ids": ["job_mcp_demo_01", "job_mcp_demo_02"]},
            )
            preparation = await client.call_tool(
                "job_preparation", {"job_id": "job_mcp_demo_01"}
            )
            return {
                "ranking": ranking.structured_content,
                "gaps": gaps.structured_content,
                "preparation": preparation.structured_content,
            }

    first = asyncio.run(call_all_tools())
    second = asyncio.run(call_all_tools())

    for result in (*first.values(), *second.values()):
        assert result["ok"] is True
        assert result["error"] is None
        assert result["meta"]["providerCalls"] == 0
        assert result["meta"]["businessWrites"] == 0
    assert first["ranking"]["data"]["count"] == 2
    assert first["gaps"]["data"]["jobIds"] == ["job_mcp_demo_01", "job_mcp_demo_02"]
    assert "cohortId" not in first["gaps"]["data"]
    assert first["preparation"]["data"]["jobId"] == "job_mcp_demo_01"
    assert first["ranking"]["data"]["items"][0]["summary"].startswith("Synthetic demo:")
    assert first["preparation"]["data"]["interviewFacts"]["items"][0]["requirementText"]
    assert first["preparation"]["data"]["storyFacts"]["items"][0]["evidenceSummary"]

    # Public MCP consumers need the selected Job IDs and grounded explanations,
    # not persistence handles for private profile/evidence/requirement records.
    forbidden_fields = {
        "profileId", "extractionId", "reportId", "cohortId", "evidenceId",
        "evidenceIds", "profileSkillIds", "requirementId", "supportingRequirementIds",
        "matchedRequirementIds", "partialRequirementIds", "missingRequirementIds",
        "evidenceLinks", "rawResume", "rawJd", "sourceRaw", "canonicalKey",
    }

    def public_keys(value: object) -> set[str]:
        if isinstance(value, dict):
            return set(value) | set().union(*(public_keys(v) for v in value.values()))
        if isinstance(value, list):
            return set().union(*(public_keys(v) for v in value))
        return set()

    for result in (*first.values(), *second.values()):
        assert not (public_keys(result["data"]) & forbidden_fields)
