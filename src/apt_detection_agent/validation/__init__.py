"""Deprecated compatibility namespace for REQ-GOV-003."""
from apt_detection_agent.evaluation.reporting import finalize_public_report
from apt_detection_agent.experiment import SyntheticScenarioConfig, SyntheticScenarioRunner
__all__ = ["SyntheticScenarioConfig", "SyntheticScenarioRunner", "finalize_public_report"]
