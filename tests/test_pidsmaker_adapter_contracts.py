import ast
import json
import re
from functools import lru_cache
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
    ids = [item.config_id for item in load_configuration_space().configurations]
    assert len(ids) == len(set(ids))
    assert len(ids) == space["expected_configuration_count"] == 311
    assert {item.pids for item in load_configuration_space().configurations} == {
        "flash",
        "kairos",
        "magic",
        "nodlink",
        "orthrus",
        "rcaid",
        "threatrace",
        "velox",
    }
    assert all("seed" not in item.overrides for item in load_configuration_space().configurations)


def test_every_numeric_decision_field_has_three_to_five_values():
    raw = yaml.safe_load(
        (ADAPTER / "config" / "configuration_space_v1.yaml").read_text(encoding="utf-8")
    )
    generated_count = 0
    for pids, spec in raw["pids_spaces"].items():
        assert spec["coverage"] == "full_factorial"
        cardinality = 1
        for field, parameter in spec.get("parameters", {}).items():
            values = parameter["values"]
            cardinality *= len(values)
            if all(isinstance(value, (int, float)) for value in values):
                assert 3 <= len(set(values)) <= 5, (pids, field, values)
        for unit, parameter in spec.get("coupled_parameters", {}).items():
            options = parameter["values"]
            cardinality *= len(options)
            by_field = {}
            for option in options:
                for field, value in option.items():
                    if isinstance(value, (int, float)):
                        by_field.setdefault(field, set()).add(value)
            assert all(3 <= len(values) <= 5 for values in by_field.values()), (
                pids,
                unit,
                by_field,
            )
        generated_count += cardinality
    assert generated_count == raw["expected_configuration_count"]


def test_agent_selection_tree_uses_real_fields_not_coupled_option_ids():
    tree = load_configuration_space().selection_tree()
    assert tree["pids"]["values"] == [
        "flash", "kairos", "magic", "nodlink", "orthrus", "rcaid", "threatrace", "velox"
    ]
    for branch in tree["pids"]["branches"].values():
        for option in branch["train"]["coupled_parameters"]["model_capacity"]["values"]:
            assert "id" not in option
            assert "overrides" not in option
            assert all("." in field for field in option)


def test_every_hyperparameter_value_is_backed_by_declared_upstream_yaml():
    @lru_cache(maxsize=None)
    def source_values(relative_path, dotted):
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        if relative_path.endswith(".md"):
            documents = [
                yaml.safe_load(block)
                for block in re.findall(r"```\s*yaml[^\n]*\n(.*?)```", source, re.DOTALL)
            ]
        else:
            documents = [yaml.safe_load(source)]
        values = set()
        for document in documents:
            if not isinstance(document, dict):
                continue
            current = document
            for part in dotted.split("."):
                current = current.get(part) if isinstance(current, dict) else None
            if current is not None and not isinstance(current, (dict, list)):
                values.add(current)
            parameter = document.get("parameters", {}).get(dotted, {})
            values.update(parameter.get("values", []))
        return values

    for item in load_configuration_space().configurations:
        declared_paths = list(item.source_files)
        assert declared_paths
        for path in declared_paths:
            assert (ROOT / path).is_file()
        values_to_check = {**item.overrides, **item.decision_values}
        for dotted, value in values_to_check.items():
            allowed = set().union(
                *(source_values(path, dotted) for path in declared_paths)
            )
            if dotted == "training.node_out_dim" and -1 in allowed:
                allowed.add(values_to_check["training.node_hid_dim"])
            assert value in allowed, (item.config_id, dotted, value, allowed)


def test_checkpoint_slug_is_readable_and_excludes_seed():
    space = load_configuration_space()
    slug = checkpoint_slug(space.get("kairos_base"))
    assert slug.startswith("checkpoint_embedding_dim-16_hidden_dim-100")
    assert "learning_rate-5e-5" in slug
    assert "seed" not in slug

    non_default = next(
        item
        for item in space.configurations
        if item.overrides.get("featurization.used_method") == "fasttext"
    )
    assert "featurization-fasttext" in checkpoint_slug(non_default)


def test_existing_named_configurations_keep_their_checkpoint_paths():
    space = load_configuration_space()
    expected = {
        "flash_base": "checkpoint_embedding_dim-30_featurization_epochs-10_hidden_dim-30_output_dim-3_learning_rate-0.01_weight_decay-5e-4_training_epochs-12",
        "kairos_base": "checkpoint_embedding_dim-16_hidden_dim-100_output_dim-100_learning_rate-5e-5_weight_decay-0.01_training_epochs-12",
        "rcaid_compact": "checkpoint_embedding_dim-32_featurization_epochs-5_hidden_dim-64_output_dim-3_learning_rate-0.001_weight_decay-1e-4_training_epochs-12",
    }
    for config_id, slug in expected.items():
        assert checkpoint_slug(space.get(config_id)) == slug


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


def test_adapter_has_no_import_time_nltk_download():
    violations = []
    for path in ADAPTER.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "nltk.download(" in source:
            violations.append(path)
    assert violations == []


def test_result_schema_forbids_privileged_metrics():
    schema = json.loads(
        (ADAPTER / "schemas" / "checkpoint_split_result_v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["properties"]["privileged_metrics"]["type"] == "null"
    assert schema["properties"]["visibility"]["properties"]["labels_used"]["const"] is False


def test_threshold_tree_is_validation_derived_and_magic_is_selectable():
    configuration = load_configuration_space()
    assert set(configuration.threshold_spaces) == {
        "flash", "kairos", "magic", "nodlink", "orthrus", "rcaid", "threatrace", "velox"
    }
    assert all(
        {option["method"] for option in threshold_space["options"]}
        == {"validation_quantile", "max_val_loss", "mean_val_loss"}
        and {
            option["value"]
            for option in threshold_space["options"]
            if option["method"] == "validation_quantile"
        } == {0.90, 0.95, 0.99}
        for threshold_space in configuration.threshold_spaces.values()
    )
    source = (ADAPTER / "config" / "configuration_space_v1.yaml").read_text(
        encoding="utf-8"
    )
    assert "values: [0.90, 0.95, 0.99]  # PIDSMaker default: 0.90" in source
    assert "values: [validation_quantile, max_val_loss, mean_val_loss]  # PIDSMaker default: max_val_loss" in source
    assert "\n        default:" not in source


def test_special_threshold_score_channels_gate_incorrect_predictions():
    from types import SimpleNamespace

    import torch

    from pidsmaker_adapter.inference import _pids_node_scores

    batch = SimpleNamespace(node_type=torch.eye(3))
    result = {
        "out": torch.tensor(
            [[4.0, 1.0, 0.0], [4.0, 3.0, 1.0], [1.0, 2.0, 4.0]]
        )
    }
    objective = torch.ones(3)
    for score_channel in ("flash_confidence", "threatrace_ratio"):
        scores = _pids_node_scores(
            result=result,
            batch=batch,
            objective_loss=objective,
            score_channel=score_channel,
        )
        assert scores.shape == objective.shape
        assert scores[0] > 0
        assert scores[1] == 0
        assert scores[2] > 0


def test_threshold_resolution_produces_validation_quantile_artifact(tmp_path):
    from pidsmaker_adapter.inference import calibrate_thresholds

    output = tmp_path / "thresholds.json"
    resolved = calibrate_thresholds(
        [1.0, 2.0, 3.0, 100.0],
        ({"method": "validation_quantile", "value": 0.9},),
        output,
        pids="nodlink",
        scoring="direct_node_loss",
        score_channel="objective_loss",
        threshold_space_version="pids_tree_quantile_v1",
    )
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert set(resolved) == {"validation_quantile_q0.9"}
    assert abs(resolved["validation_quantile_q0.9"] - 70.9) < 1e-9
    assert artifact["options"][0]["method"] == "validation_quantile"
    assert artifact["options"][0]["value"] == 0.9
    assert artifact["score_channel"] == "objective_loss"
    assert artifact["options"][0]["resolved_value"] == resolved["validation_quantile_q0.9"]


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


def test_all_systems_persist_reusable_batching(tmp_path):
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

    assert cfg.batching.save_on_disk is True


def test_alternate_featurizers_receive_upstream_method_defaults(tmp_path):
    from pidsmaker_adapter.configuration import (
        load_configuration_space,
        resolve_runtime_config,
    )

    configuration = load_configuration_space()
    database = {"host": "localhost", "user": "pids", "password": "unused", "port": "5432"}
    for method, required_field in (("fasttext", "num_workers"), ("word2vec", "num_workers")):
        legal = next(
            item
            for item in configuration.configurations
            if item.pids == "rcaid"
            and item.overrides.get("featurization.used_method") == method
        )
        cfg = resolve_runtime_config(legal, configuration, tmp_path, database)
        assert getattr(getattr(cfg.featurization, method), required_field) == 1

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


def test_low_disk_guard_is_stage_reuse_aware():
    source = (ADAPTER / "pipeline.py").read_text(encoding="utf-8")
    assert 'low_write_reuse = frontier == "batching"' in source
    assert "minimum_free_gib = min(minimum_free_gib, 10)" in source


def test_resource_usage_has_stable_scope_and_honest_historical_nulls():
    from pidsmaker_adapter.resources import historical_partial_resource_usage

    usage = historical_partial_resource_usage(
        {
            "train": {
                "resource": {
                    "peak_process_rss_gib": 4.0,
                    "peak_cuda_allocated_gib": 2.0,
                }
            },
            "val": {
                "resource": {
                    "peak_process_rss_gib": 5.0,
                    "peak_cuda_allocated_gib": 1.0,
                }
            },
        }
    )

    assert usage["collection_status"] == "historical_partial"
    assert usage["scope"] == "construction_through_train_and_validation"
    assert usage["cpu"]["peak_process_percent"] is None
    assert usage["memory"]["peak_process_rss_gib"] == 5.0
    assert usage["gpu"]["observed_split_peak_allocated_gib"] == 2.0


def test_resource_artifact_uses_fixed_checkpoint_filename():
    pipeline = (ADAPTER / "pipeline.py").read_text(encoding="utf-8")
    readme = (ADAPTER / "README.md").read_text(encoding="utf-8")
    assert 'checkpoint_dir / "train_val_resource_usage.json"' in pipeline
    assert "train_val_resource_usage.json" in readme


def test_published_matrix_reclaims_only_consumed_duplicate_stages():
    pipeline = (ADAPTER / "pipeline.py").read_text(encoding="utf-8")
    assert "shutil.rmtree(Path(cfg.feat_inference._task_path), ignore_errors=True)" in pipeline
    assert "shutil.rmtree(training_path, ignore_errors=True)" in pipeline
    assert "shutil.rmtree(Path(cfg.featurization._task_path)" not in pipeline
    assert "shutil.rmtree(Path(cfg.transformation._task_path)" not in pipeline


def test_non_tgn_batching_avoids_full_edge_message_copies():
    source = (ADAPTER / "upstream" / "utils" / "data_utils.py").read_text(
        encoding="utf-8"
    )
    assert "x_src = x_src[0] if len(x_src) == 1" in source
    assert 'needs_msg = "msg" in edge_features or use_tgn_memory' in source
    assert "if needs_msg:" in source
    assert "os.POSIX_FADV_DONTNEED" in source
    assert 'prune_edge_inputs = "rcaid_gat" in cfg.training.encoder.used_methods' in source
    assert 'reindex_device = torch.device("cpu") if prune_edge_inputs else device' in source
    assert 'if key in batch:' in source


def test_model_accepts_pruned_rcaid_edge_inputs():
    source = (ADAPTER / "upstream" / "model.py").read_text(encoding="utf-8")
    for field in ("x_src", "x_dst", "msg", "node_type_src", "node_type_dst"):
        assert f'getattr(batch, "{field}", None)' in source


def test_chunked_rcaid_gat_matches_native_forward_and_gradient():
    import torch
    from torch_geometric.nn import GATConv

    from pidsmaker_adapter.upstream.encoders.rcaid_encoder import (
        _memory_efficient_gat,
    )

    torch.manual_seed(42)
    conv = GATConv(5, 4, heads=3, concat=True, dropout=0.0)
    edge_index = torch.tensor(
        [[0, 1, 2, 2, 3, 4, 4], [1, 2, 0, 3, 1, 2, 4]], dtype=torch.long
    )
    native_x = torch.randn(5, 5, requires_grad=True)
    chunked_x = native_x.detach().clone().requires_grad_(True)
    native = conv(native_x, edge_index)
    chunked = _memory_efficient_gat(conv, chunked_x, edge_index, chunk_size=2)

    assert torch.allclose(native, chunked, atol=1e-6, rtol=1e-6)
    native.square().sum().backward()
    native_gradient = native_x.grad.detach().clone()
    conv.zero_grad(set_to_none=True)
    chunked.square().sum().backward()
    assert torch.allclose(native_gradient, chunked_x.grad, atol=1e-6, rtol=1e-6)
