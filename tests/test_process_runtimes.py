"""Versioned process-runtime build boundary tests."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_process_runtimes", ROOT / "scripts" / "build_process_runtimes.py"
)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class ProcessRuntimeTests(unittest.TestCase):
    def test_builder_source_declares_disjoint_runtime_surfaces(self) -> None:
        text = (ROOT / "scripts" / "build_process_runtimes.py").read_text()
        self.assertIn('"controller": ("finalize_real_public_report.py"', text)
        self.assertIn('"evaluator": (', text)
        self.assertIn('"build_real_hidden_request.py"', text)
        self.assertIn('"run_memory_retrieval_sensitivity.py"', text)
        self.assertIn('("schemas",)', text)

    def test_controller_runtime_excludes_evaluator_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            approved = Path(temp) / "approved"
            approved.mkdir()
            output = approved / "runtime-v1"
            with patch.dict(os.environ, {"APT_PROCESS_RUNTIME_BUILD_ROOT": str(approved)}):
                with patch("sys.argv", ["build", "--project-root", str(ROOT), "--output-root", str(output)]):
                    self.assertEqual(builder.main(), 0)
            controller = output / "controller"
            evaluator = output / "evaluator"
            self.assertFalse(
                (controller / "src" / "apt_detection_agent" / "evaluator").exists()
            )
            self.assertFalse(
                (controller / "scripts" / "build_real_hidden_request.py").exists()
            )
            self.assertTrue(
                (evaluator / "scripts" / "build_real_hidden_request.py").is_file()
            )
            self.assertTrue(
                (evaluator / "scripts" / "run_memory_retrieval_sensitivity.py").is_file()
            )
            self.assertTrue(
                (output / "pids" / "scripts" / "run_structured_pids_adapter_smoke.py").is_file()
            )
            self.assertFalse(
                (controller / "scripts" / "run_structured_pids_adapter_smoke.py").exists()
            )


if __name__ == "__main__":
    unittest.main()
