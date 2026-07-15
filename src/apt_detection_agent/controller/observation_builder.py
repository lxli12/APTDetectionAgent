"""Build Agent-visible observations from already sanitized state."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from apt_detection_agent.schemas import Observation, PIDSResult


class ObservationBuilder:
    def build(
        self,
        *,
        window_id: str,
        observed_at: datetime,
        provenance_evidence: tuple[Mapping[str, Any], ...],
        pids_results: tuple[PIDSResult, ...],
        memory_context: tuple[str, ...],
        environment_state: Mapping[str, Any],
    ) -> Observation:
        return Observation(
            observation_id=str(uuid4()),
            window_id=window_id,
            observed_at=observed_at,
            provenance_evidence=provenance_evidence,
            pids_results=tuple(item.to_dict() for item in pids_results),
            memory_context=memory_context,
            environment_state=dict(environment_state),
        )
