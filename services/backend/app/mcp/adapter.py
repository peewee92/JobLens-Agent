"""MCP-to-Registry adapter with no business rules of its own."""
from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from app.agent.context import CareerAgentContext, CareerAgentContextBlocker, CareerAgentContextBuilder
from app.agent.tool_registry import (
    CareerAgentToolError,
    CareerAgentToolName,
    CareerAgentToolRegistry,
    JobPreparationRequest,
    RankMatchReportsRequest,
    TargetCohortGapsRequest,
)
from app.api.v1.schemas.job_preparation import JobPreparationResponse
from app.api.v1.schemas.match_ranking import BatchMatchRankingResponse
from app.api.v1.schemas.target_cohort_gaps import TargetCohortGapResponse
from app.application.create_target_cohort import TargetCohortSelectionError
from app.application.job_queries.errors import JobNotFoundError
from app.application.match_report import MatchReportPersistenceNotReadyError
from app.mcp.schemas import (
    JobPreparationInput,
    McpToolEnvelope,
    RankMatchReportsInput,
    TargetCohortGapsInput,
)


class JobLensMcpAdapter:
    """Expose only registered, governed, read-only workflows to MCP.

    The adapter owns transport validation and stable error/result projection. It
    intentionally delegates all context, selection, and current-job checks to
    existing Agent boundaries.
    """

    def __init__(
        self,
        *,
        context_builder: CareerAgentContextBuilder,
        tool_registry: CareerAgentToolRegistry,
        trace_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._context_builder = context_builder
        self._tool_registry = tool_registry
        self._trace_id_factory = trace_id_factory or (lambda: f"mcp_{uuid4().hex}")

    def rank_match_reports(self, request: RankMatchReportsInput) -> McpToolEnvelope:
        tool = CareerAgentToolName.RANK_MATCH_REPORTS
        return self._invoke(
            tool=tool,
            context=self._context_builder.build(),
            request=RankMatchReportsRequest(
                job_ids=tuple(request.job_ids),
                include_blocked=request.include_blocked,
                top_n=request.top_n,
            ),
            project=lambda output: BatchMatchRankingResponse.from_details(output).model_dump(
                by_alias=True, mode="json"
            ),
        )

    def target_cohort_gaps(self, request: TargetCohortGapsInput) -> McpToolEnvelope:
        tool = CareerAgentToolName.TARGET_COHORT_GAPS
        return self._invoke(
            tool=tool,
            context=self._context_builder.build(),
            request=TargetCohortGapsRequest(
                cohort_id=f"mcp_cohort_{uuid4().hex}",
                name=request.name,
                selected_job_ids=tuple(request.selected_job_ids),
            ),
            project=self._project_gap_response,
        )

    def job_preparation(self, request: JobPreparationInput) -> McpToolEnvelope:
        tool = CareerAgentToolName.JOB_PREPARATION
        return self._invoke(
            tool=tool,
            context=self._context_builder.build(current_job_id=request.job_id),
            request=JobPreparationRequest(job_id=request.job_id),
            project=lambda output: JobPreparationResponse.from_result(output).model_dump(
                by_alias=True, mode="json"
            ),
        )

    def _invoke(self, *, tool: CareerAgentToolName, context: CareerAgentContext, request: object, project: Callable[[object], dict]) -> McpToolEnvelope:
        trace_id = self._trace_id_factory()
        if not context.usable:
            code = self._context_error_code(context)
            message = "; ".join(context.blocker_messages) or "JobLens context is not available."
            return McpToolEnvelope.failure(
                tool=tool.value, trace_id=trace_id, code=code, message=message
            )
        try:
            output = self._tool_registry.invoke(context=context, tool=tool, request=request)  # type: ignore[arg-type]
            return McpToolEnvelope.success(
                tool=tool.value, trace_id=trace_id, data=project(output)
            )
        except (CareerAgentToolError, TargetCohortSelectionError) as exc:
            return McpToolEnvelope.failure(
                tool=tool.value, trace_id=trace_id, code="invalid_argument", message=str(exc)
            )
        except MatchReportPersistenceNotReadyError as exc:
            return McpToolEnvelope.failure(
                tool=tool.value, trace_id=trace_id, code="match_not_ready", message=str(exc)
            )
        except JobNotFoundError as exc:
            return McpToolEnvelope.failure(
                tool=tool.value, trace_id=trace_id, code="not_found", message=str(exc)
            )
        except (OSError, TimeoutError) as exc:
            return McpToolEnvelope.failure(
                tool=tool.value,
                trace_id=trace_id,
                code="backend_unavailable",
                message="JobLens local storage is temporarily unavailable.",
                retryable=True,
            )
        except Exception:
            return McpToolEnvelope.failure(
                tool=tool.value,
                trace_id=trace_id,
                code="internal_error",
                message="JobLens could not complete this read-only request.",
            )

    @staticmethod
    def _context_error_code(context: CareerAgentContext) -> str:
        blockers = set(context.blockers)
        if CareerAgentContextBlocker.CURRENT_JOB_NOT_FOUND in blockers:
            return "not_found"
        if {
            CareerAgentContextBlocker.CAREER_CONTEXT_NOT_RELEASED,
            CareerAgentContextBlocker.CAREER_CONTEXT_IDENTITY_CHANGED,
            CareerAgentContextBlocker.RELEVANT_EVIDENCE_NOT_CONFIRMED,
        } & blockers:
            return "context_not_released"
        return "business_invariant"

    @staticmethod
    def _project_gap_response(output: object) -> dict:
        """Remove the transport-private cohort handle from the public result.

        MCP callers select jobs directly on every request.  The cohort ID only
        exists to satisfy the internal workflow contract and cannot be reused
        across requests, so returning it would advertise a false public API.
        """
        response = TargetCohortGapResponse.from_result(output).model_dump(
            by_alias=True, mode="json"
        )
        response.pop("cohortId", None)
        return response
