"""Standard-library-only helpers for stable public contract serialization."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
import json
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "1.0"


def encode(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {item.name: encode(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): encode(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [encode(item) for item in value]
    return value


def versioned_dict(value: Any) -> dict[str, Any]:
    payload = encode(value)
    if not isinstance(payload, dict):
        raise TypeError("versioned contracts must encode to objects")
    return {"schema_version": SCHEMA_VERSION, **payload}


def deterministic_json(value: Any) -> str:
    payload = value.to_dict() if hasattr(value, "to_dict") else encode(value)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def nested_versioned(value: Any, name: str) -> dict[str, Any]:
    """Restore the top-level version omitted when a contract is nested."""

    data = dict(require_object(value, name))
    data.setdefault("schema_version", SCHEMA_VERSION)
    return data


def require_object(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object")
    return value


def require_keys(
    data: Mapping[str, Any],
    *,
    required: Iterable[str],
    optional: Iterable[str] = (),
    name: str,
    versioned: bool = False,
) -> None:
    required_set = set(required)
    optional_set = set(optional)
    if versioned:
        required_set.add("schema_version")
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"unsupported {name} schema_version")
    missing = required_set - data.keys()
    unknown = data.keys() - required_set - optional_set
    if missing:
        raise ValueError(f"{name} missing fields: {sorted(missing)}")
    if unknown:
        raise ValueError(f"{name} has unknown fields: {sorted(unknown)}")


def parse_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be an ISO-8601 string")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def require_nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")


def require_nonnegative(value: int | float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def require_unit_interval(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
        raise ValueError(f"{field_name} must be between 0 and 1")
