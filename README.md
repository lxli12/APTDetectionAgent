# APTDetectionAgent

APTDetectionAgent is an LLM-based orchestration layer for long-horizon APT
detection. It uses the pinned `PIDSMaker/` git submodule only through a typed
adapter and does not modify, duplicate, or manage PIDSMaker internals.

## Documentation

- [Project architecture v1.1](docs/architecture/PROJECT_ARCHITECTURE_DESIGN_v1.1.md)
  is frozen and defines repository structure, ownership, dependencies, and the
  PIDSMaker integration boundary.
- [Agent design v0.4](docs/design/APT_Detection_Agent_Design_v0.4.md) defines the
  current research protocol: construction-graph steps, event-triggered
  fast/slow paths, fixed memory harness, constrained tools, SFT-first training,
  and held-out evaluation.
- [Development rules](AGENTS.md) record the local/remote execution boundary,
  authoritative AutoDL environment, coding conventions, PIDSMaker protection,
  and Git discipline for all future work.
- [Implementation tasks](docs/implementation/IMPLEMENTATION_TASKS.md) divide the
  complete v0.4 implementation into dependency-ordered tasks with deliverables,
  acceptance criteria, milestones, and local/AutoDL verification boundaries.

## Repository layout

```text
PIDSMaker/                    pinned, unchanged detection backend
src/apt_detection_agent/     Agent policy, controller, memory, tools, adapter,
                             schemas, evaluation, experiments, and future SFT
configs/                     stable YAML configuration
prompts/                     runtime-loaded plain-text prompts
scripts/                     thin reproducible entry points
tests/                       architecture-aligned tests
data/                        Agent-owned local-only datasets
checkpoints/                 Agent-owned local-only checkpoints
experiments/                 Agent run definitions and generated outputs
docs/                        architecture, current design, and archive
```

PIDSMaker continues to own provenance preprocessing, PIDS implementations,
backend training/inference/evaluation, intermediate artifacts, and PIDS
checkpoints. APTDetectionAgent owns orchestration and interacts with that backend
only through `pidsmaker_adapter/` and typed tools.

## Development

The local Apple Silicon machine is for code, documentation, and lightweight
checks only. Data processing and experiments must run on the AutoDL server after
its live environment has been inspected; the historical setup script is only a
reference. See [AGENTS.md](AGENTS.md) before making changes.

```bash
python -m pip install -e '.[dev]'
pytest
```

Generated datasets, checkpoints, and run outputs are local-only. Prompt templates
are plain `.txt` files under `prompts/`.
