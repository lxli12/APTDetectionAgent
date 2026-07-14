"""End-to-end validation harnesses; synthetic evidence is never formal performance."""

from .report import finalize_public_report
from .synthetic import SyntheticScenarioConfig, SyntheticScenarioRunner

__all__ = ["SyntheticScenarioConfig", "SyntheticScenarioRunner", "finalize_public_report"]
