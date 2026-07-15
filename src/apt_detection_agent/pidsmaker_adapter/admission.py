"""Explicit allow-list for exact backend configurations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Admission:
    detector: str
    config_name: str
    dataset: str


class AdmissionPolicy:
    def __init__(self, admitted: tuple[Admission, ...] = ()) -> None:
        self._admitted = {
            (item.detector.casefold(), item.config_name, item.dataset) for item in admitted
        }

    def require(self, detector: str, config_name: str, dataset: str) -> None:
        key = (detector.casefold(), config_name, dataset)
        if key not in self._admitted:
            raise PermissionError("PIDSMaker request is not explicitly admitted")
