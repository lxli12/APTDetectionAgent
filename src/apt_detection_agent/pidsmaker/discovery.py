"""Discover PIDS and datasets from a pinned PIDSMaker checkout without importing it.

Requirements: REQ-PIDS-001..005, REQ-CAUSAL-004, REQ-ARTIFACT-002.
"""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from apt_detection_agent.schemas import (
    AvailabilityStatus,
    CheckpointDescriptor,
    ConfigParameter,
    DetectionUnit,
    PIDSCapability,
    PIDSRef,
    PipelineStage,
    TransductiveStatus,
)


PINNED_COMMIT = "32602734bc9f896be5fc0f03f0a185c967cd6624"
RESERVED_CONFIGS = frozenset({"default", "tests"})
PIPELINE_KEYS = {stage.value: stage for stage in PipelineStage}
KEY_VALUE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_-]*):(?:\s*(?P<value>.*?))?\s*$")


class DiscoveryError(RuntimeError):
    """Raised when source evidence is incomplete or inconsistent."""


@dataclass(frozen=True)
class ParsedConfig:
    config_id: str
    path: Path
    include: str | None
    values: dict[str, str]
    sections: frozenset[str]


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(value):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return value[:index].rstrip()
    return value.strip()


def _parse_config(path: Path) -> ParsedConfig:
    stack: list[tuple[int, str]] = []
    values: dict[str, str] = {}
    sections: set[str] = set()
    include: str | None = None
    for raw_line in path.read_text().splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        match = KEY_VALUE.match(raw_line)
        if not match:
            continue
        indent = len(match.group("indent"))
        key = match.group("key")
        value = _strip_inline_comment(match.group("value") or "")
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path_parts = [item[1] for item in stack] + [key]
        dotted = ".".join(path_parts)
        if indent == 0:
            sections.add(key)
        if dotted == "_include_yml" and value:
            include = value.strip("'\"")
        if value:
            values[dotted] = value
        else:
            stack.append((indent, key))
    return ParsedConfig(path.stem, path, include, values, frozenset(sections))


class PIDSMakerDiscovery:
    """Static source discovery with no PIDSMaker or database imports."""

    def __init__(
        self,
        project_root: Path,
        checkpoint_root: Path | None = None,
        *,
        pidsmaker_root: Path | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.pidsmaker_root = (
            pidsmaker_root.resolve()
            if pidsmaker_root is not None
            else (self.project_root / "PIDSMaker").resolve()
        )
        self.config_root = self.pidsmaker_root / "config"
        self.checkpoint_root = checkpoint_root

    def verify_commit(self) -> str:
        compatibility_marker = self.pidsmaker_root / ".apt-pidsmaker-compat.json"
        if compatibility_marker.is_file():
            import json

            identity = json.loads(compatibility_marker.read_text())
            commit = str(identity.get("upstream_commit", ""))
            if (
                identity.get("schema_version") != "apt-pidsmaker-compat-v1"
                or identity.get("source_submodule_modified") is not False
                or commit != PINNED_COMMIT
            ):
                raise DiscoveryError("isolated PIDSMaker compatibility identity is invalid")
            return commit
        result = subprocess.run(
            ["git", "-C", str(self.pidsmaker_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        commit = result.stdout.strip()
        if commit != PINNED_COMMIT:
            raise DiscoveryError(f"PIDSMaker commit {commit} does not match {PINNED_COMMIT}")
        return commit

    def parsed_configs(self) -> dict[str, ParsedConfig]:
        configs = {path.stem: _parse_config(path) for path in sorted(self.config_root.glob("*.yml"))}
        if "default" not in configs:
            raise DiscoveryError("PIDSMaker default.yml is missing")
        for config in configs.values():
            if config.include and config.include not in configs:
                raise DiscoveryError(f"{config.config_id} includes missing config {config.include}")
        return configs

    def resolved_config(self, config_id: str) -> tuple[dict[str, str], frozenset[str]]:
        configs = self.parsed_configs()
        visiting: set[str] = set()

        def resolve(current: str) -> tuple[dict[str, str], set[str]]:
            if current in visiting:
                raise DiscoveryError(f"cyclic config include at {current}")
            visiting.add(current)
            config = configs[current]
            values: dict[str, str] = {}
            sections: set[str] = set()
            if config.include:
                parent_values, parent_sections = resolve(config.include)
                values.update(parent_values)
                sections.update(parent_sections)
            values.update(config.values)
            sections.update(config.sections)
            visiting.remove(current)
            return values, sections

        values, sections = resolve(config_id)
        return values, frozenset(sections)

    def model_config_ids(self) -> tuple[str, ...]:
        return tuple(
            config_id
            for config_id in sorted(self.parsed_configs())
            if config_id not in RESERVED_CONFIGS
        )

    def dataset_ids(self) -> tuple[str, ...]:
        config_py = self.pidsmaker_root / "pidsmaker/config/config.py"
        module = ast.parse(config_py.read_text())
        for node in module.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "DATASET_DEFAULT_CONFIG" for target in node.targets):
                continue
            data = ast.literal_eval(node.value)
            if not isinstance(data, dict):
                break
            return tuple(data.keys())
        raise DiscoveryError("DATASET_DEFAULT_CONFIG literal was not found")

    @staticmethod
    def pids_ref(config_id: str) -> PIDSRef:
        if config_id == "orthrus_fixed":
            return PIDSRef(pids_id="orthrus", variant_id="fixed")
        if config_id == "orthrus_non_snooped":
            return PIDSRef(pids_id="orthrus", variant_id="non_snooped")
        return PIDSRef(pids_id=config_id, variant_id="default")

    def _checkpoint(self, config_id: str) -> CheckpointDescriptor:
        if self.checkpoint_root is None:
            return CheckpointDescriptor(
                format="pytorch_state_dict_bundle",
                availability=AvailabilityStatus.UNVERIFIED,
            )
        candidate = self.checkpoint_root / config_id
        state_dicts = tuple(candidate.rglob("state_dict.pkl")) if candidate.is_dir() else ()
        if not state_dicts:
            return CheckpointDescriptor(
                format="pytorch_state_dict_bundle",
                availability=AvailabilityStatus.UNAVAILABLE,
                unavailable_reason="no state_dict.pkl found under configured checkpoint root",
            )
        return CheckpointDescriptor(
            format="pytorch_state_dict_bundle",
            availability=AvailabilityStatus.UNVERIFIED,
            unavailable_reason=None,
        )

    def capabilities(self) -> tuple[PIDSCapability, ...]:
        commit = self.verify_commit()
        configs = self.parsed_configs()
        datasets = self.dataset_ids()
        capabilities: list[PIDSCapability] = []
        for config_id in self.model_config_ids():
            resolved, sections = self.resolved_config(config_id)
            evaluation_method = resolved.get("evaluation.used_method", "node_evaluation")
            transductive = resolved.get("featurization.training_split") == "all"
            if evaluation_method == "node_evaluation":
                transductive = transductive or (
                    resolved.get("evaluation.node_evaluation.use_kmeans") == "True"
                )
            elif evaluation_method == "node_tw_evaluation":
                transductive = transductive or (
                    resolved.get("evaluation.node_tw_evaluation.use_kmeans") == "True"
                )
            elif evaluation_method == "queue_evaluation":
                transductive = transductive or (
                    resolved.get(
                        "evaluation.queue_evaluation.kairos_idf_queue.include_test_set_in_IDF"
                    )
                    == "True"
                )
            if evaluation_method == "edge_evaluation":
                unit = DetectionUnit.EDGE
            elif evaluation_method in {"node_tw_evaluation", "queue_evaluation"}:
                unit = DetectionUnit.NODE_TIME_WINDOW
            else:
                unit = DetectionUnit.NODE
            checkpoint = self._checkpoint(config_id)
            current = checkpoint.availability
            reason = checkpoint.unavailable_reason if current == AvailabilityStatus.UNAVAILABLE else None
            stage_values = tuple(
                stage for name, stage in PIPELINE_KEYS.items() if name in sections and name != "reconstruction"
            )
            parameters = tuple(
                ConfigParameter(name=name, value_type="upstream_yaml", configurable_by_agent=False)
                for name in sorted(resolved)
                if "." in name and not name.startswith("_")
            )
            capabilities.append(
                PIDSCapability(
                    pids=self.pids_ref(config_id),
                    implementation_path="PIDSMaker/pidsmaker/main.py",
                    source_config_id=config_id,
                    source_path=f"PIDSMaker/config/{config_id}.yml",
                    source_semantics=(
                        f"inherits {configs[config_id].include}" if configs[config_id].include else "standalone"
                    ),
                    supported_datasets=datasets,
                    required_pipeline_stages=stage_values,
                    detection_unit=unit,
                    training_support="training" in sections,
                    inference_support="evaluation" in sections,
                    checkpoint=checkpoint,
                    configurable_modules=tuple(sorted(name for name in sections if name in PIPELINE_KEYS)),
                    configurable_parameters=parameters,
                    threshold_semantics=resolved.get(
                        "evaluation.node_evaluation.threshold_method",
                        resolved.get("evaluation.edge_evaluation.threshold_method", "upstream_defined"),
                    ),
                    cpu_supported=True,
                    gpu_required=False,
                    expected_outputs=("scores", "metrics", "stage_artifacts"),
                    known_compatibility_limitations=(
                        "all dataset entries are syntactic support until checkpoint smoke validation",
                    ),
                    transductive_status=(
                        TransductiveStatus.TRANSDUCTIVE if transductive else TransductiveStatus.CAUSAL
                    ),
                    compatibility_status=(
                        "compatibility_baseline" if transductive else "causal_candidate_unverified"
                    ),
                    current_availability_status=current,
                    unavailable_reason=reason,
                    pidsmaker_commit=commit,
                )
            )
        return tuple(capabilities)
