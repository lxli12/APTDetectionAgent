"""Normalize JSON backend output without exposing PIDSMaker internals."""

from __future__ import annotations

import json
from typing import Any, Mapping

from apt_detection_agent.schemas import PIDSResult


class ResultParser:
    def parse(self, detector: str, run_id: str, payload: str | Mapping[str, Any]) -> PIDSResult:
        data = json.loads(payload) if isinstance(payload, str) else dict(payload)
        if not isinstance(data, dict):
            raise ValueError("PIDSMaker result must be a JSON object")
        alerts = data.get("alerts", ())
        scores = data.get("scores", ())
        if not isinstance(alerts, (list, tuple)) or not isinstance(scores, (list, tuple)):
            raise ValueError("PIDSMaker alerts and scores must be arrays")
        return PIDSResult(
            detector=detector,
            run_id=run_id,
            status=str(data.get("status", "succeeded")),
            alerts=tuple(dict(item) for item in alerts),
            scores=tuple(float(item) for item in scores),
            metadata=dict(data.get("metadata", {})),
        )
