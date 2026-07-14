# Reproduction and operational handoff

Requirements: REQ-GIT-001..003, REQ-ENV-001..004, REQ-RESOURCE-001..003,
REQ-REPRO-001..003, REQ-WANDB-001.

## Immutable baselines

- Main code comes only from GitHub and is synchronized to AutoDL with a clean-tree
  `git pull --ff-only`.
- PIDSMaker is fixed at `32602734bc9f896be5fc0f03f0a185c967cd6624`.
- AutoDL quotas are 32 vCPU, 240 GiB RAM, two RTX 4090 GPUs, and 24 GiB per GPU;
  host-visible excess is never allocatable.
- PIDSMaker uses the existing `pids` environment. vLLM uses the independent `vllm`
  environment. Neither environment is merged or upgraded by project scripts.
- PostgreSQL is version 17.9 at
  `/root/autodl-tmp/postgresql/17/main`. Runtime scripts never initialize, migrate,
  restore, drop, or repair it.
- W&B is disabled and never used as an artifact or reproduction service.

## Test and synthetic acceptance

On AutoDL:

```bash
cd /root/APTDetectionAgent
source /root/miniconda3/etc/profile.d/conda.sh
conda activate pids
PYTHONPATH=src python -m unittest discover -s tests -v
```

The accepted Phase 9 synthetic run is
`/root/autodl-tmp/apt-agent/experiments/runs/phase9_synthetic_e2e_20260714_001`.
It proves chronological/config/memory/process-boundary behavior only. Its private
fixture and complete metrics stay under the evaluator-private root and are not an
Agent input.

The formal stage entrypoints are:

```bash
export APT_AGENT_PYTHON="$CONDA_PREFIX/bin/python"
scripts/train_agent.sh --run-id <new-id> --stage all
scripts/test_agent.sh --run-id <new-id> --mode synthetic
scripts/test_agent.sh --run-id <new-id> --mode real
```

`train_agent.sh --stage all` currently exits 3 after recording successful preflight
stages and explicit Phase 8/SFT blockers. `test_agent.sh --mode real` also exits 3
before data/model mutation. These are expected fail-closed states, not test
failures. Every run ID is append-only and must be new.

## Long-run operations

After `tmux` is installed through a separately approved environment operation:

```bash
scripts/remote/start_run.sh <run-id> train --stage all
scripts/remote/status_run.sh <run-id>
scripts/remote/tail_run.sh <run-id> 100
scripts/remote/collect_run_summary.sh <run-id>
scripts/remote/stop_owned_run.sh <run-id>
```

`stop_owned_run.sh` refuses sessions without the ownership marker created by
`start_run.sh`. On the current AutoDL baseline `tmux` is absent, so `start_run.sh`
returns `BLOCKED_BY_MISSING_TMUX` before creating a run/control directory. Do not
replace this with an unowned background process for long training.

## Required artifacts

Formal run directories are below
`/root/autodl-tmp/apt-agent/experiments/runs/<run_id>/` and preserve command, main
and submodule SHA, diff, environment, resource/config/data/artifact manifests,
stdout/stderr, tool calls, trajectory, predictions, metrics or sanitized metric
reference, status, and summary. Full held-out metric files remain evaluator-private;
the Agent-visible report receives only the versioned episode artifact reference.

## Real-data continuation gate

Before a real run, all of the following must be approved and verified:

1. create distinct least-privilege `pids_worker` and `hidden_evaluator` PostgreSQL
   roles/grants without exposing credentials;
2. install `tmux` without changing CUDA/PyTorch/vLLM/PIDSMaker dependencies;
3. approve a versioned compatibility patch applied only to an isolated PIDSMaker
   build copy, adding bounded `[start,end)` construction, optional local logging,
   train/validation-only training, and checkpoint save/load;
4. validate one causal ApprovedConfig/checkpoint/threshold before held-out use.

No PIDS is promoted from unavailable until those checks and an independent resource
profile pass.
