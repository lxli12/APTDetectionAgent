# pidsmaker_adapter

This directory is the runnable, project-owned node-detection subset used to prepare
finite detector configurations before Agent evaluation.

List the frozen configuration space:

```bash
python -m pidsmaker_adapter.main list-configs
```

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
    ├── train_result.json
    ├── val_result.json
    └── test_result.json
```

`train_result.json` and `val_result.json` are eligible initialization references.
`test_result.json` is deliberately excluded from Agent initialization and contains
no label-derived metrics. Any label-dependent test evaluation belongs in a separate
post-hoc evaluator output.

Run all frozen CLEARSCOPE_E3 configurations across both GPUs with:

```bash
bash pidsmaker_adapter/experiments/run_clearscope_e3.sh
```
