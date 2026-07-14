# Hidden evaluation and metric definitions

Requirements: REQ-LABEL-001..004, REQ-EVAL-001..006, REQ-DB-001..003.

Metric definition version: `agent-eval-v1`.

The hidden evaluator is a separate process entrypoint at
`scripts/run_hidden_evaluator.py`. Its request and full output must remain under an
evaluator-private filesystem root. The Agent-visible root receives only an
`EpisodeMetricsFeedback` artifact reference for validation/held-out. Agent-training
may receive a predefined scalar step reward; other splits cannot.

Definitions:

- campaign coverage: fraction of versioned campaign manifests having at least one
  alerted malicious entity;
- unique-node TP/FP/FN: set operations over formal alerted entity IDs and the union
  of malicious entities in the manifests;
- P@C=100%: entity precision at the highest score threshold at which every campaign
  has at least one detected malicious entity; equal-score entities enter together;
- MCC: standard binary Matthews correlation coefficient over the declared unique
  entity universe, returning zero for a zero denominator;
- ADP: trapezoidal area under the campaign-coverage-versus-entity-precision curve,
  derived from the PIDSMaker Average Detection Precision intent at
  `PIDSMaker/pidsmaker/detection/evaluation_methods/evaluation_utils.py:633-710`,
  but using versioned campaign manifests and deterministic score-threshold groups;
- node-window occurrences, malicious-edge recovery, attack-chain edge recovery,
  phase recovery, evidence provenance completeness, latency, GPU time, and tool
  calls are separate maps with explicit independent denominators.

Campaign identity never comes from a ground-truth filename. Node-window truth is an
explicit private pair set; it is not fabricated as the Cartesian product of campaign
windows and entities.

The database role contract requires four distinct roles: manual admin/migration,
PIDS worker, read-only hidden evaluator, and Agent controller. The controller role
has no private-schema access. Phase 7 validates the policy and filesystem IPC but
does not create roles or change PostgreSQL; live grants remain a manual deployment
gate.

`src/apt_detection_agent/evaluator/calibration.py` implements the private
`campaign-coverage-calibration-v1` workflow. It accepts only validation data, a
versioned nonempty agent-level campaign manifest, unique scored entities, a declared
universe, checkpoint hash, and code commit. It selects the highest tied-score-safe
threshold satisfying the requested campaign coverage and emits complete
`ThresholdProvenance`. Held-out/deployment and benign-only inputs fail closed. The
calibration result remains evaluator-private until its threshold record is reviewed,
frozen, and added to the ApprovedConfig catalog; it is never online Agent feedback.
