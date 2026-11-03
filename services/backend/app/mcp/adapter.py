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
            request=RankMatchReportsRequest(
                job_ids=tuple(request.job_ids),
                include_blocked=request.include_blocked,
                top_n=request.top_n,
            ),
            project=self._project_ranking_response,
        )

    def target_cohort_gaps(self, request: TargetCohortGapsInput) -> McpToolEnvelope:
        tool = CareerAgentToolName.TARGET_COHORT_GAPS
        return self._invoke(
            tool=tool,
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
            current_job_id=request.job_id,
            request=JobPreparationRequest(job_id=request.job_id),
            project=self._project_preparation_response,
        )

    def _invoke(
        self,
        *,
        tool: CareerAgentToolName,
        request: object,
        project: Callable[[object], dict],
        current_job_id: str | None = None,
    ) -> McpToolEnvelope:
        trace_id = self._trace_id_factory()
        try:
            context = (
                self._context_builder.build(current_job_id=current_job_id)
                if current_job_id is not None
                else self._context_builder.build()
            )
            if not context.usable:
                code = self._context_error_code(context)
                message = {
                    "not_found": "The requested JobLens job is not available.",
                    "context_not_released": "JobLens career context is not released for this request.",
                }.get(code, "JobLens context cannot be used for this request.")
                return McpToolEnvelope.failure(
                    tool=tool.value, trace_id=trace_id, code=code, message=message
                )
            output = self._tool_registry.invoke(context=context, tool=tool, request=request)  # type: ignore[arg-type]
            return McpToolEnvelope.success(
                tool=tool.value, trace_id=trace_id, data=project(output)
            )
        except (CareerAgentToolError, TargetCohortSelectionError):
            return McpToolEnvelope.failure(
                tool=tool.value,
                trace_id=trace_id,
                code="invalid_argument",
                message="JobLens rejected the requested tool arguments.",
            )
        except MatchReportPersistenceNotReadyError:
            return McpToolEnvelope.failure(
                tool=tool.value,
                trace_id=trace_id,
                code="match_not_ready",
                message="JobLens match facts are not ready for this request.",
            )
        except JobNotFoundError:
            return McpToolEnvelope.failure(
                tool=tool.value,
                trace_id=trace_id,
                code="not_found",
                message="The requested JobLens job is not available.",
            )
        except (OSError, TimeoutError):
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
    def _project_ranking_response(output: object) -> dict:
        """Expose ranking decisions without private persistence/evidence handles."""
        response = BatchMatchRankingResponse.from_details(output).model_dump(
            by_alias=True, mode="json"
        )
        return {
            "items": [
                {
                    "jobId": item["jobId"],
                    "eligibility": item["eligibility"],
                    "recommendation": item["recommendation"],
                    "summary": item["summary"],
                    "matchedRequirementCount": len(item["matchedRequirementIds"]),
                    "partialRequirementCount": len(item["partialRequirementIds"]),
                    "missingRequirementCount": len(item["missingRequirementIds"]),
                    "evidenceLinkCount": len(item["evidenceLinks"]),
                }
                for item in response["items"]
            ],
            "count": response["count"],
        }

    @staticmethod
    def _project_gap_response(output: object) -> dict:
        """Expose grounded gaps without cohort, profile or evidence record IDs."""
        response = TargetCohortGapResponse.from_result(output).model_dump(
            by_alias=True, mode="json"
        )
        return {
            "jobIds": response["jobIds"],
            "factsUsable": response["factsUsable"],
            "items": [
                {
                    "capability": item["capability"],
                    "priority": item["priority"],
                    "whyImportant": item["whyImportant"],
                    "supportingJobIds": item["supportingJobIds"],
                    "currentState": item["currentState"],
                    "completionCriteria": item["completionCriteria"],
                    "supportingRequirementCount": len(item["supportingRequirementIds"]),
                    "confirmedEvidenceCount": len(item["evidenceIds"]),
                }
                for item in response["items"]
            ],
            "blockers": response["blockers"],
        }

    @staticmethod
    def _project_preparation_response(output: object) -> dict:
        """Keep reviewed preparation facts, never private record identifiers."""
        response = JobPreparationResponse.from_result(output).model_dump(
            by_alias=True, mode="json"
        )
        resume = response["resumeDelta"]
        experience = response["experiencePriority"]
        stories = response["storyFacts"]
        interview = response["interviewFacts"]
        study = response["studyChecklist"]
        return {
            "jobId": response["jobId"],
            "factsUsable": response["factsUsable"],
            "resumeDelta": None if resume is None else {
                "highlights": [
                    {"capability": item["capability"], "evidenceCount": len(item["evidenceIds"])}
                    for item in resume["highlights"]
                ],
                "evidenceGaps": [
                    {"capability": item["capability"], "status": item["status"]}
                    for item in resume["evidenceGaps"]
                ],
            },
            "experiencePriority": None if experience is None else {
                "items": [
                    {
                        "evidenceType": item["evidenceType"],
                        "matchedCapabilities": item["matchedCapabilities"],
                        "mustHaveCount": item["mustHaveCount"],
                        "requirementCount": item["requirementCount"],
                    }
                    for item in experience["items"]
                ],
            },
            "storyFacts": None if stories is None else {
                "items": [
                    {
                        "evidenceType": item["evidenceType"],
                        "evidenceSummary": item["evidenceSummary"],
                        "matchedCapabilities": item["matchedCapabilities"],
                        "mustHaveCount": item["mustHaveCount"],
                        "requirementCount": item["requirementCount"],
                    }
                    for item in stories["items"]
                ],
            },
            "interviewFacts": None if interview is None else {
                "items": [
                    {
                        "requirementType": item["requirementType"],
                        "requirementText": item["requirementText"],
                        "importance": item["importance"],
                        "normalizedCapability": item["normalizedCapability"],
                        "preparationPriority": item["preparationPriority"],
                        "evidenceStatus": item["evidenceStatus"],
                        "evidenceSummaries": item["evidenceSummaries"],
                    }
                    for item in interview["items"]
                ],
            },
            "studyChecklist": None if study is None else {
                "items": [
                    {
                        "requirementText": item["requirementText"],
                        "capability": item["capability"],
                        "importance": item["importance"],
                        "evidenceStatus": item["evidenceStatus"],
                        "need": item["need"],
                        "completionCriteria": item["completionCriteria"],
                    }
                    for item in study["items"]
                ],
            },
            "blockers": response["blockers"],
        }
