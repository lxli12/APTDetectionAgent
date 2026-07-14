"""Deprecated compatibility import; use :mod:`apt_detection_agent.runtime`.

Requirements: REQ-GOV-003, REQ-RUNTIME-001..006.
"""

from apt_detection_agent.runtime import *  # noqa: F401,F403
from apt_detection_agent.runtime import __all__ as _runtime_all
from apt_detection_agent.experiment.legacy_controller import (
    Controller, ControllerConfig, ControllerStepResult, TriggerDecision,
)
__all__ = [*_runtime_all, "Controller", "ControllerConfig", "ControllerStepResult", "TriggerDecision"]
