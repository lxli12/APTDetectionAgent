"""Validated PIDSMaker process adapter.

The caller supplies an executor-owned runner. Agent/LLM output is never accepted
as a shell command.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping
from uuid import uuid4

from apt_detection_agent.schemas import PIDSResult

from .admission import AdmissionPolicy
from .registry import PIDSRegistry
from .result_parser import ResultParser

BackendRunner = Callable[[str, str, str, Mapping[str, Any]], str | Mapping[str, Any]]


class PIDSMakerAdapter:
    def __init__(
        self,
        registry: PIDSRegistry,
        admission: AdmissionPolicy,
        runner: BackendRunner,
        parser: ResultParser | None = None,
    ) -> None:
        self.registry = registry
        self.admission = admission
        self.runner = runner
        self.parser = parser or ResultParser()

    def run(
        self, detector: str, config_name: str, dataset: str, parameters: Mapping[str, Any]
    ) -> PIDSResult:
        capability = self.registry.get(detector)
        if capability.config_name != config_name:
            raise ValueError("configuration does not match registered detector")
        self.admission.require(detector, config_name, dataset)
        run_id = str(uuid4())
        payload = self.runner(detector, config_name, dataset, dict(parameters))
        return self.parser.parse(detector, run_id, payload)
