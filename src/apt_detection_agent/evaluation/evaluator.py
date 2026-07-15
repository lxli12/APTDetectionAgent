"""Offline evaluator; ground truth stays outside controller observations."""

from __future__ import annotations

from .cost_metrics import CostMetrics
from .detection_metrics import compute_detection_metrics


class Evaluator:
    def evaluate(
        self, predicted: set[str], truth: set[str], cost: CostMetrics
    ) -> dict[str, object]:
        return {
            "detection": compute_detection_metrics(predicted, truth).to_dict(),
            "cost": cost.to_dict(),
        }
