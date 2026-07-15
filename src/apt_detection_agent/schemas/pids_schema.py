"""Normalized PIDS backend result contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class PIDSResult:
    detector: str
    run_id: str
    status: str
    alerts: tuple[Mapping[str, Any], ...] = ()
    scores: tuple[float, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.detector or not self.run_id:
            raise ValueError("detector and run_id are required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
