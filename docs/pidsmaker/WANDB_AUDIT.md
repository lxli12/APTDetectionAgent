# PIDSMaker W&B dependency audit

Requirements: REQ-WANDB-001, REQ-PIDS-005, REQ-TOOL-005.

AutoDL read-only inspection found W&B 0.25.1 installed in `pids` and absent in
`vllm`. Installation history is not approval: APTDetectionAgent disables W&B and
does not use it for reproduction.

| Class | Finding |
|---|---|
| A — configuration can disable network logging | CLI omission of `--wandb` reaches disabled initialization in `main.py:330-345`, but this still requires the package to be installed |
| B — calls remain but disabled backend absorbs them | training/evaluation/main contain `wandb.log` calls |
| C — uninstall causes import-time failure | unconditional imports in `main.py:20`, `training_loop.py:18`, `tasks/evaluation.py:3`, `tasks/triage.py:5`, and `tests/test_framework.py:6` |
| D — true optional dependency requires upstream compatibility change | imports and `wandb.Image` use must become optional/local |
| E — adapter can avoid forced online mode | never invoke `scripts/run.sh:18`, `scripts/run_serial.sh:18`, tuning, uncertainty, sweep, or `--wandb` |

`PIDSMaker/pyproject.toml:27` mentions W&B only in lint configuration; the Apptainer
environment separately declares it at `PIDSMaker/scripts/apptainer/environment.yaml:23`.

Initial adapter policy:

1. build argv without `--wandb`, tuning, sweep, uncertainty, project, entity, or tags;
2. run with disabled upstream mode and local JSON/JSONL logs;
3. prohibit WANDB environment values and outbound tracking as runtime policy;
4. retain a versioned compatibility-patch plan for a future isolated build copy;
5. never create a fake W&B package or monkey-patch global imports.

For preprocessing-only Phase 8 work, `scripts/pidsmaker_stage_runner.py` avoids
`PIDSMaker/pidsmaker/main.py` and bypasses
`PIDSMaker/pidsmaker/tasks/__init__.py`, whose eager imports pull in W&B-dependent
training/evaluation modules. It permits only construction, transformation,
featurization, and `feat_inference`, and requires `WANDB_MODE=disabled`. This is
class E avoidance, not proof that training is W&B-independent.

Because the current `pids` environment still contains W&B, disabled-mode smoke can
run without installing anything. This is a temporary upstream compatibility fact,
not an approved project dependency.
