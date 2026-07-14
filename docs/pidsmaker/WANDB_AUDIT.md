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
| D — upstream change required | accepted training path is resolved by the versioned isolated compatibility patch; evaluation/triage remain outside Agent execution |
| E — adapter can avoid forced online mode | never invoke `scripts/run.sh:18`, `scripts/run_serial.sh:18`, tuning, uncertainty, sweep, or `--wandb` |

`PIDSMaker/pyproject.toml:27` mentions W&B only in lint configuration; the Apptainer
environment separately declares it at `PIDSMaker/scripts/apptainer/environment.yaml:23`.

Adapter policy:

1. build argv without `--wandb`, tuning, sweep, uncertainty, project, entity, or tags;
2. run with disabled upstream mode and local JSON/JSONL logs;
3. prohibit WANDB environment values and outbound tracking as runtime policy;
4. apply the versioned compatibility patch only to an isolated build copy;
5. never create a fake W&B package or monkey-patch global imports.

For preprocessing work, `scripts/pidsmaker_stage_runner.py` avoids
`PIDSMaker/pidsmaker/main.py` and bypasses
`PIDSMaker/pidsmaker/tasks/__init__.py`, whose eager imports pull in W&B-dependent
training/evaluation modules. It permits only construction, transformation,
featurization, and `feat_inference`, and requires `WANDB_MODE=disabled`.

The isolated patch at
`compat/pidsmaker/32602734bc9f896be5fc0f03f0a185c967cd6624/0001-apt-causal-runtime.patch`
removes the training path's import/calls and lazily imports optional uncertainty
code. The real Phase 8 training and frozen inference runs passed an import gate
asserting that `wandb` was absent from loaded modules. The accepted VELOX path is
therefore class D resolved by a versioned patch plus class E adapter avoidance.
W&B 0.25.1 being present in the historical `pids` environment remains unapproved
and unnecessary; no install, login, initialization, or network request is part of
reproduction.
