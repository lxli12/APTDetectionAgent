# pidsmaker_adapter

This directory is the runnable, project-owned node-detection subset used to prepare
finite detector configurations before Agent evaluation.

List the frozen configuration space:

```bash
python -m pidsmaker_adapter.main list-configs
```

`config/configuration_space_v1.yaml` declares PIDS-specific decision domains with
explicit `values`. Numeric decision fields expose three to five upstream-anchored
values. Embedding and hidden dimensions are represented as validated
`model_capacity` tuples rather than an unsafe Cartesian product. The declared
capacity, representation, and learning-rate dimensions are expanded with
`coverage: full_factorial`, producing 295 concrete train configurations across
seven selectable PIDS. MAGIC remains in the adapter as commented/reference code
but is excluded from the Agent configuration space because its native threshold
calibration observes held-out test scores. The 14 active, previously published
`base`/`compact`/`wide` identifiers are aliases for matching tuples and retain
their existing checkpoint paths.

Prepare one checkpoint on the AutoDL data disk:

```bash
export PIDS_DB_PASSWORD=...
CUDA_VISIBLE_DEVICES=0 python -m pidsmaker_adapter.main prepare --config kairos_base
```

The publication layout is:

```text
/root/autodl-tmp/apt-detection-agent/pidsmaker-output/
├── stage-cache/<stage>/<content-digest>/
└── CLEARSCOPE_E3/<pids>/checkpoint_<formatted-config>/
    ├── model/
    ├── inference/{train,val,test}/node_scores.jsonl
    ├── manifest.json
    ├── resolved_config.yaml
    ├── thresholds.json
    ├── train_val_resource_usage.json
    ├── train_result.json
    ├── val_result.json
    └── test_result.json
```

Internal hashes are used only for cache identity. Once a compact persistent
batching artifact is complete, its much wider feat-inference input is reclaimed.
Configurations that differ only in learning rate therefore reuse construction,
transformation, featurization, feature inference, and batching without retaining
duplicate edge-embedding corpora.

`train_result.json` and `val_result.json` are eligible initialization references.
Threshold selection is PIDS-specific: FLASH uses `flash`, ThreaTrace uses
`threatrace`, Nodlink uses `nodlink`, and Kairos/Orthrus/R-CAID/Velox use
`max_val_loss`. Selecting a method resolves a scalar in `thresholds.json`; it
does not change model weights or the checkpoint hash. MAGIC is not selectable.
`train_val_resource_usage.json` records the consistently named resource scope from
construction through train and validation, including cache reuse, wall time, CPU,
peak RSS, and per-visible-GPU peaks. Runs completed before resource monitoring was
introduced use the same schema with `collection_status: historical_partial` and
explicit `null` values for observations that cannot be recovered.
`test_result.json` is deliberately excluded from Agent initialization and contains
no label-derived metrics. Any label-dependent test evaluation belongs in a separate
post-hoc evaluator output.

Run all frozen CLEARSCOPE_E3 configurations across both GPUs with:

```bash
bash pidsmaker_adapter/experiments/run_clearscope_e3.sh
```

To finish one detector family first without changing the legal configuration
set, set `PIDS_PRIORITY` (for example, `PIDS_PRIORITY=rcaid`). The run snapshots
both the complete configuration set and the resulting `execution_order.txt`.
