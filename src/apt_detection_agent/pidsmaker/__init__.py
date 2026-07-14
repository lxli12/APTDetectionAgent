"""PIDSMaker discovery and adapter boundary.

Requirements: REQ-PIDS-001..005, REQ-TOOL-001..005.
"""

from .discovery import DiscoveryError, PIDSMakerDiscovery
from .adapter import ExecutionOutcome, PIDSDetectionRequest, PIDSMakerAdapter
from .tools import (
    ApprovedConfigCatalog,
    PIDSToolService,
    ResultComparison,
    TraceResult,
    VisibleTraceGraph,
)

__all__ = [
    "DiscoveryError",
    "ApprovedConfigCatalog",
    "ExecutionOutcome",
    "PIDSDetectionRequest",
    "PIDSMakerAdapter",
    "PIDSMakerDiscovery",
    "PIDSToolService",
    "ResultComparison",
    "TraceResult",
    "VisibleTraceGraph",
]
