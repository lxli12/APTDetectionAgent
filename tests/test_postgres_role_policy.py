"""Static contracts for approved PostgreSQL role provisioning.

Requirements: REQ-DB-001..003, REQ-LABEL-001, REQ-REPRO-001.
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PostgreSQLRolePolicyScriptTests(unittest.TestCase):
    def test_manifest_uses_measured_database_names_and_no_secret(self) -> None:
        manifest = (ROOT / "configs" / "database" / "autodl.yaml").read_text()
        for database in (
            "cadets_e3",
            "clearscope_e3",
            "clearscope_e5",
            "optc_h201",
            "theia_e3",
        ):
            self.assertIn(database, manifest)
        self.assertNotIn("password", manifest.casefold())
        self.assertIn("availability: absent", manifest)

    def test_provisioner_has_fixed_roles_and_read_only_worker_grants(self) -> None:
        script = (ROOT / "scripts" / "postgres" / "provision_roles.sh").read_text()
        for role in ("db_admin", "pids_worker", "hidden_evaluator", "agent_controller"):
            self.assertIn(role, script)
        self.assertIn("GRANT SELECT ON ALL TABLES", script)
        self.assertIn("REVOKE CONNECT", script)
        self.assertNotIn("GRANT ALL", script)
        self.assertNotIn("CREATE SCHEMA", script)
        self.assertNotIn("DROP ", script)
        self.assertNotIn("TRUNCATE ", script)

    def test_secrets_are_file_injected_and_not_echoed(self) -> None:
        script = (ROOT / "scripts" / "postgres" / "provision_roles.sh").read_text()
        self.assertIn("SECRET_FILE", script)
        self.assertIn("mode must be 400 or 600", script)
        self.assertNotIn("set -x", script)
        self.assertNotIn("database_password", script)

    def test_verifier_checks_login_connect_select_and_no_dml(self) -> None:
        script = (ROOT / "scripts" / "postgres" / "verify_role_policy.sh").read_text()
        self.assertIn("rolcanlogin", script)
        self.assertIn("has_database_privilege", script)
        self.assertIn("has_table_privilege", script)
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            self.assertIn(f"'{privilege}'", script)
        self.assertIn("hidden evaluator unexpectedly connected", script)


if __name__ == "__main__":
    unittest.main()
