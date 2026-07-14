"""PIDSMaker discovery and adapter boundary.

Requirements: REQ-PIDS-001..005, REQ-TOOL-001..005.
"""

from .registry import DiscoveryError, PIDSMakerDiscovery
from .adapter import ExecutionOutcome, PIDSDetectionRequest, PIDSMakerAdapter
from .admission import PIDSAdmissionRegistry

__all__ = [
    "DiscoveryError",
    "ExecutionOutcome",
    "PIDSDetectionRequest",
    "PIDSMakerAdapter",
    "PIDSAdmissionRegistry",
    "PIDSMakerDiscovery",
]
