# Phase 10 acceptance report — pre-SFT complete, formal SFT blocked

Requirements: REQ-SFT-001..004, REQ-LABEL-002..004,
REQ-ARTIFACT-001..003, REQ-REPRO-001..003.

The privileged teacher, deployment-visible student, recursive sanitizer, dataset
builder, split manifest, dry-run trainer, checkpoint contract, and static-LTM
release boundary are implemented under `src/apt_detection_agent/sft/` and tested in
`tests/test_sft.py`. Teacher-only rationale, labels, counterfactual actions, dataset
identity shortcuts, and hidden feedback cannot enter student inputs or deployable
memory.

Pre-SFT runtime assets are now frozen and independently exercised:

- `scripts/freeze_pre_sft_bundle.py` creates an append-only validation bundle with
  checkpoint, train-fitted featurizer, threshold catalog, ApprovedConfig catalog,
  availability manifest, and content hashes;
- the current accepted bundle is
  `/root/autodl-tmp/apt-agent/pre-sft-bundles/velox-cadets-validation-8eb6f76-003`;
- `scripts/validate_pre_sft_bundle.py` verifies that it remains causal,
  validation-only, non-deployment, and contains neither SFT data nor static LTM;
- `scripts/run_frozen_pidsmaker_smoke.sh` proved new-window inference without
  featurizer refit, checkpoint selection, labels, W&B, or configuration drift;
- `scripts/run_structured_pids_adapter_smoke.py` exercised the actual typed
  request → adapter → frozen PIDSMaker → standardized observation path in
  `structured-adapter-20260714-007`;
- AutoDL commit `33040bb2658323c1d2a6fccee4440bddb68a3d26`
  passed 225 tests.

`scripts/train_agent.sh` no longer reports obsolete Phase 8 blockers. With
`APT_PRE_SFT_BUNDLE` and `APT_PRE_SFT_BUNDLE_ROOT` set, its PIDS/threshold/config
stages validate frozen evidence; trajectory construction, SFT, SFT validation,
static LTM, and deployment freeze remain explicitly gated.

The formal gate run
`/root/autodl-tmp/apt-agent/experiments/runs/phase10-pre-sft-gate-20260714-002`
confirmed this disposition: the first six stages succeeded; trajectory build,
SFT train/validation, static LTM, and deployment freeze emitted their explicit
blocked reasons and the append-only run terminated with status `blocked`.

No formal trajectory dataset, SFT update, adapter checkpoint, deployable static
LTM, or held-out performance claim exists. These stages remain
`BLOCKED_BY_SFT_DATASET` (and deployment additionally by held-out approval) until
the user-provided dataset passes deployability and split checks.
