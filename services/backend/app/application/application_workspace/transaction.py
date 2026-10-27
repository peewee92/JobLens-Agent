"""A caller-owned boundary around existing local workspace commands."""
from __future__ import annotations
from typing import Callable, Protocol, TypeVar, Generic
from app.application.application_workspace.status_use_case import WorkspaceStatusRepository, ApplicationTimelineRepository
from app.application.application_workspace.execution_action import ExecutionActionRepository
from app.application.application_workspace.evidence_context import EvidenceActionSources
from app.application.application_workspace.evidence_proposal import EvidenceProposalRepository
from app.application.career_context.models import SaveProfileCommand, ProfileDetail
from app.application.ports.career_context_repository import AbstractCareerContextRepository, AbstractCareerContextQueryRepository
from app.application.career_context.use_cases import SaveProfileUseCase


class WorkspacePersistenceError(RuntimeError):
    """The local business transaction could not be committed."""


class WorkspaceCommandUnitOfWork(Protocol):
    workspaces: WorkspaceStatusRepository
    timeline: ApplicationTimelineRepository
    actions: ExecutionActionRepository
    proposals: EvidenceProposalRepository
    evidence_sources: EvidenceActionSources
    profiles: AbstractCareerContextQueryRepository
    profile_writer: AbstractCareerContextRepository

    def __enter__(self) -> WorkspaceCommandUnitOfWork: ...
    def __exit__(self, exc_type, exc, tb): ...
    def commit(self) -> None: ...


class SaveProfileInTransaction:
    """Use existing normalization and version rules without a nested commit."""
    def __init__(self, repository: AbstractCareerContextRepository):
        self._repository = repository

    def execute(self, command: SaveProfileCommand) -> ProfileDetail:
        return SaveProfileUseCase.execute_in_repository(command, self._repository)


T = TypeVar('T')
T_co = TypeVar('T_co', covariant=True)


class ExecutableCommand(Protocol[T_co]):
    def execute(self, *args, **kwargs) -> T_co: ...


class TransactionalWorkspaceCommand(Generic[T]):
    def __init__(self, factory: Callable[[], WorkspaceCommandUnitOfWork],
                 build: Callable[[WorkspaceCommandUnitOfWork], ExecutableCommand[T]]):
        self._factory, self._build = factory, build

    def execute(self, *args, **kwargs) -> T:
        with self._factory() as uow:
            result = self._build(uow).execute(*args, **kwargs)
            uow.commit()
            return result
