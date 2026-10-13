from __future__ import annotations

import asyncio

import pytest

try:
    import mcp  # noqa: F401
except ImportError as exc:  # pragma: no cover - only when SDK installation is incomplete
    pytest.skip(f"MCP SDK is unavailable: {exc}", allow_module_level=True)

from app.agent.context import CareerAgentContext
from app.mcp.adapter import JobLensMcpAdapter
from app.mcp.server import create_mcp_server


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
    assert by_name["job_preparation"]._meta["joblens"]["requiresCurrentJob"] is True
