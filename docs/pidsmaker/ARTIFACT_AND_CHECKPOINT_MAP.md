# PIDSMaker artifact and checkpoint map

Requirements: REQ-ARTIFACT-001..003, REQ-PIDS-002, REQ-REPRO-001.

PIDSMaker derives hashed per-stage artifact paths in
`PIDSMaker/pidsmaker/config/pipeline.py:240-320`. Important raw outputs include:

| Stage | Raw artifacts | Evidence |
|---|---|---|
| construction | graph tensors, index/type maps | `build_default_graphs.py:145-174,459` |
| transformation | transformed graph tensors | `tasks/transformation.py:51,76` |
| feat_inference | `*.TemporalData.simple` | `tasks/feat_inference.py:80` |
| batching | serialized train/val/test batches | `tasks/batching.py:36` |
| inference | per-window edge-loss directories | `inference_loop.py:71,248` |
| node evaluation | results/stats/scores pickle files | `node_evaluation.py:411-424` |
| edge evaluation | score pickle files | `edge_evaluation.py:116-128` |
| triage | traced time-window information | `triage/tracing_methods/depimpact.py:172` |

The defined model bundle is `state_dict.pkl`, plus `neighbor_loader.pkl` and
optionally `memory.pkl` for TGN encoders, at
`PIDSMaker/pidsmaker/utils/data_utils.py:868-906`.

Critical gap: the normal training loop currently comments out its `save_model` call
at `PIDSMaker/pidsmaker/detection/training_methods/training_loop.py:221-222`.
Consequently a successful training process does not establish checkpoint
availability. Phase 2 must report missing checkpoint explicitly; Phase 8 must verify
a versioned compatibility approach before claiming save/load acceptance. No direct
submodule edit is allowed.

Raw pickle/Torch artifacts are not Agent contracts. The adapter must collect them
under a unique run root, hash them, retain their producing stage and config/checkpoint
provenance, and emit only standardized deployment-visible summaries.
