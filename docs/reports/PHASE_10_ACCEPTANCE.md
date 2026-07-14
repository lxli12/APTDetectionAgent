# Phase 10 acceptance report — interfaces complete, formal training blocked

Requirements: REQ-SFT-001..004, REQ-LABEL-002..004,
REQ-ARTIFACT-001..003, REQ-REPRO-001..003.

## Accepted interface behavior

- `src/apt_detection_agent/sft/teacher.py` is the privileged teacher schema;
  `src/apt_detection_agent/sft/contracts.py:StudentSFTExample` is the separate
  deployment-visible student schema.
- `src/apt_detection_agent/sft/sanitizer.py` removes teacher-only rationale,
  privileged labels, and counterfactual fields, rejects privileged phrases in
  student rationale, and hashes the exact sanitized payload.
- `src/apt_detection_agent/sft/builder.py` accepts agent-training records only,
  creates explicit non-overlapping train/validation partitions, and emits a
  versioned dataset hash/manifest. Synthetic data cannot be formally approved.
- `scripts/train_sft.py` validates dataset/config identity and supports dry-run
  without weight updates or checkpoint creation. Missing/unapproved data produces
  `BLOCKED_BY_SFT_DATASET`.
- Checkpoint/adapter and future low-bandwidth RL contracts reject unsafe paths,
  held-out step reward, unbounded reward, and missing provenance.
- `scripts/train_agent.sh` and `scripts/test_agent.sh` expose the required formal
  stage lists; their real-data paths fail closed at documented gates.
- `scripts/remote/` implements unique owned-run start/status/tail/stop/summary.
  The live missing-tmux preflight returned code 3 before creating any run directory.

AutoDL commit `266c050f49a1d5a11fc002945715a8bf8ed90c80` passed all
168 tests in the existing `pids` environment. Formal entrypoint runs are:

- `/root/autodl-tmp/apt-agent/experiments/runs/phase10_train_preflight_20260714_001`
  — 11 stages recorded, expected terminal status `blocked`, with the SFT stages
  explicitly `BLOCKED_BY_SFT_DATASET`;
- `/root/autodl-tmp/apt-agent/experiments/runs/phase10_test_synthetic_20260714_001`
  — terminal status `succeeded`, explicitly non-formal synthetic evidence.

Both GPUs remained at 0 MiB for these interface/preflight runs.

## Deliberately not claimed

No formal trajectory dataset, SFT weight update, adapter, checkpoint, or performance
result exists. Formal SFT therefore remains `BLOCKED_BY_SFT_DATASET`. A future
trainer backend may be connected only after dataset deployability approval; the
current CLI reports readiness but never fabricates training.
