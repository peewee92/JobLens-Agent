"""Application-owned persistence ports for versioned Profile/SearchIntent."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.application.career_context.models import (
    CareerContextSnapshot,
    ProfileDetail,
    SaveProfileCommand,
    SaveSearchIntentCommand,
    SearchIntentDetail,
)


class AbstractCareerContextRepository(ABC):
    """Write-side persistence used inside a caller-owned transaction."""

    @abstractmethod
    def current_profile_version(self) -> int:
        """Return the latest local Profile version, or zero when absent."""

    @abstractmethod
    def add_profile_version(
        self,
        command: SaveProfileCommand,
        *,
        version: int,
    ) -> ProfileDetail:
        """Persist one immutable Profile aggregate and flush it."""

    @abstractmethod
    def current_search_intent_version(self) -> int:
        """Return the latest local SearchIntent version, or zero when absent."""

    @abstractmethod
    def add_search_intent_version(
        self,
        command: SaveSearchIntentCommand,
        *,
        version: int,
    ) -> SearchIntentDetail:
        """Persist one immutable SearchIntent version and flush it."""


class AbstractCareerContextQueryRepository(ABC):
    """Read-only current-version queries for API/Web/Agent consumers."""

    @abstractmethod
    def get_current_context(self) -> CareerContextSnapshot:
        """Atomically select current Profile/SearchIntent version identities."""

    @abstractmethod
    def get_current_profile(self) -> ProfileDetail | None:
        """Return the latest confirmed Profile version."""

    @abstractmethod
    def get_current_search_intent(self) -> SearchIntentDetail | None:
        """Return the latest confirmed SearchIntent version."""
