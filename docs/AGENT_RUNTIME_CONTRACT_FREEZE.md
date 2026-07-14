# APT-Agent Runtime Contract Freeze

Requirements: REQ-GOV-003, REQ-CAUSAL-001..004, REQ-LABEL-001..004,
REQ-WINDOW-001..004, REQ-CONFIG-001..003, REQ-PIDS-001..005,
REQ-TOOL-001..005, REQ-MEMORY-001..007, REQ-ARTIFACT-001..003,
REQ-RESOURCE-001..003, REQ-REPRO-001..003.

Status: Phase 1.6 normative design freeze for review. This document freezes the
runtime contract required before formal trajectory collection. It does not define
an SFT dataset, generate trajectories, run training, approve any PIDS, or change
runtime code.

## 1. Sources, authority, and superseded terminology

This contract reconciles:

1. `docs/design/APT_Detection_Agent_Design_v0.4.md`;
2. `docs/PIDSMaker_FRAMEWORK_NOTE.md`;
3. `docs/PIDSMaker_CAPABILITY_CATALOG.md`;
4. `docs/AGENT_TOOL_CAPABILITY_SPEC.md`.

When this document deliberately narrows an earlier runtime term, this document is
normative for the frozen runtime contract. It does not change the underlying v0.4
research objectives.

The following names are superseded at the Agent boundary:

| Earlier term | Frozen runtime term | Reason |
|---|---|---|
| `KEEP_AND_INFER` | `KEEP_CURRENT_CONFIG` | Committed inference already happened automatically; the Agent must not request a second current-window run |
| `ADJUST_THRESHOLD` | `SELECT_VALIDATED_THRESHOLD` | The Agent selects an approved candidate, not an arbitrary numeric threshold |
| `LOAD_TUNED_CONFIG` | `LOAD_APPROVED_CONFIG` | “Tuned” is insufficient; split, checkpoint, causality, parser, and provenance approval are required |
| `SWITCH_PIDS` | `SWITCH_DETECTOR` | Stable public terminology must not imply direct PIDSMaker control |
| `RETRAIN_CURRENT_PIDS` | `RETRAIN_DETECTOR` | Retraining creates a candidate and does not automatically replace the committed detector |
| `ADJUST_RESOURCE_CONFIG` | `SELECT_RESOURCE_PRESET` | Resources are selected from executor-owned presets, never free parameters |

`KEEP_AND_INFER` is forbidden in new runtime schemas, prompts, trajectories, and
reports. Historical documents may retain the term as provenance, but readers must
interpret it only as `KEEP_CURRENT_CONFIG` after the current window has already
been inferred and committed.

## 2. Frozen runtime invariants

The following invariants are non-negotiable:

1. Each aligned `[start,end)` construction window is processed once, in
   chronological sequence.
2. The committed fast-path detector/config/checkpoint/threshold state is fixed
   before the window closes.
3. Committed fast-path inference is a harness-internal operation, not an LLM tool
   choice.
4. A current-window result is append-only once committed, including an explicit
   failed-result record when inference fails.
5. Observation and trigger decisions are constructed only after result commit.
6. The trigger uses only deployment-visible, validation-frozen rules.
7. If no trigger fires, the harness records the default
   `KEEP_CURRENT_CONFIG` outcome without creating an assistant turn.
8. The LLM runs only on the optional slow path.
9. Additional detector runs are investigative, separately identified, and cannot
   replace or merge into the committed current-window result.
10. Persistent detector, config, threshold, and detection-resource changes take
   effect no earlier than the next window.
11. Hidden evaluation cannot feed the runtime loop, memory, prompt, tool result, or
    state transition.

## 3. Strict causal order for one window

### 3.1 Normative sequence

For window `W_t`, the only valid order is:

```text
window close
→ committed fast-path inference
→ result commit
→ observation construction
→ trigger decision
→ optional slow path
→ next-window state transition
```

The order cannot be shortened by moving the trigger or LLM before result commit,
and it cannot be reversed by applying a slow-path result to `W_t`.

| Order | Operation | Owner | LLM decision? | Contract |
|---:|---|---|---|---|
| 1 | Close `W_t` | Harness | No | Verify alignment, end time, sequence, and absence of future events |
| 2 | Snapshot committed state | Harness | No | Bind detector, approved config, checkpoint, threshold, reset/state token, and resource preset already effective for `W_t` |
| 3 | Run committed fast-path inference | Harness/executor | No | Execute exactly the bound state; the LLM cannot supply detector or executor arguments |
| 4 | Validate and commit result | Harness | No | Parse, sanitize, validate provenance/window identity, then append one immutable committed-result or explicit failure record |
| 5 | Construct execution/canonical observations | Harness | No | Build RawExecutionState and CanonicalAgentVisibleObservation deterministically |
| 6 | Decide trigger | Harness | No | Apply a pre-frozen label-blind trigger profile; if false, record harness-default `KEEP_CURRENT_CONFIG` and skip the LLM |
| 7 | Run optional slow path | LLM Agent + harness tools | Yes, only here | If triggered, build ModelPromptObservation from canonical state plus trigger reasons, then run memory read/use and one bounded action cycle; additional evidence remains non-committed |
| 8 | Validate pending transition | Harness | No | Admit or reject the requested future state; never mutate `W_t` |
| 9 | Activate state for `W_{t+1}` | Harness | No | Atomically promote an admitted pending state at the next-window boundary |

### 3.2 Automatic harness behavior

The harness automatically performs window closure, state binding, committed
inference, parsing, result commit, all observation transformations, trigger
evaluation, tool validation/execution, memory retrieval/write validation, pending
state validation, failure handling, audit logging, and next-window activation.

The harness also determines CLI/argv, environment, device, resource lease,
checkpoint location, internal pipeline work, cache reuse, artifact paths, and
process isolation. None are LLM outputs.

### 3.3 LLM Agent behavior

When and only when the harness opens a slow path, the LLM may:

- decide whether memory retrieval is needed and form an allowlisted query;
- decide how to use returned memories;
- diagnose the deployment-visible symptom;
- choose one action from the frozen action taxonomy;
- select only opaque approved candidate IDs permitted by that action;
- propose an optional sanitized memory write candidate;
- declare confidence and a fallback.

The LLM does not decide whether the committed fast path runs, whether a result is
committed, whether the trigger fires, or when a pending state is activated.

Every control-decision record carries `decision_source`. It is
`harness_default` for an untriggered `KEEP_CURRENT_CONFIG` and `llm_agent` for a
slow-path action. A harness default is runtime provenance, not a fabricated
assistant message.

### 3.4 Failure semantics

A failed committed inference is itself committed as a typed failure, not converted
to an empty benign result. Observation construction records only a sanitized
failure code and deployment-visible resource/health evidence. The failure triggers
slow diagnosis according to the frozen trigger profile.

An additional detector may investigate the same closed window after this failure,
but its result does not retroactively become the committed fast-path result. Whether
a separate pre-commit automatic safety fallback is required has no supporting
evidence and is listed as `UNRESOLVED_REQUIRES_EXPERIMENT`.

## 4. Frozen fast-path and slow-path detection boundary

### 4.1 Committed fast path

Committed detector inference is an internal operation with an internal request
identity such as `CommittedFastPathInferenceRequest`. It is created only by the
harness from the state snapshot for `W_t`. It is not present in the Agent tool
catalog and requires no assistant turn.

Its result must carry:

- `execution_role = committed_fast_path`;
- scenario, episode, window, and sequence identities;
- committed config, detector, checkpoint, threshold, and resource-preset IDs;
- standardized scores/alerts or explicit failure status;
- immutable result and artifact provenance;
- start/end timing and sanitized resource summary.

Exactly one committed result identity exists per scenario/episode/window. Retries,
if a future policy permits them, remain attempts under the same transaction and
must never create multiple committed predictions.

### 4.2 Approved additional detector run

The only detector execution an Agent may request is
`RUN_ADDITIONAL_DETECTOR`, backed by a public high-level tool such as
`run_additional_detector`.

The request contains only:

```text
{
  case_id,
  window_id,
  approved_candidate_id,
  investigation_reason_code,
  visible_evidence_ids
}
```

It cannot contain a checkpoint path, pipeline stage, raw config, CUDA/device,
resource values, CLI, path, or arbitrary numeric override.

The result must carry:

- `execution_role = additional_investigation`;
- a distinct investigation and result ID;
- the same immutable window identity;
- the approved candidate identity;
- standardized label-blind scores/alerts and cost/health summary;
- `committed = false`;
- `eligible_to_replace_committed_result = false`.

### 4.3 Required schema and trajectory separation

Even when both roles reuse the same executor process and per-PIDS parser, they must
use different request schemas or a non-forgeable executor-assigned role field.
Trajectory records must store them in separate fields:

```text
window_step.committed_fast_path_result
window_step.slow_path.additional_detector_tool_calls[]
```

An Agent request cannot set `execution_role = committed_fast_path`. A result
comparison may compare the two roles using deployment-visible signals, but cannot
merge alerts, change the committed result, or infer correctness from disagreement.

## 5. Frozen Agent action taxonomy

### 5.1 General action rules

The slow path emits exactly one action per decision turn. Actions are either:

- terminal for the current diagnosis (`KEEP_CURRENT_CONFIG`, a successful future
  reconfiguration request, or `FINISH_DIAGNOSIS`); or
- evidence-acquiring (`RUN_ADDITIONAL_DETECTOR`), after which the harness may build
  a supplemental prompt and request another bounded decision turn.

The number of additional evidence cycles is not frozen without experiment. It must
be controlled by a harness budget marked `UNRESOLVED_REQUIRES_EXPERIMENT`.

No action changes the current committed result. A tool success means the request
was validated and executed; it does not mean detection was correct.

For an untriggered window, the harness records `KEEP_CURRENT_CONFIG` directly with
`decision_source=harness_default`; there is no prompt, memory exchange, or assistant
turn. If a slow path is open, the LLM may independently choose the same action with
`decision_source=llm_agent`. The two records share state semantics but not
authorship.

### 5.2 Action definitions

#### `KEEP_CURRENT_CONFIG`

| Property | Frozen contract |
|---|---|
| Preconditions | Current result is committed; either no trigger fired, or slow-path diagnosis finds no deployment-visible reason to change |
| Tool call | No |
| Affects current window | No |
| Effective time | Current committed state simply remains active for `W_{t+1}` |
| Fallback | Preserve the last admitted healthy state; if no healthy state exists, close with typed unavailable/stop rather than fabricating a result |
| Current implementation status | Generic `NO_CHANGE`/committed-state primitives exist; exact frozen action enum, decision-source distinction, and prompt contract are not implemented |

This action never runs inference. It records a decision to preserve state after the
automatic inference for `W_t` is complete.

#### `RUN_ADDITIONAL_DETECTOR`

| Property | Frozen contract |
|---|---|
| Preconditions | Slow path is open; an additional detector candidate is approved for the scenario/split/window; budget and resources admit it; a deployment-visible information need is cited |
| Tool call | Yes: `run_additional_detector` |
| Affects current window | Produces supplemental evidence for `W_t`, but cannot alter its committed result |
| Effective time | Result becomes available only to the current slow-path diagnosis after successful validation; no persistent state transition |
| Fallback | `FINISH_DIAGNOSIS` or `KEEP_CURRENT_CONFIG`; record sanitized unavailable/failed reason |
| Current implementation status | Generic/parallel detection execution primitives exist, but committed-versus-additional schemas, non-replacement guards, per-PIDS admission, and end-to-end tool are not implemented |

#### `SELECT_VALIDATED_THRESHOLD`

| Property | Frozen contract |
|---|---|
| Preconditions | Candidate belongs to the active detector/config/checkpoint and scenario; it was frozen from an allowed source before held-out use; expected change is supported by score/alert evidence |
| Tool call | Yes: `select_validated_threshold` |
| Affects current window | No |
| Effective time | `W_{t+1}` or later after atomic admission |
| Fallback | Keep the current threshold/config; never use a free numeric value |
| Current implementation status | Threshold provenance and validation-quantile primitives exist; candidate catalog, high-level tool, atomic transition, and real per-PIDS validation are missing |

#### `LOAD_APPROVED_CONFIG`

| Property | Frozen contract |
|---|---|
| Preconditions | Opaque config candidate is frozen and approved for the same detector, dataset/scenario, split, checkpoint, parser, causality class, and resources |
| Tool call | Yes: `load_approved_config` |
| Affects current window | No |
| Effective time | `W_{t+1}` or later after admission and any required state initialization |
| Fallback | Preserve current approved config; reject partial loading |
| Current implementation status | Frozen ApprovedConfig catalog selection exists; named tool, populated real catalog, activation/rollback, and smoke evidence are missing |

#### `SWITCH_DETECTOR`

| Property | Frozen contract |
|---|---|
| Preconditions | Target detector candidate passes the full PIDS admission gate for the scenario/split; capability mismatch is supported by visible evidence; reset/warm-up policy is defined |
| Tool call | Yes: `switch_detector` |
| Affects current window | No |
| Effective time | `W_{t+1}` or a later explicitly admitted boundary; never mid-window |
| Fallback | Preserve the current detector if healthy; otherwise enter typed unavailable/stop policy without fabricating alerts |
| Current implementation status | Discovery, identity, frozen-config, scheduler, and pending-state primitives exist; atomic switch, state initialization, rollback, per-PIDS parser/checkpoint/profile, and real smoke are missing |

#### `RETRAIN_DETECTOR`

| Property | Frozen contract |
|---|---|
| Preconditions | Slow path is open; an approved training recipe exists; only allowed train/validation inputs are accessible; budget/resources admit the job; the current checkpoint is unsuitable based on visible stability/health evidence |
| Tool call | Yes: `retrain_detector` |
| Affects current window | No |
| Effective time | None by itself. Success creates a quarantined candidate; activation requires admission plus a later `LOAD_APPROVED_CONFIG` or `SWITCH_DETECTOR`, effective at a future window |
| Fallback | Continue the current admitted detector if healthy; otherwise typed unavailable/stop policy; never auto-promote an incomplete checkpoint |
| Current implementation status | Training/provenance research primitives exist, but W&B-free real lifecycle, recipe catalog, reliable checkpointing, asynchronous tool, promotion gate, and real PIDS smoke are missing |

#### `SELECT_RESOURCE_PRESET`

| Property | Frozen contract |
|---|---|
| Preconditions | A validated preset is compatible with the detector/job and explicit project quota; visible OOM/timeout/pressure evidence or planned job requirements justify selection |
| Tool call | Yes: `select_resource_preset` |
| Affects current window | Never changes or reruns its committed result |
| Effective time | For a later uncommitted job after admission; persistent fast-path changes apply no earlier than `W_{t+1}` |
| Fallback | Retain the current admitted preset or block the job; Agent never chooses GPU IDs or arbitrary batch/resource values |
| Current implementation status | Fixed resource profile, executor GPU placement, thread limits, and admission scheduler exist; validated preset catalog, Agent tool, retry/rollback policy, and per-PIDS measurements are missing |

#### `FINISH_DIAGNOSIS`

| Property | Frozen contract |
|---|---|
| Preconditions | Slow path is open and the Agent has no justified additional tool/action, or a bounded investigation has completed/failed |
| Tool call | No |
| Affects current window | No |
| Effective time | Ends the slow path immediately; any separately admitted pending transition remains scheduled, otherwise current config persists |
| Fallback | `KEEP_CURRENT_CONFIG` semantics when no pending transition exists |
| Current implementation status | Generic no-tool termination/reflection behavior exists; exact action, closure invariants, and bounded supplemental-cycle handling are not implemented |

### 5.3 Action implementation summary

No frozen action is currently both end-to-end implemented and backed by an admitted
real PIDS. `KEEP_CURRENT_CONFIG` and `FINISH_DIAGNOSIS` have the closest generic
controller equivalents. All execution and reconfiguration actions retain at least
one missing high-level tool, real artifact, parser, admission, or lifecycle gate.

## 6. Three observation layers

The word “observation” is frozen into three distinct contracts. They must never be
serialized under one ambiguous type.

### 6.1 A. `RawExecutionState`

**Audience:** trusted harness/executor only.

**Contents:**

- raw standardized-parser inputs and quarantined PIDSMaker files;
- process status, attempts, timestamps, executor command manifest, environment-key
  names, device/resource lease, and internal stage trace;
- raw resource telemetry, cache/artifact records, checkpoint/config/threshold
  provenance, and parser diagnostics;
- committed-versus-additional execution role and immutable window identity.

This layer may contain implementation details that are forbidden to the LLM. It
must not intentionally ingest hidden evaluator data. If an upstream artifact
contains labels, private mappings, or forbidden columns, the parser quarantines it
and the run fails closed rather than copying those fields forward.

**Computation:** entirely programmatic and deterministic, except measurements from
the external process itself. No field is generated by the LLM.

**Compression/truncation:** raw logs may be size-capped or artifactized according
to a versioned executor retention policy, but the immutable hashes, status,
identity, timing, and failure provenance remain complete. Raw-log limits are not
prompt limits.

### 6.2 B. `CanonicalAgentVisibleObservation`

**Audience:** controller, trajectory audit, memory harness, prompt builder, and LLM
through the next projection.

**Contents:**

- scenario/episode/window identity and `[start,end)` timing;
- environment and current-graph summaries derived from visible provenance;
- committed detector/config/checkpoint/threshold opaque IDs and state health;
- standardized score distribution, alert IDs/count/ratio, shift, instability, and
  degeneracy summaries;
- sanitized execution status, runtime/resource-pressure classes, budget state,
  pending transition, and opaque provenance IDs;
- approved capability availability summaries.

It excludes labels, TP/FP/FN/TN, precision/recall/F1/MCC/ADP/coverage, attack or
campaign identity, attack-window mappings, teacher rationale, evaluator feedback,
raw PIDSMaker artifacts, CLI, paths, CUDA/device identity, credentials, arbitrary
pipeline controls, and unsanitized errors.

**Computation:** every field is deterministically constructed and schema-validated
by the harness from `RawExecutionState`, committed state, current/past visible
windows, and frozen catalogs. No canonical observation field may be authored or
rewritten by the LLM.

**Compression/truncation:** Raw-to-canonical conversion performs versioned
aggregation and sanitization, not token-budget truncation. The canonical record is
complete under its schema and is retained for audit. If a required field cannot be
computed, it carries a typed unknown/unavailable status; it is not omitted to save
tokens.

### 6.3 C. `ModelPromptObservation`

**Audience:** LLM only.

**Contents:** after a trigger opens the slow path, a deterministic prompt projection
of the canonical observation plus the separate trigger decision/reason codes,
stable enum descriptions, allowed actions/tools, opaque evidence references, and an
explicit remaining budget. No model prompt is required for an untriggered fast-path
window. After memory retrieval or an additional detector run, the harness builds a
new prompt projection that includes only the admitted sanitized records/results.

**Computation:** field selection, ordering, formatting, numeric rendering,
artifact-reference substitution, memory insertion, and token accounting are
performed by a versioned deterministic prompt builder. The LLM generates no field
inside `ModelPromptObservation`; it generates a response to it. Historical memory
text may originate from previously reviewed LLM write candidates, but it remains a
separate provenance-bearing record selected by the harness.

**Compression/truncation:** token-budget compression and truncation occur only at
this layer. They must be deterministic, field-aware, and provenance-preserving.
Required identity, timing, active state, trigger reasons, action allowlist,
failures, and budget cannot be silently truncated. Exact token budget, history
length, record count, and truncation priority are
`UNRESOLVED_REQUIRES_EXPERIMENT`.

### 6.4 Layer transition rules

```text
RawExecutionState
  -- deterministic parser/sanitizer/aggregator -->
CanonicalAgentVisibleObservation
  -- deterministic trigger decision -->
optional slow path
  -- deterministic prompt projection/budgeting -->
ModelPromptObservation
```

The reverse direction is forbidden. LLM output cannot patch a canonical or raw
observation. Every layer records schema version, builder version, source IDs, and a
content hash so the same canonical input can be reproduced.

### 6.5 Training/deployment consistency

Formal trajectory collection and deployment must use the same:

- canonical observation schema and validators;
- raw-to-canonical builder version;
- prompt builder, tokenizer identity, field order, numeric rendering, and
  compression/truncation policy;
- action/tool schemas and catalog filtering;
- memory request/use protocol and retrieval policy version;
- label/privacy guard and failure semantics.

Privileged teacher/evaluator data may produce offline supervision outside this
runtime boundary, but it cannot modify any of the three observation layers or the
deployed prompt. Every formal trajectory stores canonical-observation and rendered-
prompt hashes so divergence is detectable. This consistency rule does not define
an SFT dataset.

## 7. Frozen memory interaction sequence

### 7.1 Normative sequence

When a slow path is opened, the memory protocol is:

```text
observation
→ memory_read_request
→ retrieved records
→ memory_use_decision
→ action
→ optional memory_write_candidate
```

The harness owns storage, retrieval, ranking, sanitization, namespace isolation,
deduplication, and actual writes. The LLM owns the read intent, use/downweight/
ignore decisions, action selection, and optional write candidate content.

### 7.2 Turn protocol

With memory retrieval, the minimum diagnostic exchange is:

1. **Assistant turn 1:** emit one typed `memory_read_request`. It may set
   `needed=false`; it cannot directly retrieve records.
2. **Memory tool turn 1:** harness validates the request and returns sanitized,
   provenance-bearing records or a typed empty/failure result.
3. **Assistant turn 2:** emit `memory_use_decision`, diagnosis, exactly one frozen
   action, confidence/fallback, and optional `memory_write_candidate`.

Thus the base memory-assisted decision uses **two assistant turns and one tool
turn**. If `needed=false`, the harness still returns a deterministic empty retrieval
result so training and deployment preserve the same turn shape.

If the selected action invokes a runtime tool, add:

4. **Action tool turn 2:** harness executes the validated tool and returns a
   sanitized result.

For terminal reconfiguration actions, the harness can close the slow path after
recording success/failure and fallback; no extra assistant turn is required. For
`RUN_ADDITIONAL_DETECTOR`, interpreting new evidence requires a supplemental
canonical/prompt observation and another bounded diagnostic exchange. That exchange
must end in a terminal action or another explicitly budgeted evidence request.

The exact maximum number of supplemental exchanges and retries is
`UNRESOLVED_REQUIRES_EXPERIMENT`.

### 7.3 Memory use and write constraints

- Every retrieved record receives exactly one `use`, `downweight`, or `ignore`
  decision; reasons cite only visible evidence.
- The final diagnosis/action cites IDs of memories actually used. Retrieval alone
  does not authorize an action.
- A write candidate is a proposal, not a completed write. The harness validates,
  sanitizes, deduplicates, and applies namespace policy.
- A write candidate emitted before an action-tool result may record observation,
  diagnosis, and intended action, but must not claim the tool succeeded.
- If actual tool outcome should be remembered, the harness records deterministic
  execution facts; any new LLM-authored interpretation requires a later explicit
  assistant turn.
- Held-out runtime cannot update static LTM. Working/episode state remains scoped
  and resets according to the accepted memory lifecycle.

## 8. Minimum PIDS admission gate for formal trajectory collection

A PIDS/config/variant/dataset combination is admitted only if all gates pass. One
failure yields `NOT_ADMITTED_FOR_FORMAL_TRAJECTORY` with an explicit reason. A
synthetic fixture or zero exit code cannot satisfy a real gate.

### 8.1 Gate checklist

| Gate | Minimum evidence | Fail-closed condition |
|---|---|---|
| Causal config | Resolved config and data-flow audit prove vocabulary, normalization, IDF/statistics, embeddings, model, threshold, and reference state use only allowed train/validation/current-past inputs and freeze before held-out | Any test/future-window consultation, unknown fit scope, transductive mode, or mutable held-out fit state |
| Checkpoint | Real loadable model bundle with format, content hash, producing config/code/data provenance, successful reload, and no fabricated path | Missing/unloadable/mismatched checkpoint or normal run that failed to persist one |
| Threshold | Frozen threshold record bound to detector/config/checkpoint/dataset, allowed source split/method, timestamp, code commit, and finite value | Test-derived, unbound, missing-provenance, arbitrary Agent-supplied, or non-finite threshold |
| Parser | Per-PIDS parser validates real raw artifacts, detection unit, score semantics, `[start,end)` bounds, finite values, required IDs, and rejects labels/private columns | Generic artifact presence only, malformed/out-of-window output, label-bearing field, or unsupported detector output |
| Resource profile | Real measured smoke profile records runtime, CPU/RAM/GPU use, concurrency assumption, timeout behavior, and fits explicit project quota | Host-capacity inference, missing measurement, quota breach, OOM, or unknown same-device concurrency |
| State/reset semantics | Documented and tested initialization, ordering, per-window update, scenario/split reset, replay/warm-up, retry idempotence, and checkpoint-state relationship | State leakage across split/scenario, future access, nondeterministic retry mutation, or undefined stateful-detector reset |
| Real smoke | At least one real, non-synthetic, label-blind end-to-end run on an approved non-held-out smoke scenario validates execution, parser, commit, observation, resource, failure, and artifact behavior | Synthetic-only success, hidden-label access, missing outputs, zero-exit-only evidence, or uninspected remote run |
| Provenance | Unique non-overwriting run ID plus exact project/PIDSMaker SHAs, dataset/window IDs, resolved approved config, checkpoint/threshold hashes, environment manifest, command manifest, seed, timing, resources, stage/artifact hashes, parser/schema versions, and failures | Missing/mismatched identity, overwritten artifact, untracked implementation, or unverifiable run lineage |

### 8.2 Admission result

The admission record is deterministic and reviewable:

```text
PIDSAdmissionRecord {
  admission_id
  detector_id
  variant_id
  dataset_or_scenario_id
  experiment_class
  gate_version
  gate_results[]
  admitted_for_formal_trajectory: boolean
  admitted_uses[]
  evidence_artifact_ids[]
  reviewed_at
  reviewer_identity
}
```

Admission is scoped. Passing offline compatibility smoke does not imply causal-main
or held-out admission. Passing one PIDS variant/dataset does not admit another.
Every admitted use must distinguish committed fast path, additional investigation,
training candidate creation, and resource profile.

At the current Phase 1.6 evidence level, none of the eight PIDS is admitted for
formal real trajectory collection because approved real checkpoint/parser/resource/
smoke evidence is incomplete.

## 9. Frozen trajectory event structure

This section freezes runtime event separation, not a dataset format.

Each window audit must preserve these logically distinct events:

```text
WindowRuntimeTrace {
  window_closed
  committed_state_snapshot
  committed_fast_path_attempts
  committed_fast_path_result
  raw_execution_state_ref
  canonical_observation_ref
  trigger_decision
  optional_slow_path {
    model_prompt_ref
    assistant_memory_read_request
    memory_tool_result
    assistant_memory_use_and_action
    optional_action_tool_result
    optional_supplemental_observation_cycles
    optional_memory_write_candidate
    harness_memory_write_result
  }
  pending_state_validation
  next_window_transition
}
```

Committed inference is recorded even when no LLM turn occurs. An additional
detector call is never placed in `committed_fast_path_attempts`. Harness events,
assistant messages, memory tool results, and runtime tool results retain separate
roles and timestamps.

## 10. Unresolved decisions

The following values or policies lack sufficient experimental evidence. This
document intentionally does not choose defaults for them.

| Decision | Status | Required evidence |
|---|---|---|
| Score/alert shift trigger thresholds | `UNRESOLVED_REQUIRES_EXPERIMENT` | Validation-only trigger sensitivity, false-trigger cost, and held-out freeze protocol |
| Periodic slow-path checkpoint interval | `UNRESOLVED_REQUIRES_EXPERIMENT` | Validation study of detection/control benefit versus token and runtime cost |
| Number of recent windows used for trend/instability summaries | `UNRESOLVED_REQUIRES_EXPERIMENT` | Causal rolling-range candidates evaluated only on allowed validation data |
| Scenario construction-window size when not fixed by an accepted dataset protocol | `UNRESOLVED_REQUIRES_EXPERIMENT` | Causality, detection resolution, graph size, and cost study; no online search |
| Memory retrieval top-k, candidate cap, and score weights | `UNRESOLVED_REQUIRES_EXPERIMENT` | Retrieval usefulness/leakage/cost evaluation under the fixed harness |
| Working-memory history length, episode-summary cadence, and capacity/TTL | `UNRESOLVED_REQUIRES_EXPERIMENT` | Memory ablation and isolation tests |
| Model prompt token budget and field-aware truncation priorities | `UNRESOLVED_REQUIRES_EXPERIMENT` | Prompt fidelity and action-quality sensitivity with identical deployment builder |
| Raw-log retention cap and artifactization threshold | `UNRESOLVED_REQUIRES_EXPERIMENT` | Audit/recovery needs, storage cost, and provenance-completeness validation |
| Maximum additional-detector cycles per window | `UNRESOLVED_REQUIRES_EXPERIMENT` | Marginal diagnostic value, wall time, GPU contention, and token cost |
| Tool retry count and retryable failure classes | `UNRESOLVED_REQUIRES_EXPERIMENT` | Idempotence and failure-recovery experiments; retries must not duplicate commits |
| Detector-specific threshold candidates and calibration quantiles | `UNRESOLVED_REQUIRES_EXPERIMENT` | Allowed validation calibration tied to each checkpoint and score semantics |
| Alert-volume preview method for threshold selection | `UNRESOLVED_REQUIRES_EXPERIMENT` | Label-free validation of monotonicity and stability |
| Per-PIDS cost-class boundaries | `UNRESOLVED_REQUIRES_EXPERIMENT` | Repeated real runtime/CPU/RAM/GPU profiling under the explicit resource profile |
| Resource preset values, timeouts, batching limits, and concurrency | `UNRESOLVED_REQUIRES_EXPERIMENT` | Real per-PIDS smoke and failure envelopes; Agent never selects raw values |
| Stateful detector reset, replay, and warm-up horizons | `UNRESOLVED_REQUIRES_EXPERIMENT` | Ordered replay/reset equivalence tests for each stateful PIDS/config |
| Retraining recipes, seeds, stopping rules, and promotion criteria | `UNRESOLVED_REQUIRES_EXPERIMENT` | Train/validation-only repeated runs with reliable checkpoint lifecycle |
| Real-smoke acceptance bounds for runtime, resource, output stability, and parser coverage | `UNRESOLVED_REQUIRES_EXPERIMENT` | Pre-registered smoke protocol and repeated evidence |
| Automatic pre-commit safety fallback after committed-detector failure | `UNRESOLVED_REQUIRES_EXPERIMENT` | Causal timing and reliability design proving it can finish before commit without hidden selection |
| Whether additional-detector disagreement warrants another LLM turn | `UNRESOLVED_REQUIRES_EXPERIMENT` | Label-blind diagnostic utility and bounded-loop evaluation |
| Exact action confidence calibration and fallback-selection policy | `UNRESOLVED_REQUIRES_EXPERIMENT` | Validation calibration; confidence must not be treated as correctness |

Existing implementation constants are implementation evidence, not automatically
accepted experimental choices. They remain unfrozen unless an accepted requirement
or approved experiment explicitly promotes them.

## 11. Freeze summary

The runtime unit is now frozen as a harness-owned committed detection transaction
followed by an optional LLM-owned diagnosis transaction. The Agent never invokes
the current committed detector, and `KEEP_CURRENT_CONFIG` never means infer again.

The three observation layers separate raw executor truth, complete sanitized
Agent-visible state, and token-budgeted prompt presentation. Only the prompt layer
may be compressed for model context, and no observation field is LLM-authored.

Formal real trajectory collection remains blocked for a PIDS until every admission
gate passes. All unsupported numeric constants and policy limits remain explicitly
`UNRESOLVED_REQUIRES_EXPERIMENT` pending review and evidence.
