# Completion audit — 2026-07-14 (revised)

Requirements: REQ-GOV-001..004, REQ-GIT-001..003, REQ-CAUSAL-001..004,
REQ-LABEL-001..004, REQ-TOOL-001..005, REQ-MEMORY-001..007,
REQ-EVAL-001..007, REQ-ARTIFACT-001..003, REQ-DB-001..003,
REQ-WANDB-001, REQ-REPRO-001..003, REQ-SFT-001..004.

## Revised disposition

All implementation and bounded validation work possible before the formal SFT
trajectory dataset is complete. The earlier Phase 8/9 infrastructure blockers are
closed: tmux is installed; least-privilege PostgreSQL roles and separate OS
identities are live; a versioned compatibility patch runs outside the clean pinned
submodule; exact windows, causal checkpointing, W&B-free training, frozen
featurization, standardized scores, hidden evaluation, and new-window inference
have real AutoDL evidence.

| Phase | Disposition | Scope limit |
|---|---|---|
| 0–7 | accepted | metrics and policy contracts remain subject to later empirical validation |
| 8 | bounded causal smoke accepted | VELOX/CADETS validation only; other registry entries remain unavailable/unverified |
| 9 | bounded real validation accepted | no held-out or formal performance claim |
| 10 | pre-SFT complete | formal SFT, deployable static LTM, and deployment bundle blocked by missing dataset/approval |

## Evidence

- pinned PIDSMaker:
  `32602734bc9f896be5fc0f03f0a185c967cd6624`;
- causal run:
  `/root/autodl-tmp/apt-agent/experiments/runs/phase8-velox-cadets-smoke-20260714-002`;
- real validation:
  `/root/autodl-tmp/apt-agent/experiments/runs/phase9-real-e2e-20260714-002`;
- frozen validation bundle:
  `/root/autodl-tmp/apt-agent/pre-sft-bundles/velox-cadets-validation-3fa5ec0-002`;
- frozen later-window run:
  `/root/autodl-tmp/apt-agent/experiments/runs/phase10-frozen-new-window-20260714-001`;
- checkpoint hash:
  `9fd5b64fd65f71faea65b037294dca537c75ab902a4ad92f04bb84315c0f54a2`;
- featurizer hash:
  `965911178ec53c3c6dc2efc61eb1e365b4c253168ee38df586d44582b4e58cab`;
- AutoDL commit `39c360856362e35143916690a9e428aa79a72699`:
  213/213 tests passed;
- formal pre-SFT gate run:
  `/root/autodl-tmp/apt-agent/experiments/runs/phase10-pre-sft-gate-20260714-002`.

The later-window run produced 8,394 label-free scores with the exact frozen hashes,
`featurizer_fit_on_current_window=false`, `test_labels_loaded=false`, and
`formal_performance_claim=false`. Controller permission checks denied access to raw
scores, evaluator-private files, source checkout, and evaluator runtime.

## Remaining non-bypassable gates

1. The user-provided formal trajectory dataset must pass teacher/student
   sanitization, deployability, deduplication, and disjoint split checks.
2. SFT training/validation and static-LTM distillation must use only approved
   agent-training data; validation/held-out episode memory cannot flow backward.
3. The full validation campaign set must finish before any held-out threshold,
   routing policy, PIDS selection, or deployment bundle is frozen.
4. Other PIDS remain in the capability registry with explicit unavailable reasons
   until independent data/checkpoint/resource smokes pass.
5. Transductive baselines and retrieval/trigger sensitivity experiments remain
   separate empirical work and cannot be relabeled as the causal main result.

Accordingly “pre-SFT implementation complete” is accurate. “Formal training
complete,” “held-out validated,” and “deployment ready” are not yet accurate.
