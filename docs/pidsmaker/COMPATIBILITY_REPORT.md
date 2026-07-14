# PIDSMaker compatibility report

Requirements: REQ-PIDS-005, REQ-TOOL-002..005, REQ-ARTIFACT-002..003,
REQ-LABEL-001..004, REQ-WANDB-001, REQ-DB-003.

Baseline: PIDSMaker commit
`32602734bc9f896be5fc0f03f0a185c967cd6624`. The submodule is unchanged. The
project-maintained patch
`compat/pidsmaker/32602734bc9f896be5fc0f03f0a185c967cd6624/0001-apt-causal-runtime.patch`
is applied by `scripts/build_pidsmaker_compat.py` only to a new isolated build
copy. Its patch-series hash is
`d53799806e0cb6c64427951e88446eae87c691e4d5a1c2c42f40143ec4790bab`.

| Gap | Pinned source evidence | Implemented compatibility behavior |
|---|---|---|
| Password in upstream CLI/default | `PIDSMaker/pidsmaker/config/pipeline.py:124-143` | isolated build reads `PIDS_DB_PASSWORD`; project runners never place it in argv or logs |
| Eager W&B imports/calls | `PIDSMaker/pidsmaker/main.py:20`; `PIDSMaker/pidsmaker/detection/training_methods/training_loop.py:18`; `PIDSMaker/pidsmaker/tasks/evaluation.py:3`; `PIDSMaker/pidsmaker/tasks/triage.py:5` | training path has no W&B import/call; optional experiment imports are lazy; runners require `WANDB_MODE=disabled` and write local JSON/JSONL |
| No causal checkpoint lifecycle | `PIDSMaker/pidsmaker/detection/training_methods/training_loop.py:221-222`; save/load helpers at `PIDSMaker/pidsmaker/utils/data_utils.py:868-906` | validation-selected checkpoint is saved with causal metrics, hashed, loaded with explicit map location, and exercised on a later window |
| Training reads test split | `PIDSMaker/pidsmaker/detection/training_methods/training_loop.py:224-264` | training loads train/validation only; test inference is a separate frozen operation |
| Full-day query before test truncation | `PIDSMaker/pidsmaker/preprocessing/build_graph_methods/build_default_graphs.py:238-322,451-462` | construction uses parameterized `timestamp_rec >= %s AND timestamp_rec < %s` for exact project windows |
| All-stage entrypoint reaches evaluation/triage | `PIDSMaker/pidsmaker/main.py:91-128` | `scripts/pidsmaker_stage_runner.py` loads allowed task files directly and strips ground-truth metadata; hidden evaluation is project-owned |
| Runtime NLTK download | upstream causal path imports tokenizer setup | isolated build requires preinstalled `punkt` and never downloads at runtime |
| Frozen featurizer absent from runtime contract | upstream feat inference reads config-local model path | `--frozen-bundle` validates content hashes, source config, dataset, validation-only ApprovedConfig, and exact overrides; fitting is skipped |
| OpTC DB name mismatch | `PIDSMaker/pidsmaker/config/config.py:196-249`; AutoDL DB is `optc_h201` | remains unavailable pending an approved project database mapping; no automatic rename/rebuild |

Real evidence is recorded in
`docs/reports/PHASE_8_ACCEPTANCE.md`. The accepted VELOX/CADETS run proves this
compatibility surface for one configuration only. Other PIDS remain registered and
unavailable/unverified until independent smoke profiles pass.

The patch is versioned, content-hashed, reproducible, and disposable. A long-lived
fork is still unwarranted; it should be considered only if the patch grows large or
repeatedly conflicts with a future explicitly approved upstream baseline. No fake
W&B package, global monkey patch, submodule edit, database migration, or environment
upgrade is used.
