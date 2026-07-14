"""Agent policy boundary.

The Agent proposes intent; it does not execute tools or author runtime facts.
Requirements: REQ-RUNTIME-003, REQ-TOOL-001..005, REQ-LABEL-001..004.
"""

from .policy import AgentPolicy, PolicyOutput

__all__ = ["AgentPolicy", "PolicyOutput"]
