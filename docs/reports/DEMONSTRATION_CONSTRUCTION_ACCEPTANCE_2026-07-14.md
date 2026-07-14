# Pre-SFT demonstration construction acceptance — 2026-07-14

Requirements: REQ-SFT-001..010, REQ-PIDS-001..006, REQ-RUNTIME-001..006,
REQ-LABEL-001..004, REQ-REPRO-001..003.

## Accepted implementation

The project can construct and validate the public side of an SFT corpus without a
formal dataset or performance claim:

- `src/apt_detection_agent/sft/demonstration.py` defines hashed public manifests,
  execution rows, OfflineRunRecords, visible grounding, paired exchanges,
  canonical trajectories, and typed rejections;
- `src/apt_detection_agent/sft/demonstration_builder.py` creates deterministic
  counterfactual groups, joins capabilities to exact admission/configuration
  records, validates admitted success, and reports coverage;
- `src/apt_detection_agent/evaluator/demonstration.py` keeps private links and
  teacher selection outside the student namespace and rejects rationale fields,
  out-of-set targets, and unique targets under public ambiguity;
- the sanitizer checks privileged field names and semantic leakage phrases;
- the exporter produces deterministic canonical/OpenAI-compatible transcripts
  where only assistant messages contribute loss;
- `scripts/build_synthetic_demonstrations.py` exercises the public contract and
  refuses to overwrite a run directory.

## AutoDL evidence

Commit: `0e1955d0d93e1137174398da890652219a580dbc`.

- focused warnings-as-errors suite: 7/7 passed;
- complete suite: 275/275 passed in 14.741 seconds;
- PIDSMaker remained pinned at
  `32602734bc9f896be5fc0f03f0a185c967cd6624`;
- source runtime run:
  `/root/autodl-tmp/apt-agent/frozen-runtime-runs/frozen-runtime-demo-source-20260714-001`;
- accepted construction smoke:
  `/root/autodl-tmp/apt-agent/demonstration-runs/demonstration-contract-20260714-002`.

The smoke dynamically found 10 source configs/variants representing FLASH,
KAIROS, MAGIC, NODLINK, ORTHRUS (three variants), R-CAID, ThreatRace, and VELOX.
It emitted 10 execution-matrix rows, 10 public OfflineRunRecords, one canonical
trajectory, one OpenAI-compatible JSONL trajectory, a coverage report, and an
empty rejection ledger. Every row is capability-only. The run records
`source_admission_count=0`, `successful_tool_use_count=0`,
`formal_training_approved=false`, and `synthetic_only=true`.

## Remaining gates

This acceptance does not cover a real demonstration pilot. Per-PIDS real parsers
and successful/failure examples require exact dataset/config/checkpoint/threshold/
resource/state evidence and an all-eight-gates admission. The real multi-dataset
pilot also requires the user-provided agent-training material and private companion
manifests. Until those inputs pass sanitization, evidence closure, group-disjoint
split, and coverage review, SFT weight updates, static-LTM distillation, held-out
evaluation, and deployment remain blocked.
