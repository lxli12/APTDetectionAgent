"""Tool protocol and declarative specification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    required_arguments: frozenset[str]
    handler: Callable[[Mapping[str, Any]], Mapping[str, Any]]

    def validate(self, arguments: Mapping[str, Any]) -> None:
        missing = self.required_arguments - arguments.keys()
        if missing:
            raise ValueError(f"missing tool arguments: {sorted(missing)}")
