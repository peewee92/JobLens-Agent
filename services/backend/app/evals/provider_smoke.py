"""Local non-secret snapshot for the latest explicit Requirement Provider smoke."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

DEFAULT_PROVIDER_SMOKE_SNAPSHOT = (
    Path(__file__).resolve().parents[4]
    / "data"
    / "local"
    / "requirement-provider-smoke.json"
)


@dataclass(frozen=True, slots=True)
class ProviderSmokeSnapshot:
    checked_at: str
    state: str
    provider: str
    model: str
    ready: bool
    blocker: str | None
    provider_calls: int
    plain_status_code: int | None
    structured_status_code: int | None


def save_provider_smoke_snapshot(
    snapshot: ProviderSmokeSnapshot,
    *,
    path: Path = DEFAULT_PROVIDER_SMOKE_SNAPSHOT,
) -> None:
    """Atomically persist a small non-secret smoke summary in gitignored local data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(asdict(snapshot), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_provider_smoke_snapshot(
    *,
    path: Path = DEFAULT_PROVIDER_SMOKE_SNAPSHOT,
) -> ProviderSmokeSnapshot | None:
    """Read the last smoke summary fail-soft; malformed local state never blocks MVP."""
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return ProviderSmokeSnapshot(
            checked_at=str(payload["checked_at"]),
            state=str(payload["state"]),
            provider=str(payload["provider"]),
            model=str(payload["model"]),
            ready=bool(payload["ready"]),
            blocker=(str(payload["blocker"]) if payload.get("blocker") is not None else None),
            provider_calls=int(payload["provider_calls"]),
            plain_status_code=(
                int(payload["plain_status_code"])
                if payload.get("plain_status_code") is not None
                else None
            ),
            structured_status_code=(
                int(payload["structured_status_code"])
                if payload.get("structured_status_code") is not None
                else None
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None
