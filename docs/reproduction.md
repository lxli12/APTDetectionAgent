# Reproduction and operational handoff

Requirements: REQ-GIT-001..003, REQ-ENV-001..004, REQ-RESOURCE-001..003,
REQ-REPRO-001..003, REQ-WANDB-001.

## Immutable baselines

- GitHub is the code source; AutoDL synchronization requires a clean tree and
  `git pull --ff-only` via `scripts/remote/sync_code.sh`.
- PIDSMaker is fixed at `32602734bc9f896be5fc0f03f0a185c967cd6624`.
- AutoDL allocation is 32 vCPU, 240 GiB RAM, and two 24-GiB RTX 4090 GPUs.
- PIDSMaker uses `pids`; vLLM uses `vllm`; neither environment is merged/upgraded.
- PostgreSQL 17.9 data at `/root/autodl-tmp/postgresql/17/main` is never
  initialized, migrated, restored, dropped, or repaired by runtime scripts.
- W&B is disabled and is not an artifact, logger, or reproduction dependency.

## Verification

```bash
cd /root/APTDetectionAgent
source /root/miniconda3/etc/profile.d/conda.sh
conda activate pids
APT_PIDS_CPU_THREADS=16 OMP_NUM_THREADS=16 MKL_NUM_THREADS=16 \
  OPENBLAS_NUM_THREADS=16 NUMEXPR_NUM_THREADS=16 \
  VECLIB_MAXIMUM_THREADS=16 PYTHONPATH=src python -m unittest discover -s tests -v
```

Accepted append-only evidence:

- synthetic protocol:
  `/root/autodl-tmp/apt-agent/experiments/runs/phase9_synthetic_e2e_20260714_001`;
- causal PIDSMaker smoke:
  `/root/autodl-tmp/apt-agent/experiments/runs/phase8-velox-cadets-smoke-20260714-002`;
- real validation integration:
  `/root/autodl-tmp/apt-agent/experiments/runs/phase9-real-e2e-20260714-002`;
- pre-SFT frozen validation bundle:
  `/root/autodl-tmp/apt-agent/pre-sft-bundles/velox-cadets-validation-8eb6f76-003`;
- frozen new-window inference:
  `/root/autodl-tmp/apt-agent/experiments/runs/phase10-frozen-new-window-20260714-001`.
- real structured tool invocation:
  `/root/autodl-tmp/apt-agent/structured-tool-runs/structured-adapter-20260714-007`.
- evaluator-isolated synthetic retrieval sensitivity smoke:
  `/root/autodl-tmp/apt-agent/memory-sensitivity-runs/memory-sensitivity-synthetic-20260714-001`.

These prove causal mechanics and validation integration only. Each real public
artifact records `formal_performance_claim=false`; evaluator-private mappings and
full metrics remain outside the controller filesystem.

## Formal stage entrypoints

```bash
export APT_AGENT_PYTHON="$CONDA_PREFIX/bin/python"
export APT_PRE_SFT_BUNDLE_ROOT=/root/autodl-tmp/apt-agent/pre-sft-bundles
export APT_PRE_SFT_BUNDLE="$APT_PRE_SFT_BUNDLE_ROOT/velox-cadets-validation-8eb6f76-003"
scripts/train_agent.sh --run-id <new-id> --stage all
scripts/test_agent.sh --run-id <new-id> --mode synthetic
scripts/test_agent.sh --run-id <new-id> --mode real \
  --pids-run <validated-run> --runtime-root <role-specific-runtime>
```

`train_agent.sh --stage all` still exits 3: PIDS/checkpoint/threshold/config stages
validate the bundle, while trajectory/SFT/static-LTM/deployment stages remain
blocked. Real test mode requires both explicit inputs; omission is a fail-closed
input gate. Every run ID and bundle directory is append-only.

## Long-run operations

```bash
scripts/remote/start_run.sh <run-id> train --stage all
scripts/remote/status_run.sh <run-id>
scripts/remote/tail_run.sh <run-id> 100
scripts/remote/collect_run_summary.sh <run-id>
scripts/remote/stop_owned_run.sh <run-id>
```

The current server has tmux. Ownership markers prevent stopping unrelated
sessions; a server without tmux fails before creating a run. Long work must not use
an unowned background process.

## Remaining gates

Least-privilege roles, live OS isolation, tmux, the isolated compatibility patch,
one causal checkpoint, one validation threshold, and one validation-only
ApprovedConfig are verified for VELOX/CADETS. Remaining work is to profile other
PIDS/datasets, finish the full agent-level validation campaign inventory, ingest
and sanitize the formal SFT trajectories, train/validate SFT and static LTM, and
only then create a distinct held-out-approved bundle. Test labels, hidden campaign
mappings, and validation episode memory may not influence those choices.
