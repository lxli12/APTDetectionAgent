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
