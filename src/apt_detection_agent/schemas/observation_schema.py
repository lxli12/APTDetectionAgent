"""Agent-visible observation contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class Observation:
    observation_id: str
    window_id: str
    observed_at: datetime
    provenance_evidence: tuple[Mapping[str, Any], ...] = ()
    pids_results: tuple[Mapping[str, Any], ...] = ()
    memory_context: tuple[str, ...] = ()
    environment_state: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.observation_id or not self.window_id:
            raise ValueError("observation_id and window_id are required")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["observed_at"] = self.observed_at.isoformat()
        return value
