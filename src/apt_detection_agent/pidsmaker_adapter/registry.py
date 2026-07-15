"""Descriptive catalog of PIDSMaker-backed detectors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PIDSCapability:
    detector: str
    config_name: str
    description: str


class PIDSRegistry:
    def __init__(self, capabilities: tuple[PIDSCapability, ...]) -> None:
        self._items = {item.detector.casefold(): item for item in capabilities}

    def get(self, detector: str) -> PIDSCapability:
        try:
            return self._items[detector.casefold()]
        except KeyError as exc:
            raise KeyError(f"unknown PIDS detector: {detector}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(item.detector for item in self._items.values()))


def default_registry() -> PIDSRegistry:
    names = ("VELOX", "ORTHRUS", "MAGIC", "FLASH", "KAIROS", "NODLINK", "ThreatRace", "RCAID")
    return PIDSRegistry(tuple(
        PIDSCapability(name, name.casefold(), f"PIDSMaker {name} capability")
        for name in names
    ))
