#!/usr/bin/env python3
"""Train or infer with the isolated causal PIDSMaker compatibility build.

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001..004, REQ-PIDS-004..005,
REQ-TOOL-001..005, REQ-ARTIFACT-001..003, REQ-WANDB-001,
REQ-REPRO-001..002.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pidsmaker_stage_runner as prefix


class CausalRunnerError(RuntimeError):
    pass


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("train", "infer"))
    parser.add_argument("source_config_id")
    parser.add_argument("dataset_id")
    parser.add_argument("--pidsmaker-root", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--checkpoint-hash")
    parser.add_argument("--override", action="append", default=[])
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--window-size-seconds", type=int, default=900)
    for split in ("train", "val", "test"):
        parser.add_argument(f"--{split}-date", required=True)
        parser.add_argument(f"--{split}-window-start-ns", type=int, required=True)
        parser.add_argument(f"--{split}-window-end-ns", type=int, required=True)
    return parser.parse_args(argv)


def validate(args: argparse.Namespace, environ: dict[str, str]) -> tuple[Path, Path, dict[str, object]]:
    if not prefix.SAFE_TOKEN.fullmatch(args.source_config_id):
        raise CausalRunnerError("unsafe source config")
    if not prefix.SAFE_TOKEN.fullmatch(args.dataset_id):
        raise CausalRunnerError("unsafe dataset")
    root = Path(args.pidsmaker_root).resolve()
    artifact_dir = Path(args.artifact_dir).resolve()
    allowed_text = environ.get("APT_PIDS_ARTIFACT_ROOT")
    if not allowed_text or artifact_dir.parent != Path(allowed_text).resolve():
        raise CausalRunnerError("artifact directory escaped approved root")
    if not artifact_dir.is_dir() or not (artifact_dir / "stage_summary.json").is_file():
        raise CausalRunnerError("causal runner requires completed prefix artifacts")
    identity = prefix.source_identity(root)
    if identity.get("schema_version") != "apt-pidsmaker-compat-v1":
        raise CausalRunnerError("training/inference requires an isolated compatibility build")
    if environ.get("WANDB_MODE") != "disabled":
        raise CausalRunnerError("WANDB_MODE=disabled is mandatory")
    missing = [name for name in prefix.REQUIRED_DATABASE_ENV if not environ.get(name)]
    if missing:
        raise CausalRunnerError("database environment is incomplete")
    prefix.validate_window_contract(args)
    for override in args.override:
        if not prefix.SAFE_OVERRIDE.fullmatch(override):
            raise CausalRunnerError("invalid override")
        key = override.split("=", 1)[0]
        if set(key.lower().split(".")) & prefix.FORBIDDEN_OVERRIDE_PARTS:
            raise CausalRunnerError("executor-owned override")
    if args.phase == "train" and args.checkpoint_hash is not None:
        raise CausalRunnerError("train does not accept a checkpoint hash")
    if args.phase == "infer" and not re.fullmatch(r"[0-9a-f]{64}", args.checkpoint_hash or ""):
        raise CausalRunnerError("inference requires a checkpoint hash")
    training_source = root / "pidsmaker" / "detection" / "training_methods" / "training_loop.py"
    if "import wandb" in training_source.read_text():
        raise CausalRunnerError("compatibility training path still imports W&B")
    return root, artifact_dir, identity


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise CausalRunnerError("artifact tree is empty")
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def load_cfg(args: argparse.Namespace, root: Path, artifact_dir: Path, environ: dict[str, str]):
    sys.path.insert(0, str(root))
    from pidsmaker.config import get_runtime_required_args, get_yml_cfg

    upstream = get_runtime_required_args(args=prefix.upstream_argv(args, artifact_dir, environ))
    cfg = get_yml_cfg(upstream)
    cfg.dataset.ground_truth_relative_path = []
    cfg.dataset.attack_to_time_window = []
    return cfg


def run_train(args: argparse.Namespace, cfg, root: Path, artifact_dir: Path, identity: dict[str, object]) -> dict[str, object]:
    from pidsmaker.config import set_task_to_done

    summary_path = artifact_dir / "training_stage_summary.json"
    manifest_path = artifact_dir / "checkpoint_manifest.json"
    if summary_path.exists() or manifest_path.exists():
        raise CausalRunnerError("training artifacts already exist")
    started = time.monotonic()
    module = prefix.load_stage_module(root, "training")
    best_validation_score = module.main(cfg)
    set_task_to_done(str(cfg.training._task_path))
    checkpoint_dir = Path(cfg.training._trained_models_dir) / "frozen_validation_checkpoint"
    required = (checkpoint_dir / "state_dict.pkl", checkpoint_dir / "training_metrics.json")
    if not all(path.is_file() for path in required):
        raise CausalRunnerError("training did not produce the frozen checkpoint contract")
    checkpoint_hash = tree_hash(checkpoint_dir)
    metrics = json.loads((checkpoint_dir / "training_metrics.json").read_text())
    if metrics.get("selection_split") != "validation" or metrics.get(
        "test_data_used_for_selection"
    ) is not False or metrics.get("wandb_used") is not False:
        raise CausalRunnerError("checkpoint training provenance is not causal/W&B-free")
    manifest = {
        "schema_version": "apt-pids-checkpoint-v1",
        "pidsmaker_commit": identity["upstream_commit"],
        "compatibility_patch_series_hash": identity["patch_series_hash"],
        "source_config_id": args.source_config_id,
        "dataset_id": args.dataset_id,
        "selection_split": "validation",
        "checkpoint_relative_path": checkpoint_dir.relative_to(artifact_dir).as_posix(),
        "checkpoint_hash": checkpoint_hash,
        "training_metrics_relative_path": required[1].relative_to(artifact_dir).as_posix(),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    summary = {
        "schema_version": "pidsmaker-causal-training-v1",
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "best_validation_score": float(best_validation_score),
        "checkpoint_hash": checkpoint_hash,
        "test_data_used_for_selection": False,
        "wandb_used": False,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def run_infer(args: argparse.Namespace, cfg, artifact_dir: Path, identity: dict[str, object]) -> dict[str, object]:
    from pidsmaker.detection.training_methods import inference_loop
    from pidsmaker.factory import build_model
    from pidsmaker.utils.data_utils import load_model, load_test_dataset
    from pidsmaker.utils.utils import get_device, set_seed

    summary_path = artifact_dir / "inference_stage_summary.json"
    if summary_path.exists():
        raise CausalRunnerError("inference summary already exists")
    manifest = json.loads((artifact_dir / "checkpoint_manifest.json").read_text())
    checkpoint_dir = artifact_dir / manifest["checkpoint_relative_path"]
    if (
        manifest.get("checkpoint_hash") != args.checkpoint_hash
        or tree_hash(checkpoint_dir) != args.checkpoint_hash
        or manifest.get("compatibility_patch_series_hash") != identity["patch_series_hash"]
    ):
        raise CausalRunnerError("checkpoint identity mismatch")
    test_loss_root = Path(cfg.training._edge_losses_dir) / "test"
    if test_loss_root.exists():
        raise CausalRunnerError("test score artifacts already exist")

    started = time.monotonic()
    set_seed(cfg)
    device = get_device(cfg)
    test_data, max_node_num = load_test_dataset(cfg, device)
    if not test_data or not test_data[0]:
        raise CausalRunnerError("test split is empty")
    model = build_model(
        data_sample=test_data[0][0], device=device, cfg=cfg, max_node_num=max_node_num
    )
    model = load_model(model, str(checkpoint_dir), cfg, map_location=device)
    stats = inference_loop.main(
        cfg=cfg,
        model=model,
        val_data=(),
        test_data=test_data,
        epoch=manifest.get("best_epoch", "frozen"),
        split="test",
        logging=False,
    )
    score_files = tuple(sorted(test_loss_root.rglob("*.csv")))
    if not score_files:
        raise CausalRunnerError("frozen inference produced no raw score artifact")
    forbidden_columns = {"y", "label", "ground_truth", "campaign_id", "tp", "fp", "fn"}
    for path in score_files:
        with path.open(newline="") as stream:
            columns = set(next(csv.reader(stream)))
        if columns & forbidden_columns or "loss" not in columns:
            raise CausalRunnerError("raw score schema contains labels or lacks anomaly loss")

    def finite_stat(name: str) -> float:
        value = float(stats[name])
        if not math.isfinite(value):
            raise CausalRunnerError(f"non-finite inference statistic: {name}")
        return value

    summary = {
        "schema_version": "pidsmaker-frozen-inference-v1",
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "checkpoint_hash": args.checkpoint_hash,
        "selection_split": "frozen_validation_checkpoint",
        "inference_split": "test",
        "test_labels_loaded": False,
        "anomaly_score_mean": finite_stat("test_loss"),
        "peak_inference_cpu_memory_gib": finite_stat("peak_inference_cpu_memory"),
        "peak_inference_gpu_memory_gib": finite_stat("peak_inference_gpu_memory"),
        "time_per_batch_seconds": finite_stat("time_per_batch_inference"),
        "raw_score_artifacts": [
            path.relative_to(artifact_dir).as_posix() for path in score_files
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def run(args: argparse.Namespace, environ: dict[str, str] | None = None) -> dict[str, object]:
    environ = dict(os.environ if environ is None else environ)
    root, artifact_dir, identity = validate(args, environ)
    cfg = load_cfg(args, root, artifact_dir, environ)
    if args.phase == "train":
        return run_train(args, cfg, root, artifact_dir, identity)
    return run_infer(args, cfg, artifact_dir, identity)


def main() -> None:
    try:
        summary = run(parse_args())
    except (CausalRunnerError, prefix.StageRunnerError, KeyError, FileNotFoundError) as exc:
        print(f"causal runner rejected request: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
