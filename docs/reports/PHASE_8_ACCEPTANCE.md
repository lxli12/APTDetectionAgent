# Phase 8 acceptance report — bounded causal smoke accepted

Requirements: REQ-PIDS-001..005, REQ-ARTIFACT-001..003,
REQ-RESOURCE-001..003, REQ-REPRO-001..003, REQ-LABEL-001..004,
REQ-WANDB-001, REQ-DB-001..003.

## Accepted implementation and evidence

The pinned PIDSMaker submodule remains clean at
`32602734bc9f896be5fc0f03f0a185c967cd6624`. The versioned patch
`compat/pidsmaker/32602734bc9f896be5fc0f03f0a185c967cd6624/0001-apt-causal-runtime.patch`
is applied only to an isolated build by `scripts/build_pidsmaker_compat.py`. It
adds parameterized `[start,end)` construction, environment-only database secrets,
train/validation-only checkpoint selection, frozen test inference, local logging,
lazy optional imports, and no runtime NLTK download.

The real bounded run is
`/root/autodl-tmp/apt-agent/experiments/runs/phase8-velox-cadets-smoke-20260714-002`.
It used VELOX on `CADETS_E3`, three chronological 15-minute windows, GPU 1, 16
CPU threads, and the least-privilege `pids_worker` role. Its frozen checkpoint hash
is `9fd5b64fd65f71faea65b037294dca537c75ab902a4ad92f04bb84315c0f54a2`.
Raw output contains `loss,srcnode,dstnode,time,edge_type` and no label field.

`scripts/freeze_pre_sft_bundle.py` froze that checkpoint, its train-fitted
Word2Vec model, a validation threshold, and a validation-only ApprovedConfig.
`scripts/pidsmaker_stage_runner.py` and `scripts/pidsmaker_causal_runner.py` now
accept a hash-checked `--frozen-bundle`, reject runtime parameter drift, skip
featurizer fitting, and run inference without labels. The independent new-window
run
`/root/autodl-tmp/apt-agent/experiments/runs/phase10-frozen-new-window-20260714-001`
produced 8,394 scores for `[2018-04-06 14:00,14:15)` America/New_York while
preserving checkpoint and featurizer hashes. Its public `metrics.json` records
`test_labels_loaded=false`, `featurizer_fit_on_current_window=false`, and
`formal_performance_claim=false`.

Live AutoDL gates also passed: tmux is available; distinct PostgreSQL roles are
provisioned and verified by `scripts/postgres/verify_role_policy.sh`; the isolated
compatibility build is separate from the submodule; and all project tests passed
in the existing `pids` environment at the cited commits.

## Scope limit

This accepts one bounded VELOX/CADETS validation profile and its artifact
lifecycle. It is not a benchmark and does not make every PIDS/dataset pair
available. The remaining nine registry entries stay visible with explicit
unavailable/unverified reasons until each receives its own checkpoint,
compatibility, latency, RAM, and VRAM smoke profile.
