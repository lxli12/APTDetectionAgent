"""Static policy tests for live process/filesystem isolation provisioning."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OSIsolationPolicyTests(unittest.TestCase):
    def test_provisioner_uses_distinct_non_login_users_and_private_modes(self) -> None:
        script = (ROOT / "scripts" / "provision_os_isolation.sh").read_text()
        for identity in (
            "apt_agent_controller",
            "apt_pids_worker",
            "apt_hidden_evaluator",
        ):
            self.assertIn(identity, script)
        self.assertIn("/usr/sbin/nologin", script)
        self.assertIn(
            'find "$BASE/evaluator-private" -type d -exec chmod 700 {} +', script
        )
        self.assertIn('chmod 2770 "$BASE/feedback-exchange"', script)
        self.assertNotIn("PIDS_WORKER_PASSWORD=$PIDS_WORKER_PASSWORD", script)
        self.assertNotIn("HIDDEN_EVALUATOR_PASSWORD=$HIDDEN_EVALUATOR_PASSWORD", script)

    def test_split_secret_files_are_non_overwriting_and_role_specific(self) -> None:
        script = (ROOT / "scripts" / "provision_os_isolation.sh").read_text()
        self.assertIn("partial split secret state; refusing overwrite", script)
        self.assertIn("os_isolation=already-provisioned", script)
        self.assertIn("pids_worker.env", script)
        self.assertIn("hidden_evaluator.env", script)
        self.assertIn('chown root:apt_pids_worker "$PIDS_SECRET"', script)
        self.assertIn('chown root:apt_hidden_evaluator "$EVALUATOR_SECRET"', script)

    def test_process_runtime_code_is_root_owned_and_group_read_only(self) -> None:
        script = (ROOT / "scripts" / "run_real_e2e.sh").read_text()
        self.assertIn('chown -R root:apt_agent_controller "$RUNTIME_ROOT/controller"', script)
        self.assertIn('chown -R root:apt_pids_worker "$RUNTIME_ROOT/pids"', script)
        self.assertIn('chown -R root:apt_hidden_evaluator "$RUNTIME_ROOT/evaluator"', script)
        self.assertIn("-type f -exec chmod 640", script)


if __name__ == "__main__":
    unittest.main()
