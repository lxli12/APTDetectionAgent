"""Phase 0 governance tests.

Requirements: REQ-GOV-001, REQ-GOV-003, REQ-GIT-003,
REQ-RESOURCE-001, REQ-WANDB-001.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class GovernanceTests(unittest.TestCase):
    def test_governance_checker_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_governance.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_resource_profile_uses_project_quota(self) -> None:
        profile = (ROOT / "configs/resource_profiles/autodl.yaml").read_text()
        self.assertRegex(profile, r"(?m)^cpu_vcpus: 32$")
        self.assertRegex(profile, r"(?m)^memory_gib: 240$")
        self.assertRegex(profile, r"(?m)^gpu_count: 2$")
        self.assertRegex(profile, r"(?m)^gpu_memory_gib_per_device: 24$")

    def test_project_has_no_wandb_dependency(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text().lower()
        self.assertNotIn("wandb", pyproject)

    def test_matrix_has_unique_requirement_rows(self) -> None:
        matrix = (ROOT / "docs/plans/REQUIREMENT_TRACEABILITY.md").read_text()
        row_ids = re.findall(r"(?m)^\| (REQ-[A-Z]+-\d{3}) \|", matrix)
        self.assertGreaterEqual(len(row_ids), 25)
        self.assertEqual(len(row_ids), len(set(row_ids)))


if __name__ == "__main__":
    unittest.main()
