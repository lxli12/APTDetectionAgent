"""Central deployable-data leakage detection and sanitization."""

from __future__ import annotations

from dataclasses import is_dataclass
import re
from typing import Any, Mapping

from ._serialization import encode


class DeployableDataLeakageError(ValueError):
    """Raised when privileged or label-derived data reaches an online contract."""


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")


FORBIDDEN_DEPLOYABLE_FIELDS = frozenset({
    "attack", "attack_id", "attack_identity", "attack_name", "attack_type",
    "attack_time", "attack_times", "attack_timestamp", "attack_to_time_window",
    "campaign", "campaign_id", "campaign_identity", "malicious_node",
    "malicious_nodes", "malicious_entity", "malicious_entities", "ground_truth",
    "ground_truth_labels", "label", "labels", "true_label", "hidden_label",
    "tp", "fp", "fn", "tn", "true_positive", "true_positives", "false_positive",
    "false_positives", "false_negative", "false_negatives", "true_negative",
    "true_negatives", "precision", "recall", "coverage", "attack_coverage",
    "p_at_c_100", "adp", "mcc", "confusion_matrix", "is_malicious",
    "label_derived_metrics", "counterfactual_best_action",
})

_FORBIDDEN_TEXT_PATTERN = re.compile(
    r"(?i)(?:^|[^a-z0-9])(?:attack[_ -]?(?:id|identity|time)|malicious[_ -]?nodes?|"
    r"ground[_ -]?truth|true[_ -]?positives?|false[_ -]?(?:positives?|negatives?)|"
    r"attack[_ -]?coverage|p@c|\bADP\b|\bMCC\b|\bTP\b|\bFP\b|\bFN\b|\bTN\b)"
    r"(?:$|[^a-z0-9])"
)


def find_deployable_leaks(value: Any, path: str = "$") -> tuple[str, ...]:
    """Return deterministic field/value paths containing deployment-hidden data."""

    if is_dataclass(value):
        value = encode(value)
    leaks: list[str] = []
    if isinstance(value, Mapping):
        for raw_key in sorted(value, key=lambda item: str(item)):
            key = str(raw_key)
            child_path = f"{path}.{key}"
            if _normalize_key(key) in FORBIDDEN_DEPLOYABLE_FIELDS:
                leaks.append(child_path)
                continue
            leaks.extend(find_deployable_leaks(value[raw_key], child_path))
    elif isinstance(value, (tuple, list, set, frozenset)):
        for index, item in enumerate(value):
            leaks.extend(find_deployable_leaks(item, f"{path}[{index}]"))
    elif isinstance(value, str) and _FORBIDDEN_TEXT_PATTERN.search(value):
        leaks.append(path)
    return tuple(leaks)


def assert_deployable(value: Any) -> None:
    leaks = find_deployable_leaks(value)
    if leaks:
        raise DeployableDataLeakageError(
            "deployment-hidden data found at: " + ", ".join(leaks)
        )


def sanitize_deployable(value: Any) -> Any:
    """Recursively remove forbidden fields and tainted free-text values."""

    if is_dataclass(value):
        value = encode(value)
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for raw_key in sorted(value, key=lambda item: str(item)):
            key = str(raw_key)
            if _normalize_key(key) in FORBIDDEN_DEPLOYABLE_FIELDS:
                continue
            item = sanitize_deployable(value[raw_key])
            if item is not None:
                sanitized[key] = item
        return sanitized
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(
            item for raw_item in value if (item := sanitize_deployable(raw_item)) is not None
        )
    if isinstance(value, str) and _FORBIDDEN_TEXT_PATTERN.search(value):
        return None
    return value
