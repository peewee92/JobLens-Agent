from pydantic import Field

from app.agent.entrypoint import CareerAgentGoal, CareerAgentTurn
from app.api.v1.schemas.common import CamelCaseModel


class CareerAgentTurnRequest(CamelCaseModel):
    goal: CareerAgentGoal
    current_job_id: str | None = None
    relevant_evidence_ids: list[str] = Field(default_factory=list)
    job_ids: list[str] = Field(default_factory=list)
    include_blocked: bool = False
    top_n: int | None = Field(default=None, ge=1, le=50)
    cohort_id: str | None = None
    cohort_name: str | None = None
    selected_feedback_ids: list[str] = Field(default_factory=list)

    def to_command(self) -> CareerAgentTurn:
        return CareerAgentTurn(
            goal=self.goal,
            current_job_id=self.current_job_id,
            relevant_evidence_ids=tuple(self.relevant_evidence_ids),
            job_ids=tuple(self.job_ids),
            include_blocked=self.include_blocked,
            top_n=self.top_n,
            cohort_id=self.cohort_id,
            cohort_name=self.cohort_name,
            selected_feedback_ids=tuple(self.selected_feedback_ids),
        )
