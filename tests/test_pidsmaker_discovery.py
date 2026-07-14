"""Dynamic PIDSMaker inventory tests against the pinned submodule.

Requirements: REQ-PIDS-001..005, REQ-CAUSAL-004, REQ-ARTIFACT-002.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from apt_detection_agent.pidsmaker import PIDSMakerDiscovery
from apt_detection_agent.schemas import AvailabilityStatus, DetectionUnit, TransductiveStatus


ROOT = Path(__file__).resolve().parents[1]


class PIDSMakerDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.discovery = PIDSMakerDiscovery(ROOT)

    def test_discovers_every_top_level_system_config(self) -> None:
        ids = self.discovery.model_config_ids()
        expected_from_files = {
            path.stem
            for path in (ROOT / "PIDSMaker/config").glob("*.yml")
            if path.stem not in {"default", "tests"}
        }
        self.assertEqual(set(ids), expected_from_files)
        self.assertEqual(len(ids), 10)

    def test_normalizes_orthrus_variants_without_losing_source_configs(self) -> None:
        capabilities = self.discovery.capabilities()
        identities = {(item.pids.pids_id, item.pids.variant_id) for item in capabilities}
        self.assertIn(("orthrus", "default"), identities)
        self.assertIn(("orthrus", "fixed"), identities)
        self.assertIn(("orthrus", "non_snooped"), identities)
        self.assertNotIn(("orthrus_fixed", "default"), identities)
        self.assertEqual(len({item.source_config_id for item in capabilities}), 10)

    def test_discovers_all_dataset_literals_from_config_source(self) -> None:
        datasets = self.discovery.dataset_ids()
        self.assertEqual(len(datasets), 15)
        self.assertIn("CADETS_E3", datasets)
        self.assertIn("ATLASV2_EDR", datasets)
        self.assertIn("CARBANAKV2_EDR", datasets)

    def test_inheritance_resolves_causal_and_transductive_evidence(self) -> None:
        by_source = {item.source_config_id: item for item in self.discovery.capabilities()}
        self.assertEqual(by_source["orthrus"].transductive_status, TransductiveStatus.TRANSDUCTIVE)
        self.assertEqual(by_source["rcaid"].transductive_status, TransductiveStatus.TRANSDUCTIVE)
        self.assertEqual(by_source["kairos"].transductive_status, TransductiveStatus.TRANSDUCTIVE)
        for source in ("velox", "orthrus_fixed", "orthrus_non_snooped", "flash", "magic", "nodlink", "threatrace"):
            self.assertEqual(by_source[source].transductive_status, TransductiveStatus.CAUSAL)

    def test_detection_units_come_from_resolved_pipeline_config(self) -> None:
        by_source = {item.source_config_id: item for item in self.discovery.capabilities()}
        self.assertEqual(by_source["orthrus_fixed"].detection_unit, DetectionUnit.EDGE)
        self.assertEqual(by_source["kairos"].detection_unit, DetectionUnit.NODE)
        self.assertEqual(by_source["velox"].detection_unit, DetectionUnit.NODE)

    def test_missing_checkpoint_root_retains_all_models_as_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "not-created"
            capabilities = PIDSMakerDiscovery(ROOT, checkpoint_root=missing).capabilities()
        self.assertEqual(len(capabilities), 10)
        self.assertTrue(
            all(item.current_availability_status == AvailabilityStatus.UNAVAILABLE for item in capabilities)
        )
        self.assertTrue(all(item.unavailable_reason for item in capabilities))

    def test_feat_inference_is_internal_pipeline_stage(self) -> None:
        for capability in self.discovery.capabilities():
            stages = {stage.value for stage in capability.required_pipeline_stages}
            self.assertIn("feat_inference", stages)


if __name__ == "__main__":
    unittest.main()
