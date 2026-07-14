# APT-Agent Tool Capability Specification

Requirements: REQ-GOV-003, REQ-LABEL-001..004, REQ-CONFIG-001..003,
REQ-PIDS-001..005, REQ-TOOL-001..005, REQ-CAUSAL-001..004,
REQ-WINDOW-001..004, REQ-ARTIFACT-001..003, REQ-RESOURCE-001..003,
REQ-REPRO-001..003.

Status: Phase 1.5 design specification for review. This document defines the
boundary between PIDSMaker capabilities and the APT-Agent. It does not define an
SFT dataset, modify an implementation, approve a checkpoint, or make any detector
runnable.

## 1. Scope and source priority

This specification is derived from:

1. `docs/design/APT_Detection_Agent_Design_v0.4.md`;
2. `docs/PIDSMaker_FRAMEWORK_NOTE.md`;
3. `docs/PIDSMaker_CAPABILITY_CATALOG.md`;
4. the existing project contracts, adapter, discovery service, scheduler, and
   result standardizer, inspected only to distinguish implemented primitives from
   proposed interfaces.

The pinned PIDSMaker implementation remains the authority for what a detector
actually computes. Original-paper capabilities are explanatory only. A detector
name never implies that attribution, attack reconstruction, root-cause analysis,
or another paper-level feature is available.

This specification narrows the v0.4 conceptual API in one important respect:
pipeline invalidation and cache effects may be summarized to the Agent, but
pipeline stages themselves are executor-owned and are never writable Agent
arguments.

## 2. Capability-to-action model

The required control chain is:

`PIDSMaker capability → Agent tool → deployment-visible observation → bounded action`

Each boundary removes implementation authority:

| Boundary | What crosses it | What does not cross it |
|---|---|---|
| PIDSMaker → capability registry | Stable detector identity, detection semantics, required state, availability, qualitative cost, limitations | Python module names, YAML internals, CLI flags, CUDA devices, filesystem paths |
| Registry → Agent tool | Opaque approved IDs and bounded typed choices | Arbitrary parameter dictionaries, checkpoint paths, architecture components, pipeline stages |
| Tool → observation | Scores, alerts, runtime, resource pressure, stability, failure, provenance IDs, coarse cache/recompute impact | Labels, private mappings, evaluator metrics, raw PIDSMaker artifacts, commands and environment |
| Observation → action | One enumerated high-level intent with evidence IDs and fallback policy | Shell/CLI, CUDA selection, arbitrary paths, arbitrary numeric search, current-window rewrite |

The Agent chooses *intent*. The trusted executor resolves that intent to an
allowlisted configuration, checkpoint, threshold, resource lease, stage plan,
command, and artifact location. The hidden evaluator is not callable from this
boundary.

## 3. Non-negotiable authority boundary

### 3.1 Agent MUST NOT

The Agent must not:

- invoke CUDA, choose a GPU/device, or set device environment variables;
- construct or submit a CLI, shell command, executable, working directory, or
  environment;
- provide a checkpoint path, artifact path, database connection, or credential;
- select, skip, reorder, or mutate a PIDSMaker pipeline stage;
- select arbitrary encoders, objectives, feature methods, graph transformations,
  datasets, training splits, or numeric hyperparameters;
- request PIDSMaker evaluation or triage, read raw evaluator artifacts, or query
  hidden labels/metrics;
- reinterpret original-paper behavior as an implemented capability;
- revise a prediction already committed for the current or a past window.

These restrictions apply recursively to every tool argument, memory record, error,
and result payload. Encoding a prohibited value inside free text does not make it
permissible.

### 3.2 Agent MAY

The Agent may:

- inspect the registered, sanitized capability of a detector;
- select an opaque detector/config/threshold/resource-preset ID from a catalog
  already approved for the current scenario and split;
- run the current committed detector on the current aligned window;
- compare existing standardized results using label-free signals;
- request a validated reconfiguration for the next window;
- request bounded retraining on the scenario's allowed train/validation inputs;
- cite deployment evidence IDs, state a diagnosis, and select a fallback.

### 3.3 Executor obligations

The executor, not the Agent, must validate split, causality class, configuration,
checkpoint, threshold provenance, resource quota, timing, and artifact identity;
construct the invocation; schedule devices; determine cache reuse and recomputation;
parse raw output; sanitize errors; and fail closed on missing or malformed state.

Persistent changes become effective at the next window. An optional slow-path run
on the current window may provide additional visible evidence, but it cannot alter
the already committed fast-path prediction for that window (REQ-CONFIG-001,
REQ-WINDOW-003).

## 4. Common capability contract

Every detector is represented to the Agent by this conceptual record:

```text
DetectorCapability {
  name
  purpose
  capability_type
  input
  output
  cost
  required_state
  limitations
  available_status
}
```

Field semantics:

| Field | Agent-visible meaning |
|---|---|
| `name` | Stable detector and variant identity; never an implementation path |
| `purpose` | What observable anomaly pattern the implemented detector can score |
| `capability_type` | Controlled vocabulary such as `event_surprise`, `node_role_surprise`, `feature_reconstruction`, `embedding_outlier`, `temporal_event_model`, or `root_context_anomaly` |
| `input` | Scenario/window-level input contract; no raw path or internal tensor shape |
| `output` | Standardized score/alert unit and semantics; no label-derived result |
| `cost` | Validated cost class and optional measured ranges, never device selection |
| `required_state` | Opaque approved config/checkpoint/threshold/reference-state requirements |
| `limitations` | Fidelity, causality, state, output, and compatibility restrictions |
| `available_status` | Split- and scenario-specific admission state with a reason |

`available_status` uses four semantic states:

- `available`: real checkpoint, parser, causal/split approval, and resource profile
  have all passed for this scenario;
- `unavailable`: a known condition prohibits this use;
- `unverified`: registered, but one or more real artifacts or smoke validations are
  missing;
- `blocked`: otherwise eligible, but current runtime state or budget prevents the
  requested call.

Availability is contextual. A detector can be `unavailable` for causal held-out
use and `unverified` as an offline compatibility baseline. Missing checkpoints are
never synthesized.

## 5. Per-PIDS Agent capability records

All statuses below describe the current repository evidence, not a future target.
No detector is currently `available` for real held-out Agent execution.

### 5.1 VELOX

```text
{
  name: velox/default
  purpose: Score unusual event relationships with a lightweight pairwise model.
  capability_type: event_surprise
  input: Current aligned provenance window plus an opaque approved VELOX configuration.
  output: Standardized entity anomaly scores and thresholded entity alerts derived from event surprise.
  cost: low; expected fast-path candidate, pending real project profiling.
  required_state: Train-only feature model, approved checkpoint, validation-derived threshold, compatible entity/event vocabulary, and validated result parser.
  limitations: Limited long-range structure; node alerts aggregate event evidence; no reconstruction, attribution, or root-cause output.
  available_status: unverified — causal candidate, but no approved real checkpoint, complete per-PIDS parser validation, or resource profile.
}
```

### 5.2 ORTHRUS

```text
{
  name: orthrus/{default|non_snooped|fixed}
  purpose: Score event-type surprise while incorporating local temporal graph context.
  capability_type: temporal_event_surprise
  input: Ordered aligned provenance windows plus an opaque approved ORTHRUS variant configuration.
  output: Standardized node or edge anomaly scores and thresholded alerts according to the approved variant.
  cost: medium; temporal neighborhood processing and attention are heavier than VELOX, pending real profiling.
  required_state: Explicit variant identity, approved checkpoint and threshold, ordered/reset temporal state, compatible vocabulary, and validated parser.
  limitations: Default feature fitting is transductive; optional clustering may also be non-causal; published attribution graphs are not canonical PIDSMaker output.
  available_status: unavailable for default causal held-out use; non_snooped remains unverified pending checkpoint, parser, reset, and resource validation.
}
```

### 5.3 MAGIC

```text
{
  name: magic/default
  purpose: Detect node embedding outliers after masked graph representation learning.
  capability_type: embedding_outlier
  input: Current provenance graph with supported node/relation types and an approved reference embedding state.
  output: Standardized per-node outlier scores and thresholded node alerts.
  cost: medium_to_high; graph attention, masked objectives, and nearest-neighbor scoring require profiling.
  required_state: Approved checkpoint, frozen benign reference/index, validation-only threshold statistics, compatible graph schema, and validated parser.
  limitations: Pinned scoring/threshold path consults test data; no original-paper reconstruction output; graph semantics differ from assumptions often inferred from the paper.
  available_status: unavailable for causal held-out use because the pinned inference/evaluation path leaks test information.
}
```

### 5.4 FLASH

```text
{
  name: flash/default
  purpose: Detect unexpected entity roles from semantic and positional node representations.
  capability_type: node_role_surprise
  input: Current aligned graph plus a frozen node-document representation and approved FLASH configuration.
  output: Standardized per-node confidence/anomaly scores and thresholded node alerts.
  cost: medium; feature-document construction and GraphSAGE inference require real measurement.
  required_state: Causally fitted feature corpus, approved checkpoint, validated fixed/calibrated threshold, compatible attributes, and parser.
  limitations: Pinned feature inference scans train, validation, and test; original embedding-database/XGBoost workflow is absent; fixed threshold portability is unverified.
  available_status: unavailable for causal held-out use until feature construction is made and validated as causal.
}
```

### 5.5 KAIROS

```text
{
  name: kairos/default
  purpose: Model ordered temporal interactions and score anomalous event behavior with persistent temporal state.
  capability_type: temporal_event_model
  input: Strictly ordered aligned windows, an opaque approved configuration, and executor-owned temporal state.
  output: Standardized entity anomaly scores and alerts from event losses in the currently selected PIDSMaker configuration.
  cost: high; stateful temporal graph processing has nontrivial memory and sequencing cost.
  required_state: Approved checkpoint/threshold, initialized state, exact ordering, reset/replay policy, resource profile, and validated parser.
  limitations: Current canonical output is node scoring, not the original queue detector or investigation graph; replay/reset errors invalidate results.
  available_status: unverified compatibility capability; no approved real checkpoint, state-lifecycle validation, parser, or resource profile.
}
```

### 5.6 NODLINK

```text
{
  name: nodlink/default
  purpose: Detect entities whose semantic node features are poorly reconstructed from graph context.
  capability_type: feature_reconstruction
  input: Current transformed provenance graph plus a train-only frozen semantic representation and approved configuration.
  output: Standardized per-node reconstruction scores and validation-thresholded node alerts.
  cost: medium; undirected expansion and variational feature reconstruction require profiling.
  required_state: Train-only feature model, approved checkpoint, validation quantile threshold, schema compatibility, and parser.
  limitations: Original online cache, STP logic, and attack-graph output are absent; undirected transformation changes graph semantics.
  available_status: unverified — causal candidate, but checkpoint, parser, output fidelity, and resource profile are not approved.
}
```

### 5.7 ThreatRace

```text
{
  name: threatrace/default
  purpose: Detect entities whose observed graph context is inconsistent with their expected node role.
  capability_type: node_role_surprise
  input: Current provenance graph with supported node types and edge-distribution features under an approved configuration.
  output: Standardized per-node role-surprise score/ratio and thresholded node alerts.
  cost: medium; GraphSAGE neighborhood aggregation requires real profiling.
  required_state: Approved checkpoint, validated threshold, compatible node/relation schema, and per-PIDS parser.
  limitations: Original multi-model lifecycle, retraining policy, and tracing are absent; fixed threshold generalization is unverified.
  available_status: unverified — registered causal candidate with no approved checkpoint, parser, or real resource profile.
}
```

### 5.8 R-CAID

```text
{
  name: rcaid/default
  purpose: Detect anomalous nodes while incorporating long-range causal-root context.
  capability_type: root_context_anomaly
  input: Current aligned graph plus an executor-created causal pseudo-graph and approved R-CAID configuration.
  output: Standardized per-node anomaly scores and thresholded node alerts.
  cost: high; pseudo-root expansion/pruning and multi-layer attention can increase memory and runtime substantially.
  required_state: Causally fitted semantic features, approved checkpoint/threshold, validated pseudo-graph timing, resource profile, and parser.
  limitations: Pinned Doc2Vec fitting is transductive; pseudo-edge timing needs causal validation; clustering/root-cause output from the paper is absent.
  available_status: unavailable for causal held-out use; offline compatibility use remains unverified.
}
```

## 6. Unified high-level Agent tools

Detector-specific public functions would couple the Agent to PIDSMaker internals and
make capability comparison inconsistent. The public API therefore uses one set of
tools for all detectors. PIDS-specific behavior is selected only through a stable
registry identity and an approved catalog entry.

### 6.1 `inspect_detector_capability`

**Purpose.** Return what a detector can actually do in the current scenario before
the Agent selects it. This prevents selection by paper reputation or detector name.

```text
input:  {detector_id, optional variant_id, scenario_id, intended_use}
output: {purpose, capability_type, detection_unit, cost_class,
         required_state_status, limitations, available_status,
         approved_candidate_ids}
```

The output contains no source path, YAML, module name, checkpoint path, raw config,
or private metric. This tool is needed because availability depends on scenario,
split, variant, checkpoint, causality, parser, and resources rather than registration
alone.

### 6.2 `run_pids_detection`

**Purpose.** Apply either the current committed detector or one already approved as
a bounded slow-path investigation to an identified current window.

```text
input:  {case_id, window_id, execution_intent: committed|approved_investigation,
         optional approved_candidate_id}
output: {result_id, detector_id, config_id, threshold_id, checkpoint_id,
         score_summary, alerts, runtime_summary, resource_summary,
         execution_status, provenance_id}
```

The executor resolves all internal arguments. `approved_investigation` cannot
overwrite the committed result. The tool fails closed if the candidate is not
approved for the split, the checkpoint/threshold identity does not match, the
window is misaligned, or standardized output cannot be produced.

This is needed to give every PIDS one stable inference interface despite their
different internal objectives and output files.

### 6.3 `compare_detector_results`

**Purpose.** Compare two or more already-produced standardized results using only
deployment-visible evidence.

```text
input:  {result_ids, comparison_profile_id}
output: {same_window, score_distribution_comparison, alert_overlap,
         alert_volume_comparison, runtime_comparison, resource_comparison,
         stability_comparison, comparable_fields, cautions}
```

The tool does not calculate accuracy, rank a detector by correctness, reveal which
alerts are malicious, or choose a winner using hidden evaluation. Results with
different windows, detection units, score semantics, or non-comparable calibration
must be explicitly marked rather than coerced into one number.

This is needed because slow-path diagnosis may need to distinguish score delivery,
capability mismatch, instability, and resource failure without labels.

### 6.4 Supporting unified tools

| Tool | High-level input | Deployment-visible output | Why needed |
|---|---|---|---|
| `inspect_active_detection_state` | `case_id` | Active detector/config/threshold/checkpoint IDs, health, pending change, coarse cache/recompute status | Grounds decisions in committed state without exposing internal paths |
| `select_validated_threshold` | `case_id`, `threshold_candidate_id` | Validation provenance summary, expected alert-volume effect, next-window effective sequence | Implements bounded threshold action without free numeric generation |
| `load_approved_config` | `case_id`, `approved_config_id` | Compatibility/admission result and next-window pending state | Reuses a frozen catalog entry atomically |
| `switch_detector` | `case_id`, `approved_candidate_id` | Admission result, state-reset requirement, cost class, next-window pending state | Separates capability selection from implementation details |
| `retrain_detector` | `case_id`, `training_recipe_id` | Run status, training/validation summaries, new candidate ID or sanitized failure | Provides a bounded high-cost lifecycle operation using only allowed splits |
| `select_resource_preset` | `case_id`, `resource_preset_id` | Admission, expected cost class, retry policy, pending execution state | Handles OOM/timeout without exposing GPU IDs or arbitrary batching values |

These tool names describe Agent intent. Internally they may reuse discovery,
catalog, scheduler, adapter, and parser components, but that composition is not part
of the Agent contract.

## 7. Agent-visible observation

### 7.1 Observation contract

The Agent receives a compact, versioned record composed only of evidence available
in a real deployment:

```text
AgentVisibleObservation {
  schema_version
  observation_id
  case_id
  scenario_id
  episode_id
  split
  observed_at

  window: {
    window_id, sequence_number, start, end, timezone, window_size_seconds
  }

  environment: {
    environment_profile_id,
    platform_class,
    provenance_schema_id,
    node_count,
    edge_count,
    entity_type_distribution,
    relation_type_distribution,
    event_rate,
    graph_density,
    normal_reference_status
  }

  active_detection: {
    detector_id,
    variant_id,
    capability_type,
    committed_config_id,
    checkpoint_id,
    threshold_id,
    score_semantics,
    detection_unit,
    state_health,
    pending_change_id,
    pending_effective_sequence
  }

  detection_signal: {
    score_count,
    score_minimum,
    score_maximum,
    score_mean,
    score_quantiles,
    tail_mass,
    alert_count,
    alert_ratio,
    alert_entity_ids,
    alert_score_bands,
    recent_score_shift,
    recent_alert_volume_shift,
    instability_indicators,
    degeneracy_indicators
  }

  execution: {
    status,
    elapsed_seconds,
    cpu_time_seconds,
    peak_memory_class,
    gpu_time_seconds,
    gpu_memory_pressure_class,
    timeout_indicator,
    oom_indicator,
    sanitized_failure_code,
    cache_reuse_class,
    recomputation_scope,
    provenance_id
  }

  capability_options: [{
    detector_id,
    variant_id,
    capability_type,
    available_status,
    cost_class,
    limitation_codes,
    approved_candidate_ids
  }]

  budget: {
    remaining_slow_path_calls,
    remaining_retraining_calls,
    remaining_wall_time_class,
    token_usage_so_far
  }

  memory: {
    retrieved_record_ids,
    applicability_summaries,
    conflict_indicators
  }
}
```

`checkpoint_id` is an opaque immutable identity or hash, never a path.
`cache_reuse_class` is `full`, `partial`, `none`, or `unknown`.
`recomputation_scope` is a semantic class such as `inference_only`,
`configuration_dependent`, or `training_required`; it is not a list of writable
PIDSMaker stages.

The graph statistics are summaries computed from the current and past visible
windows. They must not be annotated with malicious/benign status. Alert entity IDs
are detector outputs and therefore deployment-visible; their true class is not.

### 7.2 Explicitly forbidden observation content

No Agent-visible observation, tool result, error, memory, report, or rationale may
contain:

- `label`, ground truth, benign/malicious annotations, or label-bearing tensors;
- TP, FP, FN, TN, precision, recall, F1, MCC, ADP, ROC-AUC, average precision,
  campaign coverage, or another label-derived metric;
- attack ID, campaign ID, attack name, attack time/window mapping, or private
  campaign membership;
- teacher-only rationale, counterfactual best action, or per-alert correctness;
- raw PIDSMaker evaluation/triage output, private database rows, hidden artifact
  paths, or unsanitized exceptions;
- CLI, argv, CUDA/device state, checkpoint path, internal YAML, module path, or
  mutable stage plan.

The prohibition is semantic, not merely key-name based. For example, “three of five
alerts were correct” is forbidden even if it does not use the string `TP`.

## 8. Action alignment and current implementation status

### 8.1 Status vocabulary

To avoid overstating readiness, action status is assessed at four layers:

1. **contract** — strict types and invariants exist;
2. **primitive** — reusable catalog/adapter/scheduler/parser logic exists;
3. **Agent tool** — the named high-level tool and state transition exist end to end;
4. **real validation** — real checkpoint, parser, resource profile, and remote smoke
   have passed.

Only layers 3 and 4 together justify “implemented and available.” Synthetic tests
prove contract behavior, not real detector availability.

### 8.2 v0.4 action matrix

| v0.4 action | Required unified tool | What exists now | What must be added | Current assessment |
|---|---|---|---|---|
| `KEEP_AND_INFER` | `run_pids_detection` with `committed` intent | Typed detection request/result, frozen-config validation, executor-owned argv/environment, scheduler primitives, controller committed fast path, and a narrow VELOX-oriented standardizer | A true current-window service binding, per-PIDS standardized parsers, approved checkpoints/thresholds, production credential injection, real resource profiles and smoke runs | **Partially implemented; no real PIDS currently available** |
| `ADJUST_THRESHOLD` | `select_validated_threshold` | Threshold provenance schema and validation-quantile calibration primitive; controller supports next-window pending configuration semantics | Threshold candidate catalog for each detector/dataset, named tool/handler, alert-volume preview, atomic threshold/config commit, non-VELOX parser support and real validation | **Primitive only; high-level action must be added** |
| `SWITCH_PIDS` | `switch_detector` | Eight-detector discovery, variant identity, availability status, frozen ApprovedConfig selection, resource admission, and pending configuration schema | Atomic switch tool, capability/compatibility gate, checkpoint and parser admission, state reset/warm-up policy, rollback, next-window activation, real profiles | **Substantial primitives; end-to-end action must be added** |
| `LOAD_TUNED_CONFIG` | `load_approved_config` | Frozen ApprovedConfig catalog selection and split/identity validation | Populated reviewed catalog, named load tool, compatibility and cache-impact result, atomic next-window commit/rollback, real tuned artifacts | **Catalog primitive only; high-level action must be added** |
| `RETRAIN_CURRENT_PIDS` | `retrain_detector` | Training-related stage runner/provenance contracts and bounded causal-run research path exist; adapter records execution/artifacts | Approved recipe catalog, train/validation-only lifecycle, W&B-free upstream compatibility, reliable checkpoint save/verify, model promotion gate, asynchronous status/recovery, per-PIDS real smoke | **Research primitive only; action must be added** |
| `ADJUST_RESOURCE_CONFIG` | `select_resource_preset` | Explicit resource profile, executor-owned GPU placement, quota admission, thread limits, and unknown-workload concurrency gate | Validated discrete preset catalog, named selection/retry tool, per-PIDS measured profiles, OOM/timeout policy, pending-state and rollback semantics | **Scheduler implemented; Agent reconfiguration action must be added** |

`KEEP_AND_INFER` is the closest to an implemented path, but the adapter defaults to
execution disabled and current discovery has no approved real detector checkpoints.
It must not be labeled available merely because adapter and synthetic tests pass.

### 8.3 Action output contract

Every slow-path action decision should return:

```text
ActionDecision {
  action_id
  action_type
  diagnosis_code
  visible_evidence_ids
  requested_tool
  approved_choice_id
  expected_effect
  recomputation_scope
  cache_reuse_class
  effective_sequence_number
  confidence
  commit_policy
  fallback_policy
}
```

`approved_choice_id` is an opaque catalog identity. `expected_effect` must be phrased
in deployment-visible terms such as lower alert volume, different anomaly
capability, or lower resource pressure; it must not predict hidden accuracy.
`effective_sequence_number` must be the next window or later for persistent changes.

## 9. End-to-end interaction rules

### 9.1 Normal fast path

1. The aligned window closes and the executor runs the committed detector through
   `run_pids_detection`, without Agent-supplied implementation parameters.
2. Standardized scores and alerts are committed once.
3. The harness emits `AgentVisibleObservation` from the committed result and other
   deployment-visible state.
4. If no deployment-visible trigger fires, `KEEP_AND_INFER` means preserving the
   committed configuration for the next window; it does not rerun or rewrite the
   current-window result.

### 9.2 Slow-path capability change

1. A fixed validation-derived trigger or periodic checkpoint invokes diagnosis.
2. The Agent inspects candidate capabilities and optional existing result
   comparisons.
3. The Agent selects one approved high-level action and cites visible evidence IDs.
4. The executor validates availability and resolves all internal execution details.
5. A successful persistent change is scheduled for the next window; failure invokes
   the declared fallback.
6. The current-window committed prediction remains unchanged.

### 9.3 Fail-closed conditions

A tool returns `unavailable`, `blocked`, or sanitized failure—not partial success—if
any of the following holds:

- detector/config/checkpoint/threshold identity mismatch;
- missing checkpoint, parser, required reference state, or artifact;
- detector not approved for the scenario, split, or causality class;
- malformed, non-finite, out-of-window, or label-bearing raw output;
- insufficient resource lease, timeout, OOM, or state reset/order violation;
- request includes executor-owned fields or an unapproved candidate;
- a persistent change attempts to affect the current or a past window.

## 10. Acceptance criteria for a future implementation phase

This specification is satisfied only when:

- every Agent tool accepts a strict high-level schema and rejects recursive
  executor-owned fields;
- all eight PIDS remain discoverable even when unavailable, with explicit reasons;
- a real detector becomes `available` only after checkpoint, parser, causal/split,
  threshold, resource, and smoke validation;
- each per-PIDS parser emits the same versioned deployment result contract while
  preserving detector-specific score semantics and detection unit;
- result comparison is label-free and refuses incomparable results;
- reconfiguration becomes effective no earlier than the next window;
- tool results expose opaque provenance and coarse cost/cache effects, not internal
  paths, commands, devices, or stage controls;
- nested leakage tests reject labels, TP/FP/FN, MCC, attack IDs, private mappings,
  teacher rationale, and semantic paraphrases of privileged evidence;
- failures, timeouts, missing artifacts, and unavailable checkpoints fail closed;
- real remote smoke evidence is recorded before any capability is promoted from
  `unverified` to `available`.

## 11. Phase 1.5 conclusion

PIDSMaker supplies heterogeneous detector mechanisms; the Agent should not operate
those mechanisms directly. The stable public abstraction is a small set of unified,
high-level tools over an executor-owned approved catalog. Observations describe
what the deployment can see—graph behavior, scores, alerts, state, cost, stability,
and failure—not whether the detector was correct.

At the present repository state, the authority boundary and many supporting
primitives exist, but none of the eight PIDS has sufficient real evidence to be
advertised as an available held-out Agent capability. Phase 1.5 therefore defines
the contract and its readiness gaps without inventing artifacts or expanding into
dataset design.
