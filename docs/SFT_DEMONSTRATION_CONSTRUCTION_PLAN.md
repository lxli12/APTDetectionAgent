# APT-Agent SFT Demonstration Dataset Construction Plan

Requirements: REQ-GOV-003..004, REQ-CAUSAL-001..004,
REQ-LABEL-001..004, REQ-WINDOW-001..004, REQ-CONFIG-001..003,
REQ-PIDS-001..005, REQ-TOOL-001..005, REQ-MEMORY-001..007,
REQ-ARTIFACT-001..003, REQ-RESOURCE-001..003, REQ-ENV-001..004,
REQ-DB-001..003, REQ-WANDB-001, REQ-REPRO-001..003,
REQ-SFT-001..004.

Status: Phase 3 implementation plan for offline supervised demonstration
construction. This document does not generate data, execute PIDSMaker, update
model weights, or modify runtime code.

Normative inputs are:

- `docs/design/APT_Detection_Agent_Design_v0.4.md`;
- `docs/AGENT_RUNTIME_CONTRACT_FREEZE.md`;
- `docs/AGENT_TOOL_CAPABILITY_SPEC.md`;
- `docs/SFT_DATASET_DESIGN.md`;
- `docs/PIDSMaker_FRAMEWORK_NOTE.md`;
- `docs/PIDSMaker_CAPABILITY_CATALOG.md`.

APT-Agent is an **APT detection agent**. This plan covers supervised
demonstrations only. Its training objective is the **APT detection orchestration
policy** represented by agent execution trajectories (also called detection
trajectories) and, where terminal output is required, an APT detection report.

The intended versioned, sanitized, multi-turn chat/tool corpus teaches:

- detector and high-level tool selection;
- PIDSMaker orchestration through approved Agent tools;
- approved configuration adjustment;
- memory read/write/use policy;
- evidence-grounded APT detection decisions and post-trigger slow-path diagnosis.

It does not teach any task beyond APT detection orchestration, nor does it teach a
detector model, an attack classifier, or hidden-evaluator optimization.

## 1. SFT dataset generation pipeline

### 1.1 End-to-end flow

```text
Raw provenance datasets
→ PIDSMaker controlled execution
→ Offline run table
→ Observation construction
→ Teacher demonstration generation
→ Tool-result insertion
→ Trajectory validation
→ Sanitization
→ SFT export
```

This is an offline construction process over agent-training scenarios. Each input,
tool call, tool result, teacher message, and private selection result is recorded;
there is no unbounded Agent-directed data collection.

### 1.2 Stage contracts

| Stage | Input | Deterministic or supervised work | Output | Hard gate |
|---|---|---|---|---|
| 0. Source registration | Raw provenance inventory, public metadata, isolated label inventory | Hash, identify format, record permissions/license, assign agent-level split, create public/private manifests | `DatasetManifest` plus private companion manifest | Unknown identity, mixed split, or private path in public manifest stops |
| 1. Admission resolution | Dataset manifest, PIDS registry, configs, checkpoints, thresholds, parsers, profiles, smoke/provenance evidence | Evaluate the eight frozen PIDS admission gates for each exact use | `PIDSAdmissionRecord[]` | Successful execution is allowed only for an admitted PIDS/variant/config/dataset/role |
| 2. Controlled PIDSMaker execution | Admitted execution matrix and chronological windows | Harness executes committed or approved additional roles with frozen state and executor-owned parameters | `RawExecutionState`, standardized result/failure, artifacts and public runtime trace | No labels, arbitrary CLI/stage/device, future window, overwrite, or unparsed output |
| 3. Offline run table | Runtime traces, capability registry, environment/window summaries, public cost/failure evidence, private evaluation references | Build one Environment–Behavior–PIDS row per controlled run/rejection and group comparable PIDS alternatives | `OfflineRunRecord[]`, counterfactual group index | Public and private outcome columns remain physically separate |
| 4. Observation construction | Committed runtime trace, visible history, detection context, capability catalog, memory state, frozen trigger profile | Build canonical observation, deterministically derive the student-visible detection context, decide trigger, and render prompt only when triggered | `CanonicalAgentVisibleObservation`, `TriggerRecord`, `ModelPromptObservation` | Hash/identity mismatch, prompt over budget, untriggered prompt, private detection-context field, or leakage stops |
| 5. Teacher demonstration | Exact public prompt, isolated private construction envelope, allowed actions/tools, sanitized memory/tool context | Rule/LLM teacher uses permitted private construction information to generate candidate assistant targets; every exported target must remain grounded in deployment-visible evidence | Candidate assistant turns, memory decisions, grounding and action/tool call plus private generation provenance | Private facts/rationale cannot be copied, paraphrased, cited or encoded into the student-visible target |
| 6. Tool-result insertion | Validated teacher tool call and fixed offline tool state | Execute or retrieve the exact recorded public tool outcome, insert a paired tool message, optionally build supplemental prompt | Ordered assistant/tool transcript | Synthetic success, mismatched call ID, or current-window rewrite stops |
| 7. Trajectory validation | Complete candidate transcript plus program provenance | Validate schema, ordering, evidence closure, actions, tools, timing, PIDS coverage, memory protocol and split | Accepted candidate or typed rejection report | All validators must pass before private selection/sanitization |
| 8. Private selection and sanitization | Valid public candidates and isolated private evaluator results | Filter/rank agent-training candidates privately; choose only visibly justifiable candidates; strip private envelope recursively | `SanitizedSFTTrace[]` | Ambiguous targets or semantic private leakage are rejected, not rewritten optimistically |
| 9. SFT export | Sanitized traces, group split, prompt/tool/tokenizer manifests | Emit canonical JSONL and derived OpenAI-compatible chat/tool JSONL with assistant-only loss masks | Dataset/export manifests, train/validation JSONL, coverage and rejection reports | Round-trip, hashes, group disjointness and loss masks must pass |

### 1.3 Build ordering and immutability

The stages are append-only. A later private decision cannot alter an earlier
canonical observation, tool result, or public runtime trace. Rejected candidates
remain in a private rejection ledger with reason codes but never enter student
exports.

Dataset partitions are assigned by episode/scenario group before teacher
demonstrations are selected. Windows from one episode, their memory, repeated PIDS
runs, counterfactual group, and derived trajectories cannot cross the train/
validation boundary.

## 2. Data sources

### 2.1 Source families

#### DARPA TC CDM datasets

DARPA Transparent Computing E3/E5 sources provide whole-system provenance event
records in the Common Data Model family. PIDSMaker ingestion normalizes supported
sources into PostgreSQL entity/event tables, then builds detector-specific temporal
provenance graphs. Public provenance is available to the runtime worker. Ground
truth files, campaign mappings, and attack-chain annotations belong only to the
private teacher/evaluator store.

The registered TC datasets are CADETS, THEIA, CLEARSCOPE, FIVEDIRECTIONS, and TRACE
for E3/E5 where configured. Local AutoDL inventory currently reports dumps for
`CADETS_E3`, `THEIA_E3`, `CLEARSCOPE_E3`, `FIVEDIRECTIONS_E3`, `THEIA_E5`, and
`CLEARSCOPE_E5`; the remaining registered TC dumps are not locally observed.

#### DARPA OpTC datasets

PIDSMaker registers Windows hosts `optc_h201`, `optc_h501`, and `optc_h051`.
Their normalized provenance is intended to enter the same graph-construction
boundary. Local dumps are observed, but the compatibility report records an
unresolved database-name mapping. The plan therefore registers them in manifests
and capability-awareness demonstrations while successful execution waits for an
approved mapping and full admission.

#### Additional PIDSMaker registrations

`ATLASV2_EDR` and `CARBANAKV2_EDR` are registered EDR-derived datasets. Their
local dumps are not currently observed, so they remain inventory/reserved sources.
Registration is not evidence of graph, PIDS, checkpoint, or parser compatibility.

### 2.2 Current registered dataset inventory

| Dataset | Source/format family | PIDSMaker graph boundary | Locally observed | Label status | Planned SFT use |
|---|---|---|---|---|---|
| `CADETS_E3` | DARPA TC CDM, FreeBSD | Normalized PostgreSQL → aligned temporal provenance graphs | Yes | Private ground truth configured; project campaign manifest remains authoritative | Pilot primary; bounded VELOX validation evidence exists |
| `THEIA_E3` | DARPA TC CDM, Linux | Same registered construction boundary | Yes | Private configured, validation required | Pilot environment diversity; successful PIDS uses require admission |
| `CLEARSCOPE_E3` | DARPA TC CDM, Android | Same | Yes | Private configured, validation required | Later/pilot reserve |
| `FIVEDIRECTIONS_E3` | DARPA TC CDM | Same; upstream OS documentation conflict retained | Yes | Private configured, validation required | Pilot platform diversity; manifest carries documentation conflict |
| `TRACE_E3` | DARPA TC CDM, Linux | Same | No | Private configured upstream, local verification unavailable | Inventory/capability only until data verification |
| `CADETS_E5` | DARPA TC CDM, FreeBSD | Same | No | Private configured upstream, local verification unavailable | Inventory only |
| `THEIA_E5` | DARPA TC CDM, Linux | Same | Yes | Private configured, validation required | Expansion source |
| `CLEARSCOPE_E5` | DARPA TC CDM, Android | Same | Yes | Private configured, validation required | Expansion source |
| `FIVEDIRECTIONS_E5` | DARPA TC CDM | Same; upstream OS conflict retained | No | Private configured upstream, local verification unavailable | Inventory only |
| `TRACE_E5` | DARPA TC CDM, Linux | Same | No | Private configured upstream, local verification unavailable | Inventory only |
| `optc_h201` | DARPA OpTC, Windows provenance | Normalized PostgreSQL → aligned temporal graphs | Yes | Private configured, validation required | Pilot reserve pending database mapping |
| `optc_h501` | DARPA OpTC, Windows provenance | Same | Yes | Private configured, validation required | Expansion after mapping/admission |
| `optc_h051` | DARPA OpTC, Windows provenance | Same | Yes | Private configured, validation required | Expansion after mapping/admission |
| `ATLASV2_EDR` | EDR telemetry, Windows | Registered PIDSMaker construction path | No | Private status must be verified | Inventory only |
| `CARBANAKV2_EDR` | EDR telemetry, Windows/Linux | Registered PIDSMaker construction path | No | Private status must be verified | Inventory only |

All eight PIDS are registry candidates for every manifest, but `available_pids`
must be derived from scoped `PIDSAdmissionRecord`s rather than static registration.

### 2.3 Existing PIDS output sources

Controlled construction may consume existing real artifacts only when their full
provenance and admission are valid. Relevant PIDSMaker artifacts include:

- construction/transformation graph artifacts and node/type maps;
- fitted feature artifacts frozen before the target windows;
- temporal tensors and batches;
- checkpoint bundles, including temporal state when required;
- raw inference score files such as edge-loss CSVs;
- detector-specific node/edge/window score outputs;
- runtime, resource, command, stage and artifact manifests.

Raw Torch/pickle files and PIDSMaker evaluation outputs are not student data. A
per-PIDS parser converts label-blind raw inference into one standardized public
result. The accepted real path currently covers VELOX on bounded `CADETS_E3`
validation only; other PIDS outputs remain unavailable/unverified until their
independent admission evidence exists.

### 2.4 Dataset Manifest

The public manifest is deterministic and contains no label paths or campaign
identity:

```text
DatasetManifest {
  schema_version
  dataset_manifest_id
  dataset_id
  source_family
  source_release
  source_format
  source_content_hashes[]
  access_and_license_status

  normalized_storage_schema_id
  provenance_schema_id
  platform_class

  graph_construction {
    builder_id
    origin
    timezone
    window_size_seconds
    half_open_alignment
    entity_types[]
    relation_types[]
    transformation_policy_ids[]
  }

  pids_data_partitions {
    train_partition_ref
    validation_partition_ref
    demonstration_partition_ref
  }

  registered_pids[]
  pids_admission_ids[]
  label_availability: none | private_available | unverified

  training_use {
    pids_fit_allowed
    threshold_calibration_allowed
    sft_demonstration_allowed
    held_out_sft_forbidden
  }

  private_companion_manifest_id
  code_and_builder_versions
  created_at
  content_hash
}
```

The private companion manifest may reference the versioned campaign manifest,
ground-truth artifacts, attack chains, and evaluator permissions. It is readable
only by the privileged process. The public field `label_availability` states only
whether isolated teacher/evaluation material exists; it reveals no label value,
path, attack count, time, or identity.

`pids_data_partitions` and agent-level episode partitions remain distinct. PIDS
train/validation inputs fit detectors and thresholds. Only agent-training episodes
produce SFT demonstrations. Held-out/deployment windows never enter the SFT build.

## 3. PIDSMaker execution for SFT data

### 3.1 Execution matrix

The executor constructs a declared matrix:

```text
DatasetManifest
× aligned chronological window/range
× PIDS identity and variant
× approved config/checkpoint/threshold
× admitted use
× controlled seed/repetition record
```

The matrix contains all eight canonical PIDS:

- VELOX;
- ORTHRUS, with variant identity preserved;
- MAGIC;
- FLASH;
- KAIROS;
- NODLINK;
- ThreatRace;
- R-CAID (`rcaid` registry identity).

No matrix row executes merely because the PIDS is registered. The builder first
joins the exact admission record. Failed admission creates a capability-awareness
or deterministic rejection source, not a successful execution record.

### 3.2 Controlled execution rules

For each admitted row, the wrapper:

1. resolves dataset, config, checkpoint, threshold and resource preset from frozen
   catalogs;
2. verifies project/PIDSMaker commits and the isolated compatibility-build hash;
3. binds the aligned current window and prior state token;
4. requests the executor-owned resource lease;
5. invokes the existing structured adapter without a shell and without teacher-
   supplied internal parameters;
6. parses only label-blind inference artifacts;
7. validates finite scores, detection unit, score semantics and window bounds;
8. records state/reset behavior, runtime, resource pressure, cache/recompute class,
   failures and artifact hashes;
9. appends the result exactly once under a unique run ID.

The execution process has no private label database/filesystem permission. It does
not call PIDSMaker label evaluation or triage.

### 3.3 OfflineRunRecord

One record is created for each execution, capability-only row, or typed rejection:

```text
OfflineRunRecord {
  schema_version
  run_record_id
  counterfactual_group_id

  dataset_manifest_id
  episode_id
  window_or_range_id
  split

  environment_profile
  observable_behavior
  detection_context
  historical_evidence_context
  temporal_context
  pids_capability

  detector_id
  variant_id
  approved_config_id
  checkpoint_id
  threshold_id
  resource_preset_id
  admitted_use

  configuration_summary
  standardized_output
  deployment_visible_outcome
  cost
  failure_condition

  execution_role
  public_runtime_trace_ref
  admission_id
  private_evaluation_ref
  provenance
  content_hash
}
```

Required record fields:

| Field | Construction rule |
|---|---|
| Environment profile | Deterministic platform/provenance schema, graph scale/density, entity/relation distributions, workload/event rate, resource constraint and environment signature |
| Observable behavior | Label-free graph/score/alert/trend/state/resource symptom plus evidence IDs and unknowns |
| Detection context | Current detector status, current detection uncertainty, anomaly/confidence trend, unresolved detection evidence and current detection stage/state, all derived from causally available student-visible fields |
| Historical evidence context | Ordered current/past public windows, prior committed/additional outcomes, actions, failures, state changes and memory references |
| Temporal context | Current `[start,end)`, sequence, past-only range, persistence/change/recency and reset continuity; never attack phase or future data |
| PIDS capability | Registry capability type, detection unit, score semantics, required state, limitations, availability and compatibility status |
| Configuration | Opaque approved IDs plus public semantics; no YAML, path, arbitrary override or private checkpoint location |
| Output | Standardized score/alert summary or typed unavailable/failure; raw artifacts remain referenced |
| Cost | Wall/CPU/GPU time, memory-pressure classes, cache reuse, tool/LLM calls and token counts available at that causal point |
| Failure condition | Typed admission, timeout, OOM, parser, state/reset, config/checkpoint/threshold or tool failure with applicability/avoid conditions |

`detection_context` is strictly APT detection context and does not represent a
separate attack-analysis workflow. It must not contain an attack phase, campaign
label, ground-truth mapping or hidden evaluator result. The builder also rejects
malicious entity history, attack-to-window mapping, TP/FP/FN/TN, coverage, MCC,
ADP, or future-window facts in every public field.

Observation construction deterministically projects the allowed detection-context
fields from committed runtime state, standardized detector output and past-only
visible history into `CanonicalAgentVisibleObservation`; the LLM cannot author or
patch them. Prompt rendering may compress their presentation but cannot add a
stage, label or evaluator conclusion that is absent from the canonical record.

### 3.4 Multi-PIDS grouping

Rows sharing the same dataset manifest, episode, window/range, public environment
profile, observable behavior, and detection context receive one
`counterfactual_group_id`. The group
preserves PIDS-specific score semantics and does not directly compare raw numeric
scores across incompatible detection units.

Two public comparison views are built:

- **capability-choice view:** candidate capability, availability, historical
  evidence, cost and failure conditions available before a new tool call;
- **result-comparison view:** standardized outputs available only after approved
  additional runs have actually completed.

Private evaluation can attach outcome references to the group for teacher
selection. Those references do not enter either public view.

## 4. Detection trajectory generation

### 4.1 Demonstration boundary

A demonstration begins only after committed inference, result commit, canonical
observation construction, and a harness trigger. `INVOKE_SLOW_DIAGNOSIS` is a
program event, not an assistant action.

The base supervised sequence is:

```text
Observation
→ assistant: memory_read_request
→ tool: memory result
→ assistant: memory_use_decision
             + structured evidence summary
             + diagnosis
             + ActionDecision
             + optional memory_write_candidate
→ optional tool call
→ tool result
→ optional supplemental Observation
→ next assistant decision
```

This is a supervised demonstration assembled from declared candidates and actual
tool results. The model target is the assistant-authored turns. System, user and
tool messages are context and receive no assistant loss.

### 4.2 Trajectory source types

| Type | Source | Required content |
|---|---|---|
| Capability awareness | Validated capability registry and current environment/behavior | What the PIDS does, required state, cost/limitations/availability, applicability and non-capabilities |
| Successful tool use | Admitted real execution and standardized result | Valid tool selection, paired result, public interpretation and next decision |
| Failure/rejection | Deterministic admission/tool rejection or real typed failure | Correct diagnosis, no fabricated scores, safe fallback and optional memory candidate |
| Counterfactual PIDS choice | Same public environment/window with multiple capability views | Capability-fit comparison and visibly justified additional/switch/keep choice |
| Memory adaptation | Retrieved records and public outcome | Read/query/use/conflict/write-candidate supervision with harness-owned storage |

All eight PIDS require capability-awareness demonstrations. Successful and failure
coverage is reported independently; lack of admission does not remove capability
supervision.

### 4.3 Assistant target structure

Assistant targets are typed, concise, and auditable:

```text
AssistantDecisionTarget {
  memory_use_decisions[]

  visible_evidence_grounding {
    observable_symptoms[]
    detector_evidence_ids[]
    provenance_evidence_ids[]
    temporal_evidence_ids[]
    resource_evidence_ids[]
    observed_facts[]
    unknowns[]
    uncertainty
    action_justification
  }

  diagnosis_code
  action_decision
  optional_tool_call
  optional_memory_write_candidate
}
```

`VisibleEvidenceGrounding` / `visible_evidence_grounding` is a **structured
detection evidence summary**. It is not chain-of-thought, a private reasoning
trace, or hidden evaluator reasoning. It summarizes only:

- observable symptoms;
- detector evidence, including visible PIDSMaker scores/status where applicable;
- provenance evidence, including visible graph facts;
- temporal evidence, including visible trends and past-only history;
- uncertainty and explicitly unknown information;
- action justification tied to cited evidence IDs.

Resource evidence may be included when it materially constrains detector/tool or
configuration selection. Every summary claim must resolve to the prompt or an
earlier public tool result. Teacher scratch text, private evaluator rationale, and
uncited conclusions are never exported.

### 4.4 Tool-result insertion and next decisions

The transcript assembler never lets the teacher invent a tool result. It joins a
validated `ToolCall` to an executor/memory result by call ID, action ID, case,
window, candidate, and provenance. A failed call inserts a typed sanitized failure,
not a plausible success.

Terminal persistent actions can end after the tool result when the frozen runtime
requires no further assistant turn. `RUN_ADDITIONAL_DETECTOR` or another result
whose interpretation affects the decision creates a deterministic supplemental
prompt and a new two-assistant memory cycle. The current committed result remains
unchanged.

### 4.5 Counterfactual PIDS comparison demonstrations

For the same environment/window, the builder constructs:

1. a shared public context;
2. candidate capability views for multiple PIDS;
3. any causally available historical records;
4. actual standardized tool results only when the associated run occurred before
   the target decision;
5. comparable cost, state and failure fields;
6. a teacher target selecting keep, additional detector, switch, config, threshold
   or finish with explicit uncertainty and fallback.

If private outcomes prefer one PIDS but the public evidence cannot distinguish it,
the example is ambiguous and is rejected. The corpus must not teach an oracle
choice that a deployed Agent could not justify.

## 5. Teacher generation strategy

### 5.1 Comparison

| Strategy | Strength | Limitation | Construction role |
|---|---|---|---|
| Human expert | Strong provenance/security judgment and nuanced fallbacks | Expensive, slower, inconsistent at scale | Seed/rubric creation, rare-action examples and high-risk review |
| Rule-based teacher | Deterministic schema, causality, action/tool and timing correctness | Limited language/diagnostic nuance; rule gaps can bias coverage | Enumerate legal candidates, hard negatives, failure/fallback templates |
| LLM teacher | Scalable structured language and evidence synthesis | Can hallucinate capability, tool or unsupported explanation | Generate candidates from typed public/private construction views under strict parsing and visible-evidence closure |
| Rule + LLM refinement | Combines hard constraints with grounded language diversity | Needs private filtering and human audit | Primary construction strategy |

### 5.2 Selected strategy

Use **rule-based candidate construction plus LLM refinement**, with an isolated
private construction view, human expert seeds, and risk-stratified review.

The process is:

1. Rules bind the exact observation, allowed actions, approved IDs, memory/tool
   schemas, timing and fallbacks.
2. The construction teacher receives the exact student-visible view plus a
   separately typed private construction envelope. That envelope may contain
   attack labels, ground-truth provenance, the attack-chain/campaign manifest,
   TP/FP/FN, coverage, MCC/ADP and counterfactual detector outcomes.
3. Those private fields may be used only for candidate generation, trajectory
   filtering and detection-effectiveness validation.
4. The target renderer permits only typed memory use, structured visible detection
   evidence, diagnosis, action justification and optional tool/write candidates
   whose claims close over the student-visible view.
5. Actual tool results are inserted by the harness.
6. The private evaluator checks trajectory quality and validates detection
   effectiveness on agent-training data.
7. Every candidate passes sanitization and evidence-closure validation before SFT
   export. A decision that depends on private information to be valid is rejected;
   the teacher cannot emit it as a student target.
8. Human review samples rare actions, multi-PIDS conflicts, leakage risks,
   stateful-PIDS cases and teacher/rule disagreements.

### 5.3 Teacher and evaluator responsibilities

The construction teacher may use the isolated private envelope to generate and
screen SFT demonstration candidates. Private information can determine which
detector/action candidates deserve construction, but it is not itself a target and
cannot serve as student-visible evidence.

The evaluator has two bounded responsibilities:

- trajectory quality checking, including schema, causality, tool validity,
  visible-evidence closure and leakage checks;
- detection effectiveness validation, including whether private detector outcomes
  support retaining, rejecting or balancing a candidate.

The evaluator is a construction-time checker, not a model-optimization component,
and does not emit online scalar training feedback. Evaluator output stays in the
private construction ledger and is never supplied to the student or deployment
Agent.

## 6. Private construction information boundary

This boundary separates information used to construct the corpus from information
the trained Agent may receive. The separation is enforced with distinct schemas,
process permissions, artifact roots and recursive sanitization; a prompt convention
alone is insufficient.

### 6.1 Offline SFT demonstration construction

The isolated teacher/evaluator construction process may use:

- attack labels;
- ground-truth provenance;
- the versioned attack-chain or campaign manifest;
- TP/FP/FN results with explicit scope and denominators;
- coverage;
- MCC and ADP;
- counterfactual detector outcomes on agent-training episodes.

These fields may be used only to generate high-quality demonstration candidates,
validate detector selection and detection effectiveness, filter invalid or
ambiguous detection trajectories, and balance the dataset. They remain in the
private construction envelope and private selection ledger. They cannot be copied,
paraphrased, cited, transformed into an evidence ID, or persisted into deployable
memory.

### 6.2 SFT student-visible input and target

Student-visible input and supervised assistant targets must not contain:

- an attack label or ground-truth value;
- TP/FP/FN or correctness attribution derived from them;
- MCC or ADP;
- any hidden evaluator result, rank, rationale or counterfactual-best marker.

The student view may contain only deployment-available classes of information:

- provenance evidence;
- standardized, label-blind PIDSMaker outputs;
- detector capability, availability and execution status;
- sanitized memory state and retrieval results;
- resource state and approved resource/configuration choices.

The private/public sanitizer is followed by evidence-closure validation on the
serialized SFT example. A candidate whose action is supported only by private
construction information is rejected rather than rewritten as if the support were
visible.

### 6.3 Deployment inference

The Frozen Agent receives only the same student-visible information classes and
high-level tool schemas used by sanitized SFT examples. It has no label store,
ground-truth manifest or hidden-evaluator channel. This schema and permission
equivalence is the deployment guarantee that prevents construction-only knowledge
from becoming an inference-time dependency.

## 7. Multi-PIDS demonstration coverage

### 7.1 Coverage definitions

| Coverage class | Minimum evidence | Eligible demonstration |
|---|---|---|
| `capability_awareness` | Validated registry/capability record | Inspect applicability, required state, output semantics, cost, limitations and availability; no execution claim |
| `successful_tool_use` | All-gates admission and real standardized result | Select/run/interpret the PIDS in the admitted role |
| `failure_or_rejection` | Deterministic admission/tool rejection or real typed failure | Diagnose failure, avoid fabrication, choose fallback and optionally distill failure experience |

The coverage manifest keys every example by:

```text
PIDS × variant × dataset/environment × role × coverage_class × action × memory_case
```

### 7.2 Eight-PIDS requirement

VELOX, ORTHRUS, MAGIC, FLASH, KAIROS, NODLINK, ThreatRace and R-CAID each require:

- capability-awareness examples in multiple visible environment/behavior contexts;
- explicit limitations and unavailable/compatibility behavior where applicable;
- independent counts for successful tool use;
- independent counts for real failure/rejection.

No PIDS is removed because execution is temporarily unavailable. Unavailable
systems contribute capability and valid rejection supervision. Successful
demonstrations wait for the exact admitted use and are never replaced with
synthetic tool success.

The coverage accounting freezes two independent measures:

```text
capability-awareness coverage != successful-execution coverage
```

In mathematical terms, capability-awareness coverage ≠ successful-execution
coverage.

- **Capability-awareness coverage:** all eight PIDS must have examples grounded in
  validated capability records, including inputs/outputs, required state,
  applicability, cost, limitations and availability.
- **Successful-execution coverage:** a `successful_tool_use` example counts only
  when the exact PIDS use has passed admission, a real execution has been validated,
  and a standardized label-blind output is present.

A capability description, registry entry, documentation example, fixture or
admission-pending result cannot substitute for a real successful execution. The
coverage report publishes these two measures separately for every PIDS.

### 7.3 Capability-specific coverage

| PIDS | Required capability lesson | Important construction guard |
|---|---|---|
| VELOX | Lightweight event-surprise fast path and threshold behavior | Do not generalize bounded CADETS validation approval to other datasets/uses |
| ORTHRUS | Temporal/local-graph event surprise and variant choice | Preserve default/fixed/non-snooped identity and causality/state differences |
| MAGIC | Embedding-outlier capability | Teach current causal limitation; no successful current test-informed path |
| FLASH | Semantic/positional node-role surprise | Feature-corpus causality and threshold portability must be explicit |
| KAIROS | Stateful temporal event modeling | Ordering, reset/replay/warm-up and cost evidence are mandatory |
| NODLINK | Node-feature reconstruction | Preserve undirected/reconstruction semantics; do not claim attack graph output |
| ThreatRace | Node-role surprise | Do not teach absent multi-model/tracing paper behavior |
| R-CAID | Root-context anomaly | Do not claim root-cause output; pseudo-graph timing and transductive limits remain visible |

## 8. Memory supervision

### 8.1 Fixed backend boundary

Memory is the Agent's adaptation mechanism while model weights remain fixed during
deployment. The backend, schema, namespaces, lexical/index behavior, ranking,
candidate cap, result count policy, deduplication, conflict storage, sanitization,
capacity and actual writes are harness-owned.

SFT does not train or replace the retrieval algorithm. Demonstrations must reflect
the exact memory harness version used in deployment.

### 8.2 Supervised memory behaviors

| Behavior | Target |
|---|---|
| Read decision | Decide `needed=true/false` from observable information need, trigger and budget |
| Query construction | Use allowlisted intent, environment filters, observable symptom, current PIDS/capability and policy-bounded result request |
| Retrieval use | Assign `use`, `downweight` or `ignore` to every returned record with public evidence |
| Applicability reasoning | Compare environment, behavior, PIDS capability, historical/temporal scope, state/reset, cost, failure conditions, recency and provenance |
| Conflict handling | Preserve conflicting records; explain which constraints support use/downweight/ignore without private outcome knowledge |
| Write candidate | Distill visible environment–temporal context–behavior–PIDS–action–outcome–cost–failure experience with uncertainty and evidence IDs |

### 8.3 Memory case library

The constructor deliberately includes:

- no-read decisions where the current prompt is sufficient;
- relevant same-environment memories;
- relevant cross-environment memories with applicable capability patterns;
- stale or state-incompatible memories;
- conflicting recommendations with different evidence/support/recency;
- empty retrieval results;
- duplicate/conflicting write-candidate rejection;
- successful Working/Episode write candidates;
- held-out/static-LTM write rejection in boundary tests, never as formal held-out
  data.

An experience-distillation target may record only public outcomes already observed.
It cannot claim that an alert was correct, name an attack, or summarize private
evaluation.

## 9. Data validation

### 9.1 Demonstration validator

The validator runs before sanitization and again on the sanitized/exported form.

| Check | Required validation |
|---|---|
| Schema | Strict canonical types, required IDs/versions/hashes, no unknown fields, finite numerics, assistant response parse and export round trip |
| Tool validity | Tool/action match, approved opaque choice, call/result ID pairing, argument allowlist, admitted use, no CLI/path/CUDA/stage/resource internals |
| Temporal consistency | `[start,end)` alignment, chronological episode, committed result before observation/trigger, past-only history, no current-window rewrite, future effective transition |
| Privileged leakage | Recursive forbidden keys/values, semantic correctness phrases, attack/campaign/time mappings, metrics, private rationale, raw evaluation and hidden paths |
| Evidence grounding | Every symptom, evidence statement and justification resolves to prompt/prior tool evidence; uncertainty and fallback are present; the structured detection evidence summary contains no chain-of-thought or private reasoning trace |
| Memory protocol | Exact read→tool→use/action order, disposition for each record, namespace/scope, no claimed write before harness result |
| Episode split | Partition by episode/scenario/counterfactual group before selection; no window, memory, repeated run or near duplicate crosses splits |
| PIDS coverage | All eight capability-awareness minima; successful and failure/rejection counts separately evidenced; variant/role/admission exact |
| Tool-result causality | Alternative outputs appear only after their actual tool result; committed and additional roles never merge |
| Export/loss | System/user/tool messages masked, assistant messages supervised, tokenizer template/version bound, tool boundaries preserved |

### 9.2 Evidence-closure algorithm

For every assistant target, the validator constructs the allowed evidence set from:

1. the exact `ModelPromptObservation`;
2. sanitized retrieved memory records in the current exchange;
3. earlier public tool results in the same trajectory;
4. opaque approved capability/config catalog entries actually included in the
   prompt.

Every evidence ID, memory ID, candidate ID and action justification must close over
that set. Facts available only in `private_evaluation_ref` cause rejection. If the
chosen action is privately superior but not distinguishable from visible evidence,
the trajectory is rejected as ambiguous.

### 9.3 Validation outputs

The validator emits:

- accepted canonical trajectory ID and hash;
- sanitizer/export disposition;
- coverage dimensions;
- typed rejection codes and offending field paths;
- evidence-closure report;
- episode/group split report;
- tool pairing and timing report;
- privileged-leakage scan version;
- human-review status where required.

## 10. Pilot SFT dataset plan

### 10.1 Initial pilot construction budget

The pilot verifies the dataset construction pipeline, schema correctness, validator
correctness and coverage accounting. The following numbers are an **initial pilot
construction budget / engineering target** used for planning and exercising those
mechanisms. They are examples, not fixed corpus requirements, acceptance quotas,
optimal training sizes or runtime constants.

| Item | Example engineering budget |
|---|---:|
| Dataset manifests | 3 |
| Selected chronological windows | 72 total: 24 per dataset |
| Candidate demonstration trajectories | 192 |
| Canonical PIDS capability classes | 8 |
| Frozen Agent actions | 8 |
| Candidate counterfactual PIDS comparison trajectories | 48 |

The actual accepted trajectory count is determined by exact PIDS admission,
teacher-generation quality, validation pass rate, privileged-leakage rejection and
tool availability. The builder must never fabricate an execution, tool result,
evidence item or trajectory to reach an engineering target.

Proposed pilot manifests:

1. `CADETS_E3` — FreeBSD and the currently accepted bounded VELOX validation path;
2. `THEIA_E3` — Linux environment diversity;
3. `FIVEDIRECTIONS_E3` — additional platform diversity, with its upstream OS
   documentation conflict explicitly retained in the manifest.

The example allocation gives each dataset one contiguous chronological block of 24
aligned windows under its accepted construction policy. The actual pilot may use a
smaller validated set. The builder does not change window size or relax admission
to reach the example budget. Private evaluation may filter candidate trajectories
after construction, but cannot alter the public window sequence.

If a proposed dataset cannot pass source/permission/manifest validation, it is
replaced only through a reviewed manifest revision; `optc_h201` is the first
reserve after its database mapping is approved.

### 10.2 Illustrative trajectory allocation

The 192 candidate-trajectory budget is illustratively stratified by final action:

The action values below are the canonical names frozen by
`AGENT_RUNTIME_CONTRACT_FREEZE.md`. Legacy design names such as `SWITCH_PIDS`,
`LOAD_TUNED_CONFIG` and `ADJUST_RESOURCE_CONFIG` are not serialized SFT action
values; the Dataset Builder must not introduce an alias or semantic-mapping layer.

| Canonical runtime action | Example candidate count |
|---|---:|
| `KEEP_CURRENT_CONFIG` | 36 |
| `RUN_ADDITIONAL_DETECTOR` | 32 |
| `SELECT_VALIDATED_THRESHOLD` | 28 |
| `LOAD_APPROVED_CONFIG` | 24 |
| `SWITCH_DETECTOR` | 24 |
| `RETRAIN_DETECTOR` | 12 |
| `SELECT_RESOURCE_PRESET` | 12 |
| `FINISH_DIAGNOSIS` | 24 |
| **Example total** | **192** |

These are candidate-construction strata, not acceptance quotas. An action/tool
demonstration is accepted only when its approved choice and result/rejection are
real and valid. An unfilled stratum remains reported as unfilled; it is not
completed with invented tool output or a fabricated trajectory.

### 10.3 PIDS coverage allocation

- Example capability-awareness budget: 96 candidate trajectories = 8 PIDS × 3
  environments × 4 visible behavior/capability contexts.
- Every PIDS appears in at least one counterfactual capability-choice group.
- Every PIDS has at least two deterministic failure/rejection cases per pilot
  environment when such a real rejection condition exists.
- Successful-tool-use counts are reported for each PIDS separately and are filled
  only after admission. The pilot release report distinguishes planned, accepted,
  unfilled-admission and rejected counts.
- The 96 awareness examples, successful examples and failure examples may overlap
  in one trajectory only when all coverage labels are evidence-backed; awareness
  never implies success.

### 10.4 Illustrative memory case allocation

The following memory strata are example construction targets that overlap the 192
candidate trajectories:

| Memory case | Minimum target |
|---|---:|
| `needed=true` read decision | 144 |
| `needed=false` with deterministic empty tool result | 48 |
| Applicable record use | 64 |
| Conflicting-record resolution | 32 |
| Stale/inapplicable downweight or ignore | 32 |
| Empty retrieval | 16 |
| Experience-distillation write candidate | 64 |
| Write rejection/dedup/conflict handling | 16 |

Exact memory result count and retrieval constants remain those of the versioned
harness and are not inferred from these corpus quotas.

### 10.5 Pilot construction acceptance

The pilot is accepted as a construction corpus only when:

- every included manifest and chronological window ledger validates;
- every accepted trajectory passes canonical and export validators;
- all 8 PIDS meet capability-awareness coverage;
- capability-awareness and successful-execution coverage are reported separately;
- every action stratum is reported as planned, accepted, rejected or unfilled,
  with admission/tool gaps preserved explicitly;
- private/public separation and episode/group disjointness pass;
- the coverage, rejection and ambiguity reports are complete;
- the release manifest reports actual dataset, window, candidate, accepted,
  counterfactual and per-PIDS counts rather than substituting the example budget;
- no SFT weight update is part of pilot acceptance.

## 11. Implementation roadmap

### 11.1 Existing reusable code

| Component | Current evidence | Reuse decision |
|---|---|---|
| PIDS/dataset discovery | `src/apt_detection_agent/pidsmaker/discovery.py`, dynamic PIDSMaker configs, dataset/model inventories | Reuse for registration; do not treat registration as admission |
| Eight-gate admission | `src/apt_detection_agent/schemas/admission.py`, `tests/test_pids_admission.py` | Reuse; add manifest/coverage joins |
| Causal window/runtime | `src/apt_detection_agent/schemas/agent_runtime.py`, `src/apt_detection_agent/controller/frozen_runtime.py`, append-only committed ledger | Reuse as trajectory timing authority |
| Observation builders | `src/apt_detection_agent/controller/observation_builders.py` and canonical/prompt schemas | Reuse; extend deterministic detection-context and historical/temporal inputs without changing authority |
| Memory protocol/backend | `src/apt_detection_agent/controller/memory_protocol.py`, `src/apt_detection_agent/schemas/memory_runtime.py`, memory store/tools | Reuse exact two-assistant exchange and fixed retrieval/write boundary |
| PIDSMaker adapter/runners | structured adapter, causal/stage runners, frozen bundle validation scripts | Reuse executor-owned invocation and provenance gates |
| VELOX result path | `src/apt_detection_agent/pidsmaker/results.py`, structured adapter smoke, frozen CADETS bundle | Reuse only for its accepted bounded scope |
| Teacher/student separation | `src/apt_detection_agent/sft/frozen_teacher.py`, `frozen_sanitizer.py`, `frozen_contracts.py`, `frozen_builder.py` | Reuse private/public envelope, hashing and group partitions |
| Hidden evaluator | privileged evaluator schemas/process and private metrics | Reuse only for selection/filtering; never merge into public records |

### 11.2 New code required

| Deliverable | Required implementation | Depends on |
|---|---|---|
| Dataset parser/manifest builder | Parse source inventories and public metadata; create public/private manifests, source hashes, graph policy and split/use records | Dataset permissions and campaign-manifest review |
| PIDSMaker demonstration executor wrapper | Materialize declared execution matrix, join admission, invoke structured adapter, retain role/state/cost/failure provenance | Existing adapter/runners; per-PIDS admitted bundles |
| Per-PIDS output parsers | Convert real VELOX, ORTHRUS, MAGIC, FLASH, KAIROS, NODLINK, ThreatRace and R-CAID artifacts into standardized public results | Independent real artifacts and score semantics |
| Offline run table builder | Build `OfflineRunRecord`, detection context, historical/temporal context, coverage labels and counterfactual groups with public/private columns | Manifests, runtime traces, capability registry |
| Observation input provider extension | Deterministically populate environment, behavior, detection context, visible history, capability options, cost/failure and memory summaries | Offline table/public runtime state |
| Teacher generator | Rule candidate engine, deployment-view prompt runner, strict assistant parser, expert override/review records | Frozen actions/tools and prompt schemas |
| Tool-result transcript assembler | Pair memory/runtime calls with real results, build supplemental prompts and preserve committed/additional separation | Existing memory/runtime services |
| Canonical multi-turn trajectory schema | Represent multiple assistant/tool turns, counterfactual comparison, evidence grounding, experience distillation and final closure | Runtime/teacher contracts |
| Demonstration validator | Implement schema/tool/time/leakage/evidence/memory/split/coverage/export checks and ambiguity rejection | All canonical records |
| Sanitizer extension | Recursively sanitize new historical, comparison, grounding and multi-turn fields without copying private selection rationale | Existing frozen sanitizer |
| JSONL exporter | Emit canonical JSONL and OpenAI-compatible messages/tool calls, assistant loss masks, round-trip and hashes | Validated sanitized trajectories; tokenizer/tool manifests |
| Coverage/report builder | Produce dataset/PIDS/action/memory matrices, planned/accepted/unfilled/rejected counts and human-review samples | Validator/export manifests |

### 11.3 Implementation sequence

1. Freeze `DatasetManifest`, private companion, `OfflineRunRecord` (including
   detection context), coverage and canonical multi-turn trajectory schemas.
2. Implement manifest parsing and private/public path/permission negative tests.
3. Implement offline run builder using existing VELOX real evidence plus
   capability/rejection fixtures for contract tests only.
4. Implement historical/temporal context builders and causality tests.
5. Implement counterfactual grouping and score-semantic comparability rules.
6. Implement rule candidate generator and strict teacher output parser.
7. Implement transcript assembler over the existing memory protocol and runtime
   high-level tools.
8. Implement validator, sanitizer extension and ambiguity/leakage negative tests.
9. Implement canonical and OpenAI-compatible JSONL export with assistant-only loss
   masks and tokenizer round trip.
10. Run synthetic contract tests without formal claims.
11. Construct the reviewed pilot only from admitted real sources and record unfilled
    coverage honestly.

### 11.4 Completion gate

Dataset Builder construction implementation is complete only when the pilot manifests,
offline records, canonical trajectories, sanitized exports, coverage matrix,
rejection ledger, hashes and human-review evidence all validate. A successful
process exit, synthetic fixture, capability registry entry, or private metric alone
is insufficient.

## 12. Phase 3 conclusion

The demonstration pipeline converts admitted, causally ordered PIDSMaker evidence
into supervised multi-turn memory/diagnosis/tool trajectories while preserving a
strict private evaluator boundary. It retains all eight PIDS at the capability
level, promotes successful examples only after admission, and turns failures into
typed fallback demonstrations rather than fabricated outputs.

The initial pilot uses 3 datasets, 72 windows, 192 candidate trajectories and 48
candidate counterfactual trajectories as an example engineering budget for
construction validation and coverage accounting. Actual accepted counts are
evidence- and validation-dependent. This plan ends at validated JSONL export; it
does not include model training.

## 13. Phase 3 design freeze statement

Upon approval of this document, the **SFT Demonstration Construction Plan is
frozen** as the implementation baseline for the next phase.

The next phase is:

```text
Phase 4: SFT Dataset Builder Implementation
```

Phase 4 implements only the frozen construction contracts:

- `DatasetManifest` schema;
- `PIDSAdmissionRecord` schema, reusing and freezing the existing admission
  contract;
- `OfflineRunRecord` schema;
- canonical agent execution/detection trajectory schema;
- demonstration validator;
- private-to-student sanitizer;
- canonical and OpenAI-compatible JSONL exporter.

Phase 4 does not modify the Agent runtime architecture, SFT objective, or frozen
observation/action boundary. Those are inputs to the Dataset Builder, not
implementation choices to reopen.
