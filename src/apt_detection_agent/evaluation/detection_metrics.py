"""Agent-level detection metrics."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class DetectionMetrics:
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    coverage: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


def compute_detection_metrics(predicted: set[str], truth: set[str]) -> DetectionMetrics:
    tp = len(predicted & truth)
    fp = len(predicted - truth)
    fn = len(truth - predicted)
    return DetectionMetrics(
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=tp / (tp + fp) if tp + fp else 0.0,
        coverage=tp / len(truth) if truth else 0.0,
    )
