import ast
import json
from pathlib import Path

import yaml

from pidsmaker_adapter.configuration import checkpoint_slug, load_configuration_space

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "pidsmaker_adapter"


def test_finite_space_has_fixed_no_snoop_contract():
    space = yaml.safe_load(
        (ADAPTER / "config" / "configuration_space_v1.yaml").read_text(encoding="utf-8")
    )
    assert space["dataset"] == "CLEARSCOPE_E3"
    assert space["frozen"]["construction"]["time_window_size_minutes"] == 15
    assert space["frozen"]["reproducibility"]["seed"] == 42
    ids = [item["id"] for item in space["configurations"]]
    assert len(ids) == len(set(ids))
    assert len({item["pids"] for item in space["configurations"]}) >= 8
    assert all("seed" not in item["overrides"] for item in space["configurations"])


def test_checkpoint_slug_is_readable_and_excludes_seed():
    space = load_configuration_space()
    slug = checkpoint_slug(space.get("kairos_base"))
    assert slug.startswith("checkpoint_embedding_dim-16_hidden_dim-100")
    assert "learning_rate-5e-5" in slug
    assert "seed" not in slug


def test_production_source_never_imports_installed_pidsmaker():
    violations = []
    for path in ADAPTER.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                violations.extend(
                    (path, alias.name)
                    for alias in node.names
                    if alias.name == "pidsmaker" or alias.name.startswith("pidsmaker.")
                )
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "pidsmaker" or node.module.startswith("pidsmaker."):
                    violations.append((path, node.module))
    assert violations == []


def test_result_schema_forbids_privileged_metrics():
    schema = json.loads(
        (ADAPTER / "schemas" / "checkpoint_split_result_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["properties"]["privileged_metrics"]["type"] == "null"
    assert schema["properties"]["visibility"]["properties"]["labels_used"]["const"] is False


def test_excluded_upstream_subsets_are_not_vendored():
    assert not (ADAPTER / "upstream" / "triage").exists()
    assert not (ADAPTER / "upstream" / "tasks" / "triage.py").exists()
    assert not (ADAPTER / "upstream" / "tasks" / "evaluation.py").exists()
    assert not (ADAPTER / "upstream" / "detection" / "evaluation_methods").exists()
    assert not (
        ADAPTER
        / "upstream"
        / "preprocessing"
        / "transformation_methods"
        / "attack_generation"
        / "synthetic_attack_naive.py"
    ).exists()


def test_flash_inference_is_current_graph_only():
    flash = (
        ADAPTER
        / "upstream"
        / "featurization"
        / "feat_inference_methods"
        / "feat_inference_flash.py"
    ).read_text(encoding="utf-8")
    task = (ADAPTER / "upstream" / "tasks" / "feat_inference.py").read_text(
        encoding="utf-8"
    )
    assert "def infer_graph(" in flash
    assert "get_node2corpus" not in flash
    assert "feat_inference_flash.infer_graph" in task


def test_tgn_preprocessing_resets_native_split_state():
    source = (ADAPTER / "upstream" / "utils" / "data_utils.py").read_text(
        encoding="utf-8"
    )
    boundary = source.index("event_offset = 0")
    reset = source.index("neighbor_loader.reset_state()", boundary)
    loop_body = source.index("for data_list in dataset:", boundary)
    assert boundary < reset < loop_body


def test_training_preserves_unused_lazy_parameters():
    source = (ADAPTER / "training.py").read_text(encoding="utf-8")
    assert "UninitializedParameter" in source
    assert "UninitializedBuffer" in source
    assert "copy.deepcopy(value)" in source


def test_tgn_runtime_neighbors_are_not_checkpoint_state():
    source = (ADAPTER / "upstream" / "utils" / "data_utils.py").read_text(
        encoding="utf-8"
    )
    save_section = source[source.index("def save_model(") : source.index("def load_model(")]
    assert "neighbor_loader.pkl" not in save_section
    assert "memory.pkl" not in save_section


def test_remote_runner_uses_only_data_disk_for_generated_artifacts():
    source = (ADAPTER / "experiments" / "run_clearscope_e3.sh").read_text(
        encoding="utf-8"
    )
    assert "/root/autodl-tmp/apt-detection-agent/pidsmaker-output" in source
    assert "/root/autodl-tmp/apt-detection-agent/experiments-result" in source
    assert "RUN_ID=" in source
    assert "for candidate in +" not in source


def test_magic_inference_returns_reconstruction_scores():
    source = (
        ADAPTER / "upstream" / "objectives" / "reconstruct_masked_feat.py"
    ).read_text(encoding="utf-8")
    assert "torch.zeros((x.shape[0],)" not in source
    assert "self.loss_fn(x_rec, x_init, inference=inference)" in source


def test_word_embedding_model_paths_do_not_require_trailing_separator():
    root = ADAPTER / "upstream" / "featurization" / "feat_inference_methods"
    for filename in ("feat_inference_word2vec.py", "feat_inference_TRW.py"):
        source = (root / filename).read_text(encoding="utf-8")
        assert "cfg.featurization._model_dir +" not in source
        assert "import os" in source
        assert "os.path.join(" in source
