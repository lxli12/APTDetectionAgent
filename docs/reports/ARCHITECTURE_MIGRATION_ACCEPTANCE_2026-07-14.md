# Architecture Migration Acceptance — 2026-07-14

Status: local acceptance pending reviewer approval

Architecture: `docs/PROJECT_ARCHITECTURE_DESIGN_v1.1.md`

Requirements: REQ-GOV-001..003, REQ-RUNTIME-001..006, REQ-TOOL-001..005,
REQ-PIDS-001..006, REQ-MEMORY-001..007, REQ-SFT-001..010,
REQ-EVAL-001..007, REQ-REPRO-001..003

## Accepted ownership

- `agent/`: model transport and policy output boundary;
- `runtime/`: frozen controller, observation construction, scheduling and trajectory;
- `memory/`: store and frozen memory protocol;
- `tools/`: logical runtime and memory tools;
- `pidsmaker/`: registry, admission, adapter and result normalization;
- `sft/`: canonical models, datasets, builder, validators and exporters;
- `training/`: SFT trainer-neutral request/result interface;
- `evaluation/`: public/private models, metrics, calibration, IPC and reporting;
- `experiment/`: composition and synthetic integration runner.

The former `controller/`, `llm/`, `tooling/`, `evaluator/`, and `validation/`
packages contain compatibility imports only. Pre-demonstration SFT readers are
isolated under `sft/compat/`; the current public SFT path does not expose an RL
implementation.

## Dependency evidence

- tools consume `ActionExecutionEnvelope` from `schemas`, not runtime code;
- SFT owns an offline capability snapshot and does not import tool implementation;
- public evaluation import does not load private evaluator models;
- runtime imports Agent policy and exchange schemas, never evaluation/training/SFT;
- PIDSMaker admission behavior is separate from admission exchange schemas;
- governance rejects imports of deprecated package owners from new code.

## Configuration and reproducibility

Versioned runtime, dataset, PIDSMaker, SFT-build, training and evaluation configs
are present under `configs/`. Generated experiment runs remain outside Git;
`experiments/` accepts reviewed definitions only. PIDSMaker remains pinned at
`32602734bc9f896be5fc0f03f0a185c967cd6624` and was not modified.

## Verification

- `scripts/check_governance.py`: passed;
- full local test suite: 277 tests passed;
- synthetic multi-window/evaluator/public-report path: passed within the suite;
- process runtime isolation build: passed within the suite;
- `git diff --check`: required before commit;
- remote smoke, data generation and model training: not run and not required for
  this code-organization migration.
