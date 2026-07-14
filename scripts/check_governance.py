#!/usr/bin/env python3
"""Validate Phase 0 governance artifacts.

Requirements: REQ-GOV-001, REQ-GOV-003, REQ-GIT-003.
"""

from __future__ import annotations

import re
import ast
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PIDS_SHA = "32602734bc9f896be5fc0f03f0a185c967cd6624"
REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "docs/design/APT_Detection_Agent_Design_v0.4.md",
    "docs/PROJECT_ARCHITECTURE_DESIGN_v1.1.md",
    "docs/plans/IMPLEMENTATION_PLAN.md",
    "docs/plans/REQUIREMENT_TRACEABILITY.md",
    "docs/data_protocol.md",
    "docs/experiment_protocol.md",
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        fail(f"missing required files: {', '.join(missing)}")

    matrix = (ROOT / "docs/plans/REQUIREMENT_TRACEABILITY.md").read_text()
    plan = (ROOT / "docs/plans/IMPLEMENTATION_PLAN.md").read_text()
    ids = set(re.findall(r"REQ-[A-Z]+-\d{3}", matrix))
    if len(ids) < 25:
        fail(f"requirement matrix unexpectedly small: {len(ids)} IDs")
    if not set(re.findall(r"REQ-[A-Z]+-\d{3}", plan)).issubset(ids):
        fail("implementation plan references unknown requirement IDs")

    schemas_root = ROOT / "src/apt_detection_agent/schemas"
    forbidden_schema_imports = (
        "apt_detection_agent.sft",
        "apt_detection_agent.training",
        "apt_detection_agent.evaluation",
        "apt_detection_agent.evaluator",
        "apt_detection_agent.experiment",
    )
    schema_violations = []
    for path in schemas_root.glob("*.py"):
        source = path.read_text()
        if any(name in source for name in forbidden_schema_imports):
            schema_violations.append(str(path.relative_to(ROOT)))
    if schema_violations:
        fail(f"schemas reverse-import domain owners: {', '.join(schema_violations)}")
    if (schemas_root / "evaluation.py").exists():
        fail("private/offline evaluation models cannot live in schemas")
    public_schemas = (schemas_root / "__init__.py").read_text()
    forbidden_public_names = (
        "CampaignManifest",
        "EvaluationRecord",
        "HiddenGroundTruth",
        "EpisodeMetricsFeedback",
        "TrainingStepFeedback",
    )
    leaked = [name for name in forbidden_public_names if name in public_schemas]
    if leaked:
        fail(f"schemas public surface leaks offline/private types: {', '.join(leaked)}")

    authoritative_files = (
        "src/apt_detection_agent/agent/client.py",
        "src/apt_detection_agent/agent/policy.py",
        "src/apt_detection_agent/runtime/controller.py",
        "src/apt_detection_agent/runtime/observation.py",
        "src/apt_detection_agent/runtime/scheduler.py",
        "src/apt_detection_agent/runtime/trajectory.py",
        "src/apt_detection_agent/memory/protocol.py",
        "src/apt_detection_agent/tools/runtime.py",
        "src/apt_detection_agent/tools/memory.py",
        "src/apt_detection_agent/data/windows.py",
        "src/apt_detection_agent/pidsmaker/registry.py",
        "src/apt_detection_agent/sft/models.py",
        "src/apt_detection_agent/sft/datasets.py",
        "src/apt_detection_agent/sft/builder.py",
        "src/apt_detection_agent/sft/validators.py",
        "src/apt_detection_agent/sft/exporters.py",
        "src/apt_detection_agent/training/interface.py",
        "src/apt_detection_agent/training/sft.py",
        "src/apt_detection_agent/evaluation/private.py",
        "src/apt_detection_agent/evaluation/public.py",
        "src/apt_detection_agent/evaluation/metrics.py",
        "src/apt_detection_agent/evaluation/reporting.py",
        "src/apt_detection_agent/experiment/runner.py",
    )
    missing_authoritative = [path for path in authoritative_files if not (ROOT / path).is_file()]
    if missing_authoritative:
        fail(f"missing authoritative architecture modules: {', '.join(missing_authoritative)}")

    legacy_roots = {"controller", "llm", "tooling", "evaluator", "validation"}
    forbidden_roots = {f"apt_detection_agent.{name}" for name in legacy_roots}
    import_violations = []
    scan_roots = (ROOT / "src/apt_detection_agent", ROOT / "scripts", ROOT / "tests")
    for scan_root in scan_roots:
        for path in scan_root.rglob("*.py"):
            relative = path.relative_to(ROOT)
            parts = relative.parts
            if len(parts) > 2 and parts[0] == "src" and parts[2] in legacy_roots:
                continue
            tree = ast.parse(path.read_text(), filename=str(relative))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
                elif isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
            if any(
                module == root or module.startswith(root + ".")
                for module in imported for root in forbidden_roots
            ):
                import_violations.append(str(relative))
    if import_violations:
        fail(f"new code imports deprecated package owners: {', '.join(import_violations)}")

    compatibility_violations = []
    for package in legacy_roots:
        package_root = ROOT / "src/apt_detection_agent" / package
        for path in package_root.glob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path.relative_to(ROOT)))
            if any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body):
                compatibility_violations.append(str(path.relative_to(ROOT)))
    sft_wrapper_names = (
        "contracts.py", "sanitizer.py", "teacher.py", "frozen_contracts.py",
        "frozen_sanitizer.py", "frozen_teacher.py", "frozen_builder.py",
        "demonstration.py", "demonstration_builder.py",
        "demonstration_exporter.py", "demonstration_sanitizer.py",
    )
    for name in sft_wrapper_names:
        path = ROOT / "src/apt_detection_agent/sft" / name
        tree = ast.parse(path.read_text(), filename=str(path.relative_to(ROOT)))
        if any(isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) for node in tree.body):
            compatibility_violations.append(str(path.relative_to(ROOT)))
    if compatibility_violations:
        fail(f"deprecated compatibility paths still own implementation: {', '.join(compatibility_violations)}")

    forbidden_dependencies = {
        "agent": {"runtime", "tools", "pidsmaker", "sft", "training", "evaluation", "experiment"},
        "runtime": {"tools", "pidsmaker", "sft", "training", "evaluation", "experiment"},
        "sft": {"agent", "runtime", "memory", "tools", "pidsmaker", "training", "evaluation", "experiment"},
        "training": {"agent", "runtime", "memory", "tools", "pidsmaker", "evaluation", "experiment"},
        "evaluation": {"agent", "runtime", "memory", "tools", "pidsmaker", "sft", "training", "experiment"},
    }
    dependency_violations = []
    for owner, forbidden in forbidden_dependencies.items():
        owner_root = ROOT / "src/apt_detection_agent" / owner
        for path in owner_root.glob("*.py"):
            tree = ast.parse(path.read_text(), filename=str(path.relative_to(ROOT)))
            for node in ast.walk(tree):
                modules = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                elif isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                for module in modules:
                    prefix = "apt_detection_agent."
                    if module.startswith(prefix):
                        dependency = module[len(prefix):].split(".", 1)[0]
                        if dependency in forbidden:
                            dependency_violations.append(
                                f"{path.relative_to(ROOT)} -> {dependency}"
                            )
    if dependency_violations:
        fail(f"forbidden architecture dependencies: {', '.join(dependency_violations)}")

    if "RLCandidate" in (ROOT / "src/apt_detection_agent/sft/__init__.py").read_text():
        fail("future RL implementation cannot be exposed by the current SFT package")

    required_configs = (
        "configs/runtime/default_v1.yaml", "configs/datasets/registry_v1.yaml",
        "configs/pidsmaker/catalog_v1.yaml", "configs/sft/build_v1.yaml",
        "configs/training/sft_v1.yaml", "configs/evaluation/agent_eval_v2.yaml",
    )
    missing_configs = [path for path in required_configs if not (ROOT / path).is_file()]
    if missing_configs:
        fail(f"missing versioned architecture configs: {', '.join(missing_configs)}")

    actual_sha = subprocess.run(
        ["git", "-C", str(ROOT / "PIDSMaker"), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual_sha != EXPECTED_PIDS_SHA:
        fail(f"PIDSMaker SHA is {actual_sha}, expected {EXPECTED_PIDS_SHA}")

    submodule_diff = subprocess.run(
        ["git", "-C", str(ROOT / "PIDSMaker"), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if submodule_diff:
        fail("PIDSMaker working tree is dirty")

    print(f"OK: {len(ids)} requirement IDs; PIDSMaker {actual_sha}")


if __name__ == "__main__":
    main()
