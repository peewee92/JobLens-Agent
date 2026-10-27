"""Workspace materials reference an immutable analysis, not newly computed facts."""
from dataclasses import dataclass
from app.application.application_workspace.models import ApplicationWorkspaceSourceSnapshot
from app.application.job_preparation.bundle import JobPreparationBundle


@dataclass(frozen=True, slots=True)
class SavedWorkspacePreparation:
    thread_id: str
    result_id: str
    snapshot: ApplicationWorkspaceSourceSnapshot
    bundle: JobPreparationBundle
    stale_reasons: tuple[str, ...]

    @property
    def is_current(self):
        return not self.stale_reasons
