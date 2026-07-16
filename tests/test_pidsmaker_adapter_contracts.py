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


def test_rcaid_early_pruning_matches_legacy_post_pruning():
    import networkx as nx

    from pidsmaker_adapter.upstream.preprocessing.transformation_methods import (
        transformation_rcaid_pseudo_graph as rcaid,
    )

    graph = nx.DiGraph()
    graph.add_edges_from([("n0", "n1"), ("n1", "n2"), ("n2", "n3")])
    for index, (source, target) in enumerate(graph.edges()):
        graph[source][target]["time"] = index
    roots = rcaid.identify_root_nodes(graph)

    legacy = rcaid.create_pseudo_graph(graph, roots)
    legacy = rcaid.prune_pseudo_roots(legacy, graph, 0.5)
    optimized = rcaid.create_pseudo_graph(graph, roots, prune_threshold=0.5)
    optimized = rcaid.prune_pseudo_roots(optimized, graph, 0.5)

    assert set(optimized.nodes()) == set(legacy.nodes())
    assert set(optimized.edges()) == set(legacy.edges())


def test_rcaid_doc2vec_corpus_streams_transformed_graphs():
    source = (
        ADAPTER / "upstream" / "featurization" / "featurization_utils.py"
    ).read_text(encoding="utf-8")
    function = source[source.index("def get_corpus_using_neighbors_features(") :]
    assert "graph_list = [torch.load" not in function
    assert "for path in log_tqdm(sorted_paths" in function
    assert "G = torch.load(path)" in function
    assert "del G" in function


def test_rcaid_preserves_non_persistent_batching(tmp_path):
    from pidsmaker_adapter.configuration import (
        load_configuration_space,
        resolve_runtime_config,
    )

    configuration = load_configuration_space()
    cfg = resolve_runtime_config(
        configuration.get("rcaid_base"),
        configuration,
        tmp_path,
        {
            "host": "localhost",
            "port": "5432",
            "user": "postgres",
            "password": "",
            "name": "clearscope_e3",
        },
    )

    assert cfg.batching.save_on_disk is False

    flash = resolve_runtime_config(
        configuration.get("flash_base"),
        configuration,
        tmp_path,
        {
            "host": "localhost",
            "port": "5432",
            "user": "postgres",
            "password": "",
            "name": "clearscope_e3",
        },
    )
    assert flash.batching.save_on_disk is True


def test_full_dataset_collation_is_reserved_for_tgn_neighbors():
    source = (ADAPTER / "upstream" / "utils" / "data_utils.py").read_text(
        encoding="utf-8"
    )
    assert 'full_data = get_full_data(datasets) if use_tgn_neighbors else None' in source


def test_stage_cache_detects_partial_directory_artifacts(tmp_path):
    from pidsmaker_adapter.artifacts import (
        stage_complete,
        write_stage_manifest,
    )

    stage = tmp_path / "stage"
    artifact = stage / "graphs"
    artifact.mkdir(parents=True)
    (artifact / "one.pt").write_bytes(b"one")
    (artifact / "two.pt").write_bytes(b"two")
    signature = {"digest": "example"}
    write_stage_manifest(
        stage,
        signature,
        status="complete",
        started_at="2026-07-16T00:00:00+00:00",
        runtime_seconds=1.0,
        artifact_paths=[str(artifact)],
    )

    assert stage_complete(stage, signature)
    (artifact / "two.pt").unlink()
    assert not stage_complete(stage, signature)


def test_deep_stage_hit_covers_missing_earlier_cache(tmp_path):
    from types import SimpleNamespace

    from pidsmaker_adapter.artifacts import STAGES, write_stage_manifest
    from pidsmaker_adapter.pipeline import _cache_reuse_frontier

    cfg = SimpleNamespace(
        **{
            stage: SimpleNamespace(_task_path=str(tmp_path / stage))
            for stage in STAGES
        }
    )
    signatures = {stage: {"digest": stage} for stage in STAGES}
    feature_output = tmp_path / "feat_inference" / "edge_embeds"
    feature_output.mkdir(parents=True)
    (feature_output / "graph.pt").write_bytes(b"features")
    write_stage_manifest(
        tmp_path / "feat_inference",
        signatures["feat_inference"],
        status="complete",
        started_at="2026-07-16T00:00:00+00:00",
        runtime_seconds=1.0,
        artifact_paths=[str(feature_output)],
    )

    assert _cache_reuse_frontier(cfg, signatures) == "feat_inference"


def test_batch_cache_ignores_optimizer_only_changes(tmp_path):
    from pidsmaker_adapter.artifacts import stage_signatures
    from pidsmaker_adapter.configuration import resolve_runtime_config

    configuration = load_configuration_space()
    database = {
        "host": "localhost",
        "port": "5432",
        "user": "postgres",
        "password": "",
        "name": "clearscope_e3",
    }
    cfg = resolve_runtime_config(
        configuration.get("flash_base"), configuration, tmp_path, database
    )
    before = stage_signatures(cfg, "node_classification")
    cfg.training.lr *= 0.5
    cfg.training.num_epochs += 1
    after = stage_signatures(cfg, "node_classification")

    assert before["batching"]["digest"] == after["batching"]["digest"]
    assert before["training"]["digest"] != after["training"]["digest"]


def test_complete_published_checkpoint_can_bypass_stage_caches(tmp_path):
    from pidsmaker_adapter.artifacts import file_sha256
    from pidsmaker_adapter.pipeline import _published_checkpoint_manifest

    configuration = load_configuration_space()
    legal = configuration.get("flash_base")
    checkpoint_id = f"{legal.pids}_{checkpoint_slug(legal).removeprefix('checkpoint_')}"
    checkpoint = tmp_path / checkpoint_slug(legal)
    (checkpoint / "model").mkdir(parents=True)
    state = checkpoint / "model" / "state_dict.pkl"
    state.write_bytes(b"frozen-model")
    (checkpoint / "resolved_config.yaml").write_text(
        "scoring: node_classification\n", encoding="utf-8"
    )
    (checkpoint / "thresholds.json").write_text(
        json.dumps({"options": []}), encoding="utf-8"
    )
    for split in ("train", "val", "test"):
        (checkpoint / f"{split}_result.json").write_text(
            json.dumps(
                {
                    "schema_version": "checkpoint_split_result_v1",
                    "checkpoint_id": checkpoint_id,
                    "split": split,
                    "privileged_metrics": None,
                    "visibility": {"labels_used": False},
                }
            ),
            encoding="utf-8",
        )
    manifest = {
        "schema_version": "checkpoint_manifest_v1",
        "checkpoint_id": checkpoint_id,
        "configuration_id": legal.config_id,
        "pids": legal.pids,
        "dataset": configuration.dataset,
        "configuration_space_version": configuration.schema_version,
        "checkpoint_hash": file_sha256(state),
        "agent_initialization_artifacts": [],
    }
    (checkpoint / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    assert _published_checkpoint_manifest(
        checkpoint,
        checkpoint_id=checkpoint_id,
        legal=legal,
        space=configuration,
    ) == manifest
    state.write_bytes(b"tampered")
    assert (
        _published_checkpoint_manifest(
            checkpoint,
            checkpoint_id=checkpoint_id,
            legal=legal,
            space=configuration,
        )
        is None
    )
