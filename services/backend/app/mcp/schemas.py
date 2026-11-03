"""Public MCP contracts.

These schemas deliberately differ from internal Agent requests: MCP consumers
never see transient cohort IDs or internal persistence objects.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class McpModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class RankMatchReportsInput(McpModel):
    job_ids: list[str] = Field(min_length=1, max_length=50)
    include_blocked: bool = False
    top_n: int | None = Field(default=None, ge=1, le=50)


class TargetCohortGapsInput(McpModel):
    selected_job_ids: list[str] = Field(min_length=1, max_length=20)
    name: str = Field(default="MCP Target Cohort", min_length=1, max_length=120)


class JobPreparationInput(McpModel):
    job_id: str = Field(min_length=1, max_length=128)


class McpError(McpModel):
    code: str
    message: str
    retryable: bool = False


class McpMeta(McpModel):
    tool: str
    schema_version: str = "1"
    trace_id: str
    provider_calls: int = 0
    business_writes: int = 0


class McpToolEnvelope(McpModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: McpError | None = None
    meta: McpMeta

    @classmethod
    def success(
        cls, *, tool: str, trace_id: str, data: dict[str, Any]
    ) -> "McpToolEnvelope":
        return cls(ok=True, data=data, meta=McpMeta(tool=tool, trace_id=trace_id))

    @classmethod
    def failure(
        cls,
        *,
        tool: str,
        trace_id: str,
        code: str,
        message: str,
        retryable: bool = False,
    ) -> "McpToolEnvelope":
        return cls(
            ok=False,
            error=McpError(code=code, message=message, retryable=retryable),
            meta=McpMeta(tool=tool, trace_id=trace_id),
        )
