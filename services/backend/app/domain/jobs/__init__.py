"""Job-domain types shared across backend layers."""

from app.domain.jobs.enums import ImportOutcome, RemoteConfidence, RemoteStatus

__all__ = ["ImportOutcome", "RemoteConfidence", "RemoteStatus"]
