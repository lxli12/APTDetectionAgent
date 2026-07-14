"""Real structured PIDSMaker backend source contracts.

Requirements: REQ-TOOL-001..005, REQ-ARTIFACT-001..003,
REQ-CAUSAL-001..004, REQ-LABEL-001..004.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StructuredPIDSBackendTests(unittest.TestCase):
    def test_adapter_targets_project_frozen_runner_not_upstream_main(self) -> None:
        text = (ROOT / "src/apt_detection_agent/pidsmaker/adapter.py").read_text()
        self.assertIn("run_frozen_pids_tool.py", text)
        self.assertNotIn('"pidsmaker/main.py"', text)
        self.assertIn("approved_bundles", text)
        self.assertIn("standardize_frozen_test_scores", text)
        self.assertIn("tool_calls.jsonl", text)
        self.assertIn("stage_trace=stage_trace", text)

    def test_backend_uses_exact_window_and_frozen_assets_only(self) -> None:
        text = (ROOT / "scripts/run_frozen_pids_tool.py").read_text()
        self.assertIn('phase="infer"', text)
        self.assertIn('stop_after="feat_inference"', text)
        self.assertIn("validate_frozen_bundle", text)
        self.assertIn("test_window_start_ns", text)
        self.assertNotIn("shell=True", text)
        self.assertNotIn("wandb", text.lower())

    def test_smoke_executor_reads_secret_file_without_putting_password_in_request(self) -> None:
        text = (ROOT / "scripts" / "run_structured_pids_adapter_smoke.py").read_text()
        self.assertIn("APT_PIDS_DB_SECRET_FILE", text)
        self.assertIn("PIDS_WORKER_PASSWORD", text)
        self.assertNotIn('parser.add_argument("--database-password"', text)

    def test_agent_request_cannot_select_paths_credentials_or_cuda(self) -> None:
        request_source = (
            ROOT / "src/apt_detection_agent/pidsmaker/adapter.py"
        ).read_text().split("class PIDSDetectionRequest", 1)[1].split(
            "@dataclass", 1
        )[0]
        for forbidden in (
            "frozen_bundle",
            "compatibility_root",
            "database_environment",
            "cuda_visible_devices",
        ):
            self.assertNotIn(forbidden, request_source)


if __name__ == "__main__":
    unittest.main()
