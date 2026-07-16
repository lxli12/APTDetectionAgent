"""Finite configuration-space loading and upstream-compatible config resolution."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import yaml

ADAPTER_ROOT = Path(__file__).resolve().parent
CONFIG_ROOT = ADAPTER_ROOT / "config"
DEFAULT_SPACE = CONFIG_ROOT / "configuration_space_v1.yaml"
ALLOWED_DATASET = "CLEARSCOPE_E3"
ALLOWED_SCORING = {"direct_node_loss", "max_incident_edge_loss"}
ALLOWED_THRESHOLD_METHODS = {
    "validation_quantile",
    "max_val_loss",
    "mean_val_loss",
}
ALLOWED_SCORE_CHANNELS = {
    "objective_loss",
    "flash_confidence",
    "threatrace_ratio",
}


@dataclass(frozen=True)
class LegalConfiguration:
    config_id: str
    pids: str
    base_model: str
    scoring: str
    score_channel: str
    overrides: dict[str, Any]
    decision_values: dict[str, Any]
    source_files: tuple[str, ...]


@dataclass(frozen=True)
class ConfigurationSpace:
    schema_version: str
    dataset: str
    seed: int
    time_window_minutes: int
    threshold_space_version: str
    threshold_spaces: dict[str, dict[str, Any]]
    configurations: tuple[LegalConfiguration, ...]
    decision_spaces: dict[str, Any]

    def get(self, config_id: str) -> LegalConfiguration:
        matches = [item for item in self.configurations if item.config_id == config_id]
        if len(matches) != 1:
            raise ValueError(f"Unknown configuration {config_id!r}")
        return matches[0]

    def threshold_options(self, pids: str) -> tuple[dict[str, Any], ...]:
        try:
            return tuple(self.threshold_spaces[pids]["options"])
        except KeyError as exc:
            raise ValueError(f"No threshold space declared for PIDS {pids!r}") from exc

    def selection_tree(self) -> dict[str, Any]:
        """Return the compact conditional tree exposed to the Agent/Harness."""
        branches: dict[str, Any] = {}
        for pids, spec in self.decision_spaces.items():
            branches[pids] = {
                "train": {
                    "coupled_parameters": spec.get("coupled_parameters", {}),
                    "parameters": spec.get("parameters", {}),
                },
                "threshold": spec["threshold"],
                "constraints": {"membership": "reachable_prebuilt_leaf_only"},
            }
        return {
            "pids": {
                "values": list(branches),
                "branches": branches,
            }
        }

def _source_files(
    source_keys: list[str], source_sets: dict[str, Any], config_id: str
) -> tuple[str, ...]:
    if not source_keys:
        raise ValueError(f"{config_id} must declare hyperparameter source keys")
    source_files: list[str] = []
    for source_key in source_keys:
        paths = source_sets.get(source_key)
        if not isinstance(paths, list) or not paths:
            raise ValueError(f"Unknown hyperparameter source {source_key!r}")
        for source_path in paths:
            if not (
                isinstance(source_path, str)
                and source_path.startswith("PIDSMaker/")
                and source_path.endswith((".yml", ".yaml", ".md"))
            ):
                raise ValueError(f"Invalid hyperparameter source path {source_path!r}")
            if source_path not in source_files:
                source_files.append(source_path)
    return tuple(source_files)


def _validate_numeric_domain(name: str, values: list[Any]) -> None:
    numeric = [
        value
        for value in values
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    if numeric and len(numeric) == len(values) and not 3 <= len(set(numeric)) <= 5:
        raise ValueError(f"Numeric decision field {name} must expose 3-5 distinct values")


def _coupled_marker(overrides: dict[str, Any]) -> str:
    labels = {
        "featurization.emb_dim": "emb",
        "training.node_hid_dim": "hid",
        # node_out_dim normally mirrors node_hid_dim and is intentionally not
        # repeated in the readable internal marker.
        "training.node_out_dim": "out",
    }
    fields = [field for field in overrides if field != "training.node_out_dim"]
    if not fields:
        fields = list(overrides)
    return "-".join(
        f"{labels.get(field, field.replace('.', '-'))}{format_number(overrides[field])}"
        for field in fields
    )


def _parse_threshold_spaces(raw_spaces: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for pids, spec in raw_spaces.items():
        threshold = spec.get("threshold")
        if not isinstance(threshold, dict):
            raise ValueError(f"{pids} must declare its threshold branch")
        method_spec = threshold.get("method")
        value_spec = threshold.get("value")
        if not isinstance(method_spec, dict) or not isinstance(value_spec, dict):
            raise ValueError(f"Invalid threshold branch for {pids}")
        methods = method_spec.get("values")
        if (
            not isinstance(methods, list)
            or set(methods) != ALLOWED_THRESHOLD_METHODS
        ):
            raise ValueError(f"Invalid threshold methods for {pids}")
        if value_spec.get("when") != {"method": "validation_quantile"}:
            raise ValueError(f"{pids}.threshold.value must be conditional on validation_quantile")
        values = value_spec.get("values")
        if not isinstance(values, list) or not values:
            raise ValueError(f"{pids} must declare threshold.value.values")
        _validate_numeric_domain(f"{pids}.threshold.value", values)
        normalized = [
            {"method": "validation_quantile", "value": float(value)}
            for value in values
        ]
        normalized.extend({"method": method} for method in methods if method != "validation_quantile")
        if len({tuple(option.items()) for option in normalized}) != len(normalized):
            raise ValueError(f"Duplicate threshold options for {pids}")
        result[pids] = {"options": tuple(normalized)}
    return result


def _expand_pids_spaces(
    raw_spaces: dict[str, Any], source_sets: dict[str, Any]
) -> list[LegalConfiguration]:
    items: list[LegalConfiguration] = []
    seen_ids: set[str] = set()
    for pids, spec in raw_spaces.items():
        if spec.get("coverage") != "full_factorial":
            raise ValueError(f"{pids} must use full_factorial coverage")
        scoring = spec.get("scoring")
        if scoring not in ALLOWED_SCORING:
            raise ValueError(f"Illegal scoring rule for {pids}: {scoring!r}")
        score_channel = spec.get("score_channel")
        if score_channel not in ALLOWED_SCORE_CHANNELS:
            raise ValueError(f"Illegal score channel for {pids}: {score_channel!r}")
        fixed = dict(spec.get("fixed_overrides", {}))
        base_values = dict(spec.get("base_values", {}))
        dimensions: list[tuple[str, list[dict[str, Any]]]] = []

        for unit_name, unit in spec.get("coupled_parameters", {}).items():
            options = unit.get("values")
            if not isinstance(options, list) or not options:
                raise ValueError(f"{pids}.{unit_name} must declare values")
            normalized: list[dict[str, Any]] = []
            field_values: dict[str, list[Any]] = {}
            for option in options:
                if not isinstance(option, dict) or not option:
                    raise ValueError(f"Invalid coupled option in {pids}.{unit_name}")
                overrides = dict(option)
                for field, value in overrides.items():
                    field_values.setdefault(field, []).append(value)
                normalized.append(
                    {
                        "marker": _coupled_marker(overrides),
                        "overrides": dict(overrides),
                        "decision_values": dict(overrides),
                    }
                )
            for field, values in field_values.items():
                _validate_numeric_domain(f"{pids}.{unit_name}.{field}", values)
            dimensions.append((unit_name, normalized))

        for field, parameter in spec.get("parameters", {}).items():
            values = parameter.get("values")
            if not isinstance(values, list) or not values:
                raise ValueError(f"{pids}.{field} must declare values")
            _validate_numeric_domain(f"{pids}.{field}", values)
            conditional = parameter.get("conditional_overrides", {})
            normalized = []
            for value in values:
                overrides = dict(conditional.get(str(value), {}))
                if base_values.get(field) != value:
                    overrides[field] = value
                normalized.append(
                    {
                        "marker": value,
                        "overrides": overrides,
                        "decision_values": {field: value},
                    }
                )
            dimensions.append((field, normalized))

        aliases: dict[tuple[tuple[str, Any], ...], str] = {}
        for alias, decision_configuration in spec.get(
            "legacy_configuration_aliases", {}
        ).items():
            if not isinstance(decision_configuration, dict):
                raise ValueError(f"Invalid legacy alias {alias!r} for {pids}")
            signature = tuple(sorted(decision_configuration.items()))
            if signature in aliases:
                raise ValueError(f"Duplicate alias signature for {pids}")
            aliases[signature] = alias

        sources = _source_files(list(spec.get("sources", [])), source_sets, pids)
        for selected in product(*(options for _, options in dimensions)):
            markers = {
                dimension_name: option["marker"]
                for (dimension_name, _), option in zip(dimensions, selected)
            }
            overrides = dict(fixed)
            decision_values: dict[str, Any] = {}
            for option in selected:
                overrides.update(option["overrides"])
                decision_values.update(option["decision_values"])
            signature = tuple(sorted(decision_values.items()))
            config_id = aliases.get(signature)
            if config_id is None:
                tokens = []
                for dimension_name, _ in dimensions:
                    marker = markers[dimension_name]
                    label = {
                        "model_capacity": "capacity",
                        "training.lr": "lr",
                        "featurization.used_method": "featurization",
                    }.get(dimension_name, dimension_name.replace(".", "-"))
                    tokens.append(f"{label}-{format_number(marker)}")
                config_id = f"{pids}__" + "__".join(tokens)
            if config_id in seen_ids:
                raise ValueError(f"Duplicate generated configuration id: {config_id}")
            seen_ids.add(config_id)
            items.append(
                LegalConfiguration(
                    config_id=config_id,
                    pids=pids,
                    base_model=str(spec["base_model"]),
                    scoring=scoring,
                    score_channel=score_channel,
                    overrides=overrides,
                    decision_values=decision_values,
                    source_files=sources,
                )
            )
    return items


def load_configuration_space(path: Path = DEFAULT_SPACE) -> ConfigurationSpace:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != "configuration_space_v1":
        raise ValueError("Unsupported configuration-space schema")
    if raw.get("dataset") != ALLOWED_DATASET:
        raise ValueError(f"Only {ALLOWED_DATASET} is frozen in configuration_space_v1")
    frozen = raw.get("frozen", {})
    seed = frozen.get("reproducibility", {}).get("seed")
    window = frozen.get("construction", {}).get("time_window_size_minutes")
    threshold_space_version = frozen.get("threshold", {}).get("space_version")
    if seed != 42 or window != 15:
        raise ValueError("Detector seed=42 and construction window=15 minutes are mandatory")
    if threshold_space_version != "pids_tree_quantile_v1":
        raise ValueError("Unsupported threshold-space version")

    items: list[LegalConfiguration] = []
    source_sets = raw.get("hyperparameter_sources", {})
    if not isinstance(source_sets, dict) or not source_sets:
        raise ValueError("Configuration space must declare hyperparameter_sources")
    pids_spaces = raw.get("pids_spaces")
    if pids_spaces is not None:
        if not isinstance(pids_spaces, dict) or not pids_spaces:
            raise ValueError("pids_spaces must be a non-empty mapping")
        items = _expand_pids_spaces(pids_spaces, source_sets)
    threshold_spaces = _parse_threshold_spaces(pids_spaces or {})
    seen: set[str] = {item.config_id for item in items}
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
        source_files = _source_files(item.get("sources", []), source_sets, config_id)
        items.append(
            LegalConfiguration(
                config_id=config_id,
                pids=str(item["pids"]),
                base_model=str(item["base_model"]),
                scoring=scoring,
                score_channel=str(item.get("score_channel", "objective_loss")),
                overrides=overrides,
                decision_values=dict(overrides),
                source_files=source_files,
            )
        )
    if not items:
        raise ValueError("The configuration space cannot be empty")
    expected_count = raw.get("expected_configuration_count")
    if expected_count is not None and expected_count != len(items):
        raise ValueError(
            f"Expected {expected_count} legal configurations, generated {len(items)}"
        )
    return ConfigurationSpace(
        schema_version=raw["schema_version"],
        dataset=raw["dataset"],
        seed=seed,
        time_window_minutes=window,
        threshold_space_version=threshold_space_version,
        threshold_spaces=threshold_spaces,
        configurations=tuple(items),
        decision_spaces=dict(pids_spaces or {}),
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


def _hydrate_selected_featurization_defaults(cfg: Any) -> None:
    """Fill only the selected method's unset fields from PIDSMaker defaults."""
    selected = str(cfg.featurization.used_method)
    defaults = yaml.safe_load((CONFIG_ROOT / "default.yml").read_text(encoding="utf-8"))
    method_defaults = defaults.get("featurization", {}).get(selected, {})
    if not isinstance(method_defaults, dict):
        return
    method_cfg = getattr(cfg.featurization, selected, None)
    if method_cfg is None:
        raise ValueError(f"No runtime configuration section for featurizer {selected!r}")
    for field, value in method_defaults.items():
        if getattr(method_cfg, field, None) is None:
            setattr(method_cfg, field, value)


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
    _hydrate_selected_featurization_defaults(cfg)

    cfg.training.seed = space.seed
    cfg.training.deterministic = False
    cfg.construction.time_window_size = float(space.time_window_minutes)
    cfg.construction.mimicry_edge_num = 0
    cfg.transformation.used_methods = str(cfg.transformation.used_methods)
    if "synthetic" in cfg.transformation.used_methods:
        raise ValueError("Synthetic attacks are excluded")
    if getattr(cfg.featurization, "training_split", None) not in (None, "train"):
        cfg.featurization.training_split = "train"
    # Persist the compact, reindexed batching artifact for every system. R-CAID
    # drops its wide edge inputs during reindexing, so this artifact is now the
    # reusable training frontier instead of a second full edge-embedding copy.
    cfg.batching.save_on_disk = True
    cfg.evaluation.used_method = "node_evaluation"
    cfg.evaluation.node_evaluation.use_kmeans = False
    # Keep the upstream PIDS-native method for its internal compatibility checks.
    # Agent-visible threshold selection/calibration is owned separately by the
    # adapter and is always validation_quantile.
    if legal.pids == "magic":
        cfg.evaluation.node_evaluation.threshold_method = "magic"
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
        "featurization.used_method": "featurization",
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
