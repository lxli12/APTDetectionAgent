# Experiment Protocol

Mapped requirements: REQ-EVAL-001..006, REQ-REPRO-001..003,
REQ-RESOURCE-001..003, REQ-SFT-003..004, REQ-WANDB-001.

## Run identity and immutable inputs

Every formal run receives a unique run ID and a new directory. It records the main
Git SHA, PIDSMaker SHA, diff, exact command, resolved configuration, environment,
resource profile, data manifest, PIDS/config/checkpoint, threshold provenance,
random seeds, timestamps, runtime, peak resources, predictions, complete metrics,
and failure status. Existing run directories are never overwritten.

Required local outputs are `command.txt`, `git_commit.txt`, `git_diff.patch`,
`environment.json`, `resource_profile.yaml`, `config_resolved.yaml`,
`data_manifest.json`, `artifact_manifest.json`, `stdout.log`, `stderr.log`,
`tool_calls.jsonl`, `trajectory.jsonl`, `predictions.jsonl`, `metrics.json`,
`run_status.json`, and `summary.md`.

W&B is prohibited. JSON, JSONL, YAML, and local logs are the reproducibility record.

## Evaluation

Main metrics are campaign coverage, unique malicious-node TP/FP/FN, P@C=100%, MCC,
and ADP. Node-window occurrence, malicious-edge recovery, attack-chain edge recall,
phase coverage, evidence provenance completeness, latency, GPU time, and tool calls
are reported separately with explicit denominators.

Threshold and trigger selection occur on validation data. Held-out execution cannot
update weights, recalibrate thresholds, update static LTM, search configuration with
hidden metrics, or receive test-label feedback.

Synthetic fixtures validate behavior but are never formal model-performance
evidence. Formal SFT stages report `BLOCKED_BY_SFT_DATASET` until a validated,
sanitized trajectory dataset exists.

## Remote execution

Long tasks use an owned tmux session and write to
`/root/autodl-tmp/apt-agent/experiments/runs/<run_id>/`. After launch, verify the
session, PID, log growth, GPU/CPU/RAM use, and absence of traceback, OOM, NaN, or
database errors. Preserve status, tail, expected completion, and recovery commands.
