"""Finite configuration-space loading and upstream-compatible config resolution."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ADAPTER_ROOT = Path(__file__).resolve().parent
CONFIG_ROOT = ADAPTER_ROOT / "config"
DEFAULT_SPACE = CONFIG_ROOT / "configuration_space_v1.yaml"
ALLOWED_DATASET = "CLEARSCOPE_E3"
ALLOWED_SCORING = {"direct_node_loss", "max_incident_edge_loss"}


@dataclass(frozen=True)
class LegalConfiguration:
    config_id: str
    pids: str
    base_model: str
    scoring: str
    overrides: dict[str, Any]


@dataclass(frozen=True)
class ConfigurationSpace:
    schema_version: str
    dataset: str
    seed: int
    time_window_minutes: int
    threshold_quantiles: tuple[float, ...]
    configurations: tuple[LegalConfiguration, ...]

    def get(self, config_id: str) -> LegalConfiguration:
        matches = [item for item in self.configurations if item.config_id == config_id]
        if len(matches) != 1:
            raise ValueError(f"Unknown configuration {config_id!r}")
        return matches[0]


def load_configuration_space(path: Path = DEFAULT_SPACE) -> ConfigurationSpace:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "configuration_space_v1":
        raise ValueError("Unsupported configuration-space schema")
    if raw.get("dataset") != ALLOWED_DATASET:
        raise ValueError(f"Only {ALLOWED_DATASET} is frozen in configuration_space_v1")
    frozen = raw.get("frozen", {})
    seed = frozen.get("reproducibility", {}).get("seed")
    window = frozen.get("construction", {}).get("time_window_size_minutes")
    quantiles = tuple(frozen.get("threshold", {}).get("quantiles", ()))
    if seed != 42 or window != 15:
        raise ValueError("Detector seed=42 and construction window=15 minutes are mandatory")
    if not quantiles or any(not 0.0 < float(q) < 1.0 for q in quantiles):
        raise ValueError("Threshold quantiles must be a non-empty finite set in (0, 1)")

    items: list[LegalConfiguration] = []
    seen: set[str] = set()
    for item in raw.get("configurations", ()):
        config_id = item.get("id")
        if not isinstance(config_id, str) or not config_id or config_id in seen:
            raise ValueError(f"Invalid or duplicate configuration id: {config_id!r}")
        seen.add(config_id)
        scoring = item.get("scoring")
        if scoring not in ALLOWED_SCORING:
            raise ValueError(f"Illegal scoring rule for {config_id}: {scoring!r}")
        overrides = item.get("overrides")
        if not isinstance(overrides, dict) or not overrides:
            raise ValueError(f"{config_id} must declare a finite override tuple")
        items.append(
            LegalConfiguration(
                config_id=config_id,
                pids=str(item["pids"]),
                base_model=str(item["base_model"]),
                scoring=scoring,
                overrides=overrides,
            )
        )
    if not items:
        raise ValueError("The configuration space cannot be empty")
    return ConfigurationSpace(
        schema_version=raw["schema_version"],
        dataset=raw["dataset"],
        seed=seed,
        time_window_minutes=window,
        threshold_quantiles=tuple(float(q) for q in quantiles),
        configurations=tuple(items),
    )


def _runtime_args(model: str, dataset: str, artifact_root: Path, database: dict[str, str]):
    return argparse.Namespace(
        model=model,
        dataset=dataset,
        force_restart="",
        restart_from_scratch=False,
        wandb=False,
        project="APTDetectionAgent",
        exp="",
        tags="",
        cpu=False,
        experiment="none",
        tuning_mode="none",
        tuned=False,
        tuning_file_path="",
        database_host=database["host"],
        database_user=database["user"],
        database_password=database["password"],
        database_port=str(database["port"]),
        sweep_id="",
        artifact_dir=str(artifact_root),
        test_mode=False,
        show_attack=0,
        gt_type="orthrus",
        plot_gt=False,
    )


def _set_path(cfg: Any, dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    current = cfg
    for part in parts[:-1]:
        if not hasattr(current, part):
            raise ValueError(f"Unknown configuration field {dotted!r}")
        current = getattr(current, part)
    leaf = parts[-1]
    if not hasattr(current, leaf):
        raise ValueError(f"Unknown configuration field {dotted!r}")
    old = getattr(current, leaf)
    if old is not None and isinstance(old, bool) != isinstance(value, bool):
        expected = type(old)
        if not isinstance(value, expected):
            raise TypeError(f"{dotted} expects {expected.__name__}, got {type(value).__name__}")
    setattr(current, leaf, value)


def resolve_runtime_config(
    legal: LegalConfiguration,
    space: ConfigurationSpace,
    artifact_root: Path,
    database: dict[str, str],
):
    from pidsmaker_adapter.upstream.config.config import EXPERIMENTS_CONFIG
    from pidsmaker_adapter.upstream.config.pipeline import (
        check_edge_cases,
        get_default_cfg,
        merge_cfg_and_check_syntax,
        set_shortcut_variables,
    )

    args = _runtime_args(legal.base_model, space.dataset, artifact_root, database)
    cfg = get_default_cfg(args)
    merge_cfg_and_check_syntax(cfg, CONFIG_ROOT / f"{legal.base_model}.yml")
    merge_cfg_and_check_syntax(
        cfg,
        CONFIG_ROOT / "experiments" / "uncertainty" / "none.yml",
        syntax_check=EXPERIMENTS_CONFIG,
    )
    for dotted, value in legal.overrides.items():
        _set_path(cfg, dotted, value)

    cfg.training.seed = space.seed
    cfg.training.deterministic = False
    cfg.construction.time_window_size = float(space.time_window_minutes)
    cfg.construction.mimicry_edge_num = 0
    cfg.transformation.used_methods = str(cfg.transformation.used_methods)
    if "synthetic" in cfg.transformation.used_methods:
        raise ValueError("Synthetic attacks are excluded")
    if getattr(cfg.featurization, "training_split", None) not in (None, "train"):
        cfg.featurization.training_split = "train"
    # R-CAID's full edge-embedding corpus is too large to duplicate in the
    # persistent batching cache. Other supported models use the cache so that
    # train/validation/test publication can reuse the same preprocessing.
    cfg.batching.save_on_disk = legal.base_model != "rcaid"
    cfg.evaluation.used_method = "node_evaluation"
    cfg.evaluation.node_evaluation.use_kmeans = False
    cfg.training.decoder.use_few_shot = False
    cfg._is_running_mc_dropout = False
    set_shortcut_variables(cfg)
    check_edge_cases(cfg)
    if not math.isclose(float(cfg.construction.time_window_size), 15.0):
        raise ValueError("Construction window must remain 15 minutes")
    return cfg


def format_number(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == 0:
            return "0"
        if abs(value) < 0.001 or abs(value) >= 10000:
            mantissa, exponent = f"{value:.8e}".split("e")
            mantissa = mantissa.rstrip("0").rstrip(".")
            return f"{mantissa}e{int(exponent)}"
        return f"{value:.8f}".rstrip("0").rstrip(".")
    return str(value).lower().replace("_", "-")


def checkpoint_slug(legal: LegalConfiguration) -> str:
    aliases = {
        "featurization.emb_dim": "embedding_dim",
        "featurization.epochs": "featurization_epochs",
        "training.node_hid_dim": "hidden_dim",
        "training.node_out_dim": "output_dim",
        "training.lr": "learning_rate",
        "training.weight_decay": "weight_decay",
        "training.num_epochs": "training_epochs",
    }
    ordered = [
        key
        for key in aliases
        if key in legal.overrides
    ]
    tokens = [f"{aliases[key]}-{format_number(legal.overrides[key])}" for key in ordered]
    return "checkpoint_" + "_".join(tokens)
