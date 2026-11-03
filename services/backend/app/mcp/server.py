"""Official-SDK STDIO server exposing the bounded JobLens MCP surface."""
from __future__ import annotations

from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from app.mcp.adapter import JobLensMcpAdapter
from app.mcp.schemas import JobPreparationInput, RankMatchReportsInput, TargetCohortGapsInput


def _annotations() -> ToolAnnotations:
    return ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


def _metadata(*, requires_current_job: bool = False, requires_explicit_selection: bool = False) -> dict[str, Any]:
    return {
        "joblens": {
            "providerCostClass": "none",
            "humanGateRequirement": "none",
            "timeoutClass": "local_workflow",
            "requiresCurrentJob": requires_current_job,
            "requiresExplicitSelection": requires_explicit_selection,
            "localOnly": True,
        }
    }


def create_mcp_server(adapter: JobLensMcpAdapter) -> MCPServer:
    """Register the three externally supported tools and nothing else."""
    server = MCPServer(
        "JobLens",
        instructions=(
            "Local read-only JobLens facts. Tools never call a Provider, write career "
            "facts, or estimate hiring probability."
        ),
    )

    @server.tool(
        name="rank_match_reports",
        description="Rank existing current JobLens MatchReports for explicit job IDs. Does not generate MatchReports or call an AI Provider.",
        annotations=_annotations(),
        meta=_metadata(),
    )
    def rank_match_reports(
        job_ids: Annotated[list[str], Field(min_length=1, max_length=50)],
        include_blocked: bool = False,
        top_n: Annotated[int | None, Field(default=None, ge=1, le=50)] = None,
    ) -> dict[str, Any]:
        return adapter.rank_match_reports(
            RankMatchReportsInput(
                job_ids=job_ids, include_blocked=include_blocked, top_n=top_n
            )
        ).model_dump(by_alias=True, mode="json")

    @server.tool(
        name="target_cohort_gaps",
        description="Analyze grounded Skill Gaps for explicitly selected JobLens jobs. Does not write UserFeedback or call an AI Provider.",
        annotations=_annotations(),
        meta=_metadata(requires_explicit_selection=True),
    )
    def target_cohort_gaps(
        selected_job_ids: Annotated[list[str], Field(min_length=1, max_length=20)],
        name: Annotated[str, Field(min_length=1, max_length=120)] = "MCP Target Cohort",
    ) -> dict[str, Any]:
        return adapter.target_cohort_gaps(
            TargetCohortGapsInput(selected_job_ids=selected_job_ids, name=name)
        ).model_dump(by_alias=True, mode="json")

    @server.tool(
        name="job_preparation",
        description="Read the grounded resume, interview and study preparation facts for one explicit current JobLens job. Does not rewrite a resume or call an AI Provider.",
        annotations=_annotations(),
        meta=_metadata(requires_current_job=True),
    )
    def job_preparation(job_id: Annotated[str, Field(min_length=1, max_length=128)]) -> dict[str, Any]:
        return adapter.job_preparation(JobPreparationInput(job_id=job_id)).model_dump(
            by_alias=True, mode="json"
        )

    return server
