# Phase 1 schema contracts

Requirements: REQ-LABEL-001..004, REQ-TOOL-001..005,
REQ-CONFIG-001..003, REQ-WINDOW-001..003, REQ-MEMORY-001..006,
REQ-EVAL-001..004, REQ-ARTIFACT-001..003.

All contracts inherit from an immutable Pydantic base with `extra="forbid"`.
Undeclared fields therefore fail closed instead of being silently dropped. Public
Agent/controller schemas are exported from `apt_detection_agent.schemas`.
Privileged campaign, ground-truth, and complete evaluation records are exported
only from `apt_detection_agent.evaluator` and must be hosted by the later isolated
evaluator process.

## Public Agent/controller surface

- Deployment input: `TimeWindow`, `Observation`, `ScoreSummary`, `DetectionAlert`.
- Decision: `AgentAction`, `ToolRequest`, `PendingConfiguration`, `CaseState`.
- Executor result: `CommandManifest`, `StageTrace`, `ToolResult`.
- PIDS/config: `PIDSRef`, `PIDSCapability`, `ApprovedConfig`,
  `ThresholdProvenance`.
- State: `MemoryRecord`, `StaticLTMSnapshot`, `Prediction`.
- Provenance: `ArtifactRecord`, `ArtifactManifest`, `RunManifest`.
- Sanitized evaluator output: training-only `TrainingStepFeedback` and
  validation/held-out `EpisodeMetricsFeedback`.

`ToolRequest.arguments` rejects executor-owned command, shell, environment, working
directory, and CUDA-device fields recursively. PIDSMaker requests are validated by
the tool-specific types in `src/apt_detection_agent/pidsmaker/tools.py`; memory,
case, and visible-report requests are validated by the tool-specific types in
`src/apt_detection_agent/tooling/memory_tools.py`. The generic outer request remains
the transport envelope, while each executor establishes its narrower allowlist.

## Privileged evaluator surface

`CampaignManifest`, `HiddenGroundTruth`, and `EvaluationRecord` are intentionally
absent from the public schema export. `assert_deployable_payload` rejects known
privileged field names recursively before teacher output, memory, or other generic
payloads can cross into a student/Agent-visible boundary.

Schema separation supplements rather than replaces Phase 7 process, filesystem, and
database-role isolation.

## Versioning and serialization

Top-level online exchange contracts carry `schema_version`. Manifests and records
carry immutable IDs, hashes, timestamps, and code/config provenance appropriate to
their lifecycle. Datetimes require explicit UTC offsets; windows additionally
validate IANA timezone offset, alignment, duration, and sequence number.
