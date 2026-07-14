# APT-Agent SFT Dataset Design

Requirements: REQ-GOV-003..004, REQ-CAUSAL-001..004,
REQ-LABEL-001..004, REQ-WINDOW-001..004, REQ-CONFIG-001..003,
REQ-PIDS-001..005, REQ-TOOL-001..005, REQ-MEMORY-001..007,
REQ-ARTIFACT-001..003, REQ-RESOURCE-001..003, REQ-REPRO-001..003,
REQ-SFT-001..004.

Status: Phase 2 dataset design for review. This document defines a future formal
SFT corpus and export contract. It does not generate real or synthetic examples,
run PIDSMaker, train a model, approve a PIDS, or modify runtime behavior.

Normative runtime inputs are:

- `docs/AGENT_RUNTIME_CONTRACT_FREEZE.md`;
- `docs/AGENT_TOOL_CAPABILITY_SPEC.md`;
- `docs/PIDSMaker_FRAMEWORK_NOTE.md`;
- `docs/PIDSMaker_CAPABILITY_CATALOG.md`;
- `docs/design/APT_Detection_Agent_Design_v0.4.md` where it is not superseded by
  the runtime freeze.

The existing `HiddenTeacherRecord` and `StudentSFTExample` are useful safety
primitives, but their one-observation/one-action shape is not the final multi-turn
dataset contract defined here.

## 1. SFT training objective

### 1.1 What the Agent learns

APT-Agent SFT teaches a frozen-policy controller to map deployment-visible state
to bounded orchestration decisions. It learns:

| Objective | Learned behavior |
|---|---|
| Detector orchestration | Understand active/candidate capability, availability, cost, state, and limitations; preserve or request an approved change without touching PIDSMaker internals |
| Investigation planning | Decide whether existing evidence is sufficient, whether an approved additional detector is justified, and when to stop investigating |
| Memory usage | Decide whether to retrieve; form an allowlisted query; use, downweight, or ignore each returned record; cite memories actually used; propose bounded writes |
| Tool selection | Select one frozen high-level action/tool, use only approved opaque IDs, respect current-versus-next-window semantics, and provide a safe fallback |
| Evidence-based diagnosis | Explain the observable symptom using graph/score/alert/trend/state/resource evidence without labels, evaluator metrics, or unsupported claims |

The target is a deployable policy over this causal relation:

```text
ModelPromptObservation
→ memory_read_request
→ memory_use_decision
→ diagnosis
→ ActionDecision
→ optional tool call / memory write candidate
```

The model is supervised on typed assistant outputs, not on harness operations. Loss
is applied only to assistant-authored tokens/fields. System, user, and tool messages
are context and are masked from the language-model loss.

The desired rationale is a concise evidence-grounding record, not private chain of
thought. It cites visible evidence and explains action constraints sufficiently for
audit, while omitting hidden teacher reasoning.

### 1.2 What the Agent does not learn

The SFT corpus does not teach the Agent to:

- train, emulate, or replace a detector model;
- classify attacks, campaigns, techniques, or malicious entities directly;
- infer hidden labels from dataset identity, attack timing, or private mappings;
- optimize or query the hidden evaluator, MCC, TP/FP/FN, coverage, ADP, or another
  private metric at runtime;
- generate PIDSMaker CLI, CUDA/device choices, checkpoint/artifact paths, pipeline
  stages, model architecture, or arbitrary numeric parameters;
- rewrite a committed current-window result;
- learn a retriever, memory storage engine, threshold value, resource scheduler, or
  PIDS checkpoint through language modeling;
- imitate privileged teacher rationale or counterfactual best-action text.

Private evaluation may help select and quality-control training trajectories on
agent-training scenarios. It is not a student input, model-visible objective, or
runtime feedback channel.

### 1.3 Supervision targets

Assistant supervision is factored into auditable targets:

1. memory-read decision and valid query;
2. per-record memory-use decision;
3. explicit observable symptom statement;
4. graph, score, trend, and resource evidence grounding;
5. uncertainty statement distinguishing observed, inferred, unknown, and
   unavailable facts;
6. diagnosis code and concise visible-evidence explanation;
7. frozen action type and approved choice ID when required;
8. action justification connecting the symptom, evidence, uncertainty,
   capability, expected visible effect, and fallback;
9. optional memory write candidate;
10. tool-call syntax for actions that actually invoke a public tool.

Every target `ActionDecision` therefore carries a structured grounding block:

```text
VisibleEvidenceGrounding {
  observable_symptom
  graph_evidence_ids[]
  score_evidence_ids[]
  trend_evidence_ids[]
  resource_evidence_ids[]
  observed_facts[]
  bounded_inferences[]
  unknowns[]
  uncertainty
  action_justification
}
```

`VisibleEvidenceGrounding` is a **structured evidence summary**, not chain-of-
thought (CoT) distillation. It records externally checkable claims, evidence
references, bounded uncertainty, and the action justification needed for audit. It
must not contain hidden intermediate reasoning, private scratch work, token-level
thought traces, teacher CoT, or a paraphrase of privileged evaluator rationale.
Only the final compact grounding fields are supervised.

The validator must resolve every evidence ID to the current sanitized prompt or a
prior public tool result, reject unsupported claims, and require the justification
to explain why the chosen action is preferable to the declared fallback under the
visible uncertainty. Empty evidence categories are allowed only when explicitly
marked not applicable; invented evidence is not.

TP/FP/FN/TN, MCC, ADP, precision/recall/F1, campaign coverage, attack identity,
and any other hidden-label or evaluator-derived value are forbidden as student
inputs **and as supervision targets**. They may be used only inside the isolated
private evaluator for candidate selection and corpus analysis.

Exact weights among these targets are not selected by this design and require a
future training experiment.

## 2. Dataset unit definition

### 2.1 Sample versus trajectory versus episode

| Candidate unit | Definition | Strength | Failure mode if used alone |
|---|---|---|---|
| Sample | One serialized model input/target pair or one JSONL training row | Easy batching and loss accounting | Can erase memory/tool ordering, tool-result causality, and action fallback context |
| Trajectory | One causally ordered slow-path decision sequence, including prompt, assistant turns, memory/tool results, action, and closure | Preserves the behavior the model must reproduce while remaining bounded | Requires explicit parent episode/window identities and careful export chunking |
| Episode | One complete deployment scenario across all chronological windows | Preserves full long-horizon state and action history | Usually too long and highly correlated for one context; mixes automatic no-LLM windows with sparse slow paths |

### 2.2 Frozen choice

The **canonical semantic training unit is a trajectory**.

An `Episode` remains the isolation, provenance, grouping, and dataset-split unit. A
`Sample` is only an export artifact derived from a canonical trajectory. Therefore:

```text
Episode (split/isolation unit)
  └── WindowStep(s)
        └── zero or more slow-path Trajectories (semantic SFT unit)
              └── one or more exported Samples (serialization unit)
```

This choice preserves tool/memory turn order and supplemental investigation while
avoiding full-episode context overflow. It also prevents random window-level splits
from leaking nearly identical environment, memory, config, and event history across
train and validation.

### 2.3 Trajectory boundary

A canonical trajectory begins when a frozen trigger opens a slow path for a
committed `WindowStep`. It ends when:

- a terminal action is selected and its optional tool result is recorded;
- a declared fallback closes a failed tool call; or
- the bounded investigation budget closes with `FINISH_DIAGNOSIS`.

Untriggered windows have no assistant turn. Their harness-default
`KEEP_CURRENT_CONFIG` records stay in the `Episode` audit but are not fabricated as
SFT conversations. Slow-path examples that legitimately choose
`KEEP_CURRENT_CONFIG` remain valid assistant supervision.

If a long trajectory must be split for a model context, every exported sample must
start at a causally valid prompt boundary, include all tool results required by its
target assistant turn, and retain parent trajectory/episode IDs. Arbitrary token
slicing across a tool call/result pair is forbidden.

## 3. Canonical trajectory schema

### 3.1 Canonical root

The canonical source-of-truth is a versioned, role-aware runtime/teacher record,
not tokenizer-rendered text:

```text
CanonicalSFTCorpus
  ├── CorpusManifest
  └── Episode[]
        ├── WindowStep[]
        │     ├── Observation
        │     └── Trajectory[]
        │           ├── AssistantMessage[]
        │           ├── ToolCall[]
        │           ├── ToolResult[]
        │           ├── MemoryInteraction
        │           ├── ActionDecision[]
        │           └── FinalReport
        └── private_teacher_trace_ref (private store only)
```

Every record has `schema_version`, stable identity, source IDs, content hash,
creation time, and producer/builder version. Program facts and LLM generations are
stored separately even when they are rendered into one assistant message.

### 3.2 `Episode`

| Field group | Examples | Source |
|---|---|---|
| Identity | `episode_id`, `scenario_id`, dataset/environment profile ID, source split | Program |
| Runtime provenance | project/PIDSMaker SHAs, admitted PIDS records, catalog versions, prompt/memory policy versions | Program |
| Temporal scope | ordered window IDs, start/end, timezone, reset boundaries | Program |
| Isolation | memory namespace, split assignment, private/public store references | Program |
| Contents | ordered `WindowStep` references | Program |
| Private linkage | opaque `private_teacher_trace_ref` | Program; never student export |

Episodes are assigned to train or validation before trajectories are exported. All
windows and trajectories from one episode stay in exactly one partition.

### 3.3 `WindowStep`

| Field group | Examples | Source |
|---|---|---|
| Window identity | aligned `[start,end)`, sequence number, origin/timezone | Program |
| Committed state | detector/config/checkpoint/threshold/resource-preset IDs | Program |
| Fast path | state snapshot, committed result/failure reference, commit time | Program/harness |
| Observation | raw-state private ref, canonical observation, optional prompt refs | Program/harness |
| Trigger | triggered boolean, reason codes, trigger-profile version | Program/harness |
| Slow path | zero or more ordered trajectory references | Program ordering; contents mixed below |
| Transition | pending-state admission and next-window activation result | Program/harness |

The committed fast path is never represented as an assistant tool call.

### 3.4 `Observation`

| Field group | Examples | Source |
|---|---|---|
| Canonical state | `CanonicalAgentVisibleObservation` payload/hash | Program, deterministic |
| Trigger envelope | trigger decision/reasons added only after canonical construction | Program, deterministic |
| Prompt projection | `ModelPromptObservation` payload/hash, prompt-builder/tokenizer/tool-manifest versions | Program, deterministic |
| Supplemental state | sanitized additional-detector or action-tool result references used in a later prompt | Program, deterministic |

`RawExecutionState` stays in the runtime evidence store and is referenced by hash;
it is never embedded in the student corpus. No observation field is authored by an
LLM. Prompt compression/truncation must be the exact version used in deployment.

### 3.5 `AssistantMessage`

| Field group | Examples | Source |
|---|---|---|
| Envelope | message ID, parent prompt ID, turn index, role, timestamps, model/prompt version | Program/harness |
| Generated content | memory-read request; memory-use decisions; observable symptom; graph/score/trend/resource grounding; uncertainty; diagnosis; action justification; action; confidence/fallback; optional write candidate | Teacher LLM or human expert |
| Tool intent | requested public tool name and allowlisted argument proposal | Teacher LLM or human expert |
| Validation | parse result, schema-valid flag, evidence-grounding result, repair count | Program/validator |
| Provenance | teacher strategy/model/human-review IDs | Program |

Only validated generated content is eligible for export. Internal reasoning, hidden
teacher rationale, discarded repair attempts, and private evaluator comments are
not student targets.

### 3.6 `ToolCall`

| Field group | Examples | Source |
|---|---|---|
| LLM proposal | public tool name, opaque candidate ID, visible evidence IDs, bounded typed arguments | Teacher LLM/human |
| Harness envelope | tool-call ID, case/window scope, execution role, requested time | Program |
| Validated request | canonical arguments after allowlist/schema checks | Program/validator |
| Rejection | typed public rejection code when invalid/unavailable | Program/validator |

The LLM never supplies command, path, environment, CUDA/device, checkpoint path,
resource values, or pipeline stage. Committed fast-path inference is not a
`ToolCall` in the SFT dialogue.

### 3.7 `ToolResult`

| Field group | Examples | Source |
|---|---|---|
| Identity/status | matching tool-call ID, status, start/end, sanitized failure code | Program/executor |
| Public result | retrieved memory records, additional detector summary, admission result, pending transition | Program/executor |
| Runtime summary | visible elapsed/resource/health/cache classes and opaque provenance IDs | Program/executor |
| Private evidence | raw output, command manifest, internal stages, evaluator result | Separate runtime/private stores; references only, never student payload |

Tool results are model context, not model targets. The corpus must preserve exact
call/result pairing and chronological order.

### 3.8 `MemoryInteraction`

| Field group | Examples | Source |
|---|---|---|
| Read request | `needed`, query intent, filters, observable symptom, requested policy-bound result count | Teacher LLM/human |
| Retrieved records | sanitized record IDs/content, confidence, applicability/failure conditions, retrieval provenance | Program memory harness |
| Applicability reasoning | Environment/behavior/PIDS/temporal/cost/state compatibility and recency/provenance assessment for each record | Teacher LLM/human |
| Conflict resolution | Explicit comparison of conflicting recommendations/evidence and retained `use`/`downweight`/`ignore` decisions | Teacher LLM/human |
| Use decision | one `use`, `downweight`, or `ignore` decision and visible-evidence reason per returned record | Teacher LLM/human |
| Experience distillation/write candidate | target runtime layer, visible environment/temporal/behavior/PIDS/action/outcome/cost/failure context, applicability, uncertainty, confidence, reason | Teacher LLM/human |
| Actual write | accepted/rejected, namespace, dedup/conflict result, sanitized stored record ID | Program memory harness |

Retrieval ranking, result cap, storage, sanitization, and actual writes remain
harness functions. A write candidate cannot claim an action-tool outcome that had
not yet occurred.

Memory is the Agent's primary deployment-time adaptation mechanism while model
weights remain frozen. SFT must therefore supervise three distinct memory
behaviors rather than merely demonstrate retrieval syntax:

1. **Memory applicability reasoning:** compare the retrieved record's environment,
   observable symptom, PIDS capability, temporal scope, state/reset assumptions,
   cost regime, applicability conditions, and recency/provenance with the current
   visible context. The target explains `use`, `downweight`, or `ignore` through
   structured visible fields, not hidden outcome knowledge.
2. **Memory conflict resolution:** when records recommend different actions or
   report different failure conditions, preserve all records and evaluate their
   compatibility, support, recency, evidence quality, and current constraints.
   The Agent must not invent consensus, delete a conflicting record, or choose the
   record whose private evaluator outcome was best.
3. **Experience distillation trajectory:** after a public action/tool outcome is
   available, produce a candidate record containing environment, temporal context,
   observable behavior, PIDS capability, action, deployment-visible outcome, cost,
   failure/applicability conditions, uncertainty, and evidence provenance. The
   harness sanitizes, deduplicates, scopes, and decides whether/where to write it.

These trajectories teach adaptation through retrieval and scoped experience, not
online weight updates. Held-out experience cannot update static LTM, and private
labels or evaluator metrics cannot enter an experience-distillation target.

### 3.9 `ActionDecision`

| Field group | Examples | Source |
|---|---|---|
| Decision content | frozen action type, diagnosis code/text, `VisibleEvidenceGrounding`, used memory IDs, approved choice ID, confidence, expected visible effect, fallback | Teacher LLM/human |
| Runtime resolution | tool required, candidate admitted, effective sequence, pending-state ID, terminal/evidence-acquiring class | Program/harness |
| Outcome | tool success/failure, fallback applied, state transition result | Program/harness |
| Source | `llm_agent`, `human_expert`, or `harness_default` | Program |

Harness-default `KEEP_CURRENT_CONFIG` records may appear in episode audit, but only
`llm_agent`/`human_expert` slow-path decisions become assistant targets.

### 3.10 `FinalReport`

`FinalReport` closes a canonical trajectory; it is not the hidden evaluation
report.

| Field group | Examples | Source |
|---|---|---|
| Closure | terminal action, tool/fallback status, pending-state status, end time | Program/harness |
| Public audit | evidence IDs used, memory IDs used/written, public result IDs, validation disposition | Program/harness |
| Optional conclusion | short deployment-visible analyst summary if the runtime protocol actually requested one | Teacher LLM/human, separately sanitized |
| Private linkage | opaque evaluator/teacher trace reference | Program; never exported in messages |

The deterministic closure is metadata. It must not be converted into a fictitious
assistant final answer when the frozen runtime would have ended after a tool
result.

### 3.11 Program-versus-LLM rule

In summary:

- observations, triggers, IDs, timing, committed results, retrieval results, tool
  results, admission, state transitions, resource facts, sanitization, and hashes
  come from programs;
- memory read/use intent, diagnosis, frozen action choice, allowed tool argument
  proposal, confidence/fallback, and optional write/conclusion text come from a
  teacher LLM or human;
- no LLM-generated value is accepted as an execution fact until the harness
  validates or executes it;
- private evaluator fields remain in a separate teacher store.

## 4. SFT export format

### 4.1 Frozen format choice

The canonical corpus uses **custom versioned JSONL records** for audit and
reconstruction. The final model-facing export uses **OpenAI-compatible chat/tool
JSONL** with a `messages` array and explicit `tool_calls`/`tool_call_id` linkage.

Raw ChatML control tokens are not stored. At training time, the pinned base model's
chat template renders the OpenAI-compatible messages. This avoids hard-coding one
model family's special tokens while preserving standard `system`, `user`,
`assistant`, and `tool` roles.

Each export row is one complete trajectory or one causally valid trajectory
segment. Metadata remains outside `messages` unless the runtime prompt builder
explicitly includes it.

### 4.2 Conceptual export record

The following is a schema illustration with placeholders, not generated training
data:

```json
{
  "schema_version": "apt-agent-sft-chat-v1",
  "sample_id": "<opaque-id>",
  "episode_id": "<opaque-id>",
  "trajectory_id": "<opaque-id>",
  "source_window_id": "<opaque-id>",
  "prompt_builder_version": "<version>",
  "tool_manifest_version": "<version>",
  "messages": [
    {
      "role": "system",
      "content": "<frozen runtime policy and action/tool contract>"
    },
    {
      "role": "user",
      "content": "<deterministic ModelPromptObservation>"
    },
    {
      "role": "assistant",
      "content": "<typed memory-read intent>",
      "tool_calls": [
        {
          "id": "<call-id>",
          "type": "function",
          "function": {
            "name": "retrieve_memory",
            "arguments": "<canonical JSON arguments>"
          }
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "<call-id>",
      "name": "retrieve_memory",
      "content": "<sanitized deterministic retrieval result>"
    },
    {
      "role": "assistant",
      "content": "<memory-use decisions, observable symptom, graph/score/trend/resource evidence, uncertainty, diagnosis, action justification, action, confidence, fallback, optional write candidate>",
      "tool_calls": []
    }
  ],
  "loss_policy": "assistant_messages_only",
  "canonical_trajectory_hash": "<sha256>",
  "rendered_prompt_hash": "<sha256>"
}
```

When the action invokes a tool, the second assistant message contains the matching
function call and is followed by a `tool` message. A supplemental additional-
detector investigation adds a new deterministic `user` prompt observation and a
new memory/assistant cycle. A no-tool terminal action has no fabricated tool
message.

### 4.3 Role semantics

| Role | Content | Authorship | Loss |
|---|---|---|---|
| `system` | Frozen authority boundary, action taxonomy, tool definitions, output schema | Program/versioned template | Masked |
| `user` | Deterministic `ModelPromptObservation`, including trigger and later supplemental public evidence | Program prompt builder | Masked |
| `assistant` | Memory intent/use, observable symptom, visible evidence grounding, uncertainty, diagnosis, action justification, action, allowed tool call, confidence/fallback, optional write candidate | Teacher LLM or human | Supervised |
| `tool` | Deterministic sanitized memory/runtime tool result | Harness | Masked |

Tool schemas are versioned in a separate manifest and bound by hash. The export
validator must parse every assistant JSON/tool call back into the canonical types.
Tokenizer rendering and loss-mask construction must round-trip without changing
message roles or tool-call boundaries.

### 4.4 Export validation

An export row is rejected if:

- a role is out of order or a tool result lacks a matching prior call;
- a required prompt/tool result is missing from the causal prefix;
- assistant content fails the frozen response schema;
- committed inference is represented as an Agent tool call;
- an action uses a non-approved ID or same-window persistent effect;
- a system/user/tool token is included in the assistant loss mask;
- canonical and rendered hashes or builder versions do not match;
- privileged, executor-owned, or raw PIDSMaker fields appear anywhere recursively.

## 5. Privileged information separation

### 5.1 Separate teacher roles

“Teacher” is split into two authorities:

1. **Dialogue teacher:** generates candidate assistant messages from exactly the
   deployment-visible `ModelPromptObservation` and sanitized tool results. It does
   not receive ground truth or private evaluation.
2. **Privileged evaluator/selector:** operates only on agent-training scenarios and
   may inspect private ground truth and counterfactual run outcomes to score,
   reject, or rank candidate trajectories. It does not write student-visible
   rationale and its outputs never enter runtime prompts.

This split is preferred over giving one dialogue model labels and hoping a string
sanitizer removes every causal trace.

### 5.2 What private teacher infrastructure may see

Within the physically isolated teacher/evaluator store, authorized components may
see:

- malicious/benign entity or event ground truth;
- private campaign/attack IDs, attack-to-window mappings, and attack chains;
- TP/FP/FN/TN, MCC, precision/recall, coverage, ADP, delay, and other evaluation
  metrics with correct denominators;
- per-action and counterfactual outcomes on agent-training scenarios;
- rejected candidate trajectories and private expert annotations;
- private teacher rationale explaining selection or rejection.

These fields exist for corpus selection, balance, error analysis, and audit. They
are not copied, summarized, paraphrased, or referenced in student content.

### 5.3 Student input and target prohibitions

Neither student input nor student target may contain:

- labels, ground truth, benign/malicious annotations, or per-alert correctness;
- TP/FP/FN/TN, MCC, ADP, precision/recall/F1, coverage, ROC-AUC, or another private
  metric;
- attack/campaign ID, name, phase, technique, private time mapping, or dataset-name
  shortcut that reveals attack identity;
- teacher-only rationale, counterfactual best action, reward, rank, or evaluator
  explanation;
- hidden artifact/database paths, raw PIDSMaker evaluation/triage outputs, or
  unsanitized failures;
- CLI, CUDA/device, checkpoint path, arbitrary stage/config/resource values;
- phrases that semantically reveal correctness, such as “most alerts were true.”

Student targets may cite only IDs present in the sanitized prompt/tool context.

### 5.4 Teacher trace to sanitized SFT trace

The transformation is:

```text
deployment-visible prompt
→ dialogue-teacher candidate trajectories
→ controlled tool execution on agent-training scenario
→ isolated privileged evaluation/ranking
→ selected private TeacherTrace
→ visible-evidence rationale validation/refinement
→ deterministic sanitizer
→ SanitizedSFTTrace
→ OpenAI-compatible export
```

`TeacherTrace` contains separate compartments:

```text
TeacherTrace {
  public_runtime_trace_ref
  candidate_assistant_sequences[]
  private_ground_truth_ref
  private_evaluation_ref
  private_selection_rationale
  selected_candidate_id
  human_review
}
```

`SanitizedSFTTrace` contains only the selected public causal sequence, sanitized
assistant outputs, approved tool messages, source hashes, and sanitizer/validator
provenance.

Sanitization must include strict schemas, recursive forbidden-key/value checks,
semantic leakage checks, evidence-ID closure, action/tool validation, split
validation, and sampled human review. A record that requires guessing whether it
leaks private information is rejected rather than repaired into the corpus.

## 6. Data generation pipeline

This is a design for a later controlled build. No step is executed in Phase 2.

### 6.1 Pipeline

```text
Raw dataset
→ PIDS admission and PIDSMaker replay
→ Observation builder
→ Dialogue teacher
→ Tool execution
→ Offline run table / counterfactual PIDS grouping
→ Private evaluation + validation/sanitization
→ SFT export
```

### 6.2 Stage contracts

| Stage | Input | Operation | Output |
|---|---|---|---|
| 0. Admission | Candidate PIDS/config/dataset plus checkpoint, threshold, parser, resource, state/reset, smoke, provenance evidence | Apply the frozen eight-part admission gate | `PIDSAdmissionRecord`; only admitted combinations proceed |
| 1. Raw dataset | Agent-training provenance and physically separate private ground truth/manifest | Verify hashes, split, chronology, schema, and permissions; never expose private store to runtime worker | Public replay manifest plus private evaluator manifest |
| 2. PIDSMaker replay | Public provenance, admitted committed state, aligned windows | Run harness-owned committed fast path chronologically; commit result/failure once; preserve executor provenance | `RawExecutionState`, committed result records, public artifact refs |
| 3. Observation builder | Raw execution state, committed state, visible history, frozen catalogs/trigger profile | Deterministically build canonical observation, decide trigger, and build prompt only when triggered | `CanonicalAgentVisibleObservation`, `TriggerDecision`, `ModelPromptObservation` and hashes |
| 4. Dialogue teacher | Exact model prompt, tool/action manifest, optional sanitized memory result | Produce typed memory request/use, observable symptom, graph/score/trend/resource grounding, uncertainty, diagnosis, action justification, action/tool call, fallback, and write candidate from visible evidence only | Candidate `AssistantMessage`, `MemoryInteraction`, and `ActionDecision` records |
| 5. Tool execution | Validated candidate tool call and admitted runtime/memory state | Harness executes public tool, sanitizes result, applies no-current-window-rewrite rule, and optionally builds supplemental prompt | Paired `ToolCall`/`ToolResult`, pending-state result, or supplemental observation cycle |
| 6. Offline run table | Public runtime/tool traces, environment/behavior/capability records, cost/failure summaries, and isolated private evaluation references | Build Environment–Behavior–PIDS compatibility rows and counterfactual groups across admitted PIDSs | Versioned `OfflineRunRecord` table with public/private field separation |
| 7. Private evaluation and corpus validation | Candidate public trajectories, offline run groups, and isolated agent-training truth/counterfactual outcomes | Privately rank/select; then validate causality, schema, evidence, tool pairing, action timing, admission, leakage, uniqueness, and human-review policy | Private `TeacherTrace`; public `SanitizedSFTTrace`; rejection report |
| 8. SFT export | Approved sanitized trajectories, episode partition, prompt/tool/tokenizer manifests | Serialize canonical JSONL and derive OpenAI-compatible chat/tool JSONL with assistant-only loss masks | Versioned corpus/export manifests, hashes, train/validation files, audit report |

### 6.3 Offline run table

The offline run table is the multi-PIDS evidence backbone for teacher selection,
counterfactual grouping, capability comparison, and memory distillation. It is not
a PIDSMaker-provided table and is not directly exported to the student.

Every row binds an environment, an observable behavior pattern, one PIDS
capability/config/action, its deployment-visible outcome, cost, and failure
conditions:

```text
OfflineRunRecord {
  run_record_id
  counterfactual_group_id
  episode_id
  window_or_range_id

  environment_profile
  observable_behavior
  historical_evidence_context
  temporal_context
  pids_capability

  detector_id
  variant_id
  approved_config_id
  action_type

  deployment_visible_outcome
  cost
  failure_condition

  public_runtime_trace_ref
  private_evaluation_ref
  provenance
}
```

Required compatibility fields are:

| Field | Required content | Student visibility |
|---|---|---|
| `environment_profile` | Platform/provenance schema, graph scale/density, entity/relation distributions, event-rate/workload summaries, resource constraints, and environment signature | Sanitized deployment-visible form may enter observation/memory |
| `observable_behavior` | Label-free graph/score/alert/trend/state/resource symptom and uncertainty, with evidence IDs | Yes, after canonical observation validation |
| `historical_evidence_context` | Ordered summaries of prior visible windows, prior committed/additional public results, earlier actions/tool outcomes, memory references, state transitions, and unresolved observable symptoms | Yes, bounded to current/past evidence and prompt policy |
| `temporal_context` | Current window bounds/sequence, past-only context range, recency, duration, persistence/change indicators, and state/reset continuity | Yes, when derived without future access |
| `pids_capability` | Capability type, detection unit, score semantics, required state, limitations, availability, and compatible role | Yes, from the approved capability registry |
| `deployment_visible_outcome` | Tool/run status, standardized score/alert change, stability/state transition, cache/recompute class, and sanitized outcome evidence | Yes, only fields available at the same causal point |
| `cost` | Runtime, CPU/RAM/GPU summaries, tool/LLM calls, token use, cache reuse, and resource-pressure class | Yes, sanitized and causally available |
| `failure_condition` | Typed timeout/OOM/unavailable/parser/state/reset/config/tool failure plus applicability/avoid conditions | Yes, sanitized; never raw exceptions or private paths |

Private label metrics and counterfactual quality remain behind
`private_evaluation_ref`. They can group or rank agent-training candidates but
cannot be copied into `deployment_visible_outcome`, student targets, or deployable
memory.

Historical and temporal context is strictly deployment-visible and causal. It must
not contain attack phase, campaign label/ID, attack-to-window mapping, malicious
entity history, “time since attack start,” future window summaries, or any hidden
annotation disguised as a temporal feature.

The table must cover all eight registered PIDS capabilities and multi-PIDS
counterfactual groups where admission permits. Comparisons preserve detection unit,
score semantics, configuration, checkpoint, threshold, state/reset, dataset,
window, cost, and failure provenance. A detector name alone is never a compatibility
label. An unadmitted PIDS may contribute a validated capability-awareness or real
admission-rejection row; it cannot contribute a fabricated successful-execution
outcome.

### 6.4 Counterfactual PIDS comparison trajectories

A counterfactual comparison group holds the environment/window fixed and compares
multiple registered PIDS capability choices. Actual execution outcomes are present
only for exact uses that passed admission; other candidates expose capability and
typed availability/rejection evidence only. Its purpose is to supervise *why an
Agent chooses a capability*, not to teach a detector-name ranking.

```text
CounterfactualPIDSComparisonTrajectory {
  comparison_id
  counterfactual_group_id
  shared_environment_profile_ref
  shared_window_ref
  shared_historical_evidence_context_ref
  shared_temporal_context_ref
  observable_behavior_ref

  candidate_pids_views[] {
    detector_id
    variant_id
    capability_summary
    availability_and_required_state
    comparable_public_outcome_ref
    cost_and_failure_summary
  }

  comparison_kind
  comparability_notes
  memory_interaction
  visible_evidence_grounding
  selected_action
  fallback
  private_evaluation_ref
}
```

Two causal forms are allowed:

1. **Capability-choice trajectory:** before an additional run or switch, the
   student sees the shared current context, candidate capability/availability/cost
   summaries, and deployment-visible historical experience available at that
   moment. Alternative current-window execution outcomes remain private because
   they would not yet exist at deployment time.
2. **Result-comparison trajectory:** after the Agent has requested approved
   additional detector runs, the student may see those sanitized tool results and
   compare score distribution, alert overlap/volume, stability, cost, state, and
   failure evidence. The committed result remains immutable.

The teacher may use private counterfactual evaluation on agent-training data to
select or reject candidate actions, but the student choice basis must be recreated
entirely from the visible shared context, capability summaries, historical
experience, and causally available tool results. Numeric anomaly scores with
different detection units or semantics are marked incomparable rather than
normalized into a false universal ranking.

Every comparison target states:

- the observable symptom and temporal/historical context;
- what capability each PIDS adds or lacks;
- which public outcome/cost/failure fields are comparable;
- uncertainty and missing evidence;
- the selected `RUN_ADDITIONAL_DETECTOR`, `SWITCH_DETECTOR`,
  `KEEP_CURRENT_CONFIG`, or other admitted action;
- why that action is justified over its fallback using only visible evidence.

Attack phase, campaign label/ID, TP/FP/MCC, private per-PIDS rank, and
counterfactual-best-action text are forbidden in the comparison prompt and target.

### 6.5 Required validation gates

Before export, every trajectory must pass:

- PIDS admission and real-source evidence gate;
- chronological window/result/observation/trigger/slow-path ordering;
- committed-versus-additional detector role separation;
- program-versus-LLM field provenance validation;
- strict schema and message/tool-call round trip;
- current-window immutability and next-window reconfiguration timing;
- memory namespace, retrieval, use-decision, and write constraints;
- recursive lexical and semantic privileged-information scanning;
- visible evidence closure for every diagnosis and action;
- episode-level split isolation, duplicate/near-duplicate policy, and provenance;
- canonical/prompt/export content-hash consistency;
- human review for the pre-registered risk sample.

Synthetic fixtures may test this pipeline but remain marked synthetic and cannot
be promoted to formal training evidence.

## 7. Teacher generation strategy

### 7.1 Alternatives

| Strategy | Advantages | Risks | Fit for APT-Agent |
|---|---|---|---|
| A. Human expert trajectory | Highest domain judgment; strong on ambiguous evidence and safe fallback | Expensive, slow, inconsistent formatting, limited action/capability coverage | Essential for seed cases, rubric creation, and review; insufficient alone for scale |
| B. GPT-generated teacher | Scalable, diverse language, natural tool dialogue | Hallucinated capabilities, hidden-label leakage if prompted privately, invalid tools, self-consistent but wrong rationales | Useful only behind strict visible prompts, schemas, execution, and review |
| C. Expert rules + LLM refinement | Rules enforce causality, action availability, timing, IDs, and failure policy; LLM supplies grounded diagnosis and varied valid language | Rule coverage gaps and templated bias; still needs private outcome evaluation and human audit | Best match for the current constrained controller |
| D. Self-play | Potentially explores multi-turn investigation and failures | No stable truthful opponent/reward, distribution drift, compounding hallucination, expensive counterfactual execution | Not suitable for V1; reconsider only after a validated environment and teacher baseline |

### 7.2 Recommendation

Use **C: expert rules + LLM refinement**, supplemented by targeted **A: human
expert review and seed trajectories**.

Recommended generation logic:

1. deterministic expert rules enumerate only causally valid actions and tool
   candidates from the frozen runtime state;
2. the dialogue teacher sees only deployment-visible context and generates typed
   memory use, diagnosis, evidence citations, and one valid action candidate;
3. controlled tools execute the candidate; failures remain valid examples when the
   fallback is correct;
4. the isolated evaluator compares candidate outcomes only on agent-training data;
5. selection favors contract-correct, evidence-grounded, useful behavior, not text
   that mentions or reverse-engineers evaluator metrics;
6. the LLM may refine a selected explanation using only the original visible
   evidence; private rationale is never supplied for paraphrase;
7. human experts review high-risk, conflicting, rare-action, leakage, and model-rule
   disagreement strata.

Pure GPT teaching is not recommended because fluent outputs can mask invalid
capability assumptions. Pure human teaching is not recommended as the only source
because it is unlikely to cover memory conflicts, tool failures, detector
availability, and action timing systematically. Self-play is deferred.

## 8. First SFT dataset scope

### 8.1 V1 design goal

V1 should validate the end-to-end multi-turn supervision contract across the full
PIDSMaker capability catalog, the complete Agent-controlled action space, and the
v0.4 slow-diagnosis trigger event. Coverage does not require every PIDS × action ×
environment combination to occur equally.
Common, low-cost decisions should be frequent; expensive or exceptional actions
may be deliberately sparse, but no action class or PIDS capability is deleted from
the design.

The V1 coverage matrix is:

```text
Environment profile
× observable behavior
× PIDS capability
× action intent
× deployment-visible outcome/cost/failure condition
```

Exact per-cell counts and frequencies require the pilot and remain
`UNRESOLVED_REQUIRES_EXPERIMENT`.

### 8.2 Included Agent actions

V1 covers every Agent-controlled v0.4 action intent plus the investigation action
introduced by the runtime freeze. Exported targets use the runtime-frozen names so
historical semantics do not reintroduce current-window reinference or arbitrary
configuration control:

| v0.4 action intent | Frozen trajectory representation | Frequency class | Supervision purpose |
|---|---|---|---|
| `KEEP_AND_INFER` | `KEEP_CURRENT_CONFIG` | Common | Preserve the already committed config; never rerun the current detector |
| `ADJUST_THRESHOLD` | `SELECT_VALIDATED_THRESHOLD` | Regular | Select an approved validation-derived candidate using visible score/alert evidence |
| `LOAD_TUNED_CONFIG` | `LOAD_APPROVED_CONFIG` | Regular | Load only a frozen, admitted config with valid checkpoint/threshold/parser/resource provenance |
| `SWITCH_PIDS` | `SWITCH_DETECTOR` | Lower-frequency but required | Change capability when Environment–Behavior–PIDS compatibility evidence supports it |
| `RETRAIN_CURRENT_PIDS` | `RETRAIN_DETECTOR` | Rare/high-cost but required | Request an admitted recipe on allowed train/validation inputs; create a candidate without auto-promotion |
| `ADJUST_RESOURCE_CONFIG` | `SELECT_RESOURCE_PRESET` | Failure/recovery-focused but required | Select an approved preset after visible OOM/timeout/pressure evidence; never choose raw devices/resources |
| `FALLBACK_OR_STOP` | `FINISH_DIAGNOSIS` plus typed fallback | Common in sufficient-evidence and bounded-failure cases | Stop safely without inventing more evidence or hidden success |
| Investigation extension introduced by the runtime freeze | `RUN_ADDITIONAL_DETECTOR` | Regular | Acquire an approved second capability result without replacing the committed result |

All action classes require accepted examples before the corpus is declared
full-action-space complete. “Rare” controls sampling frequency, not eligibility.
Exact action proportions are not frozen in this design.

### 8.3 Harness trigger event: `INVOKE_SLOW_DIAGNOSIS`

`INVOKE_SLOW_DIAGNOSIS` is **not an Agent action and not an assistant target**. It
is a harness-owned trigger event produced by the frozen, validation-derived,
label-blind `TriggerDecision` after committed result and canonical observation
construction.

The event appears in `WindowStep` and `ModelPromptObservation` as program context:

```text
HarnessTriggerEvent {
  triggered
  trigger_profile_id
  visible_reason_codes[]
  source_observation_id
  decided_at
}
```

If `triggered=false`, the harness records `KEEP_CURRENT_CONFIG` with
`decision_source=harness_default` and creates no assistant turn. If
`triggered=true`, the harness opens the memory/diagnosis exchange and the Agent
selects one of the frozen actions in Section 8.2. The student never predicts,
overrides, or retroactively justifies the trigger.

### 8.4 Included PIDS

PIDS coverage has three non-interchangeable levels:

| Coverage type | Definition | Admission requirement | What it proves |
|---|---|---|---|
| `capability_awareness` | The prompt presents the sanitized registered capability, required state, detection unit/score semantics, cost class, limitations, variant/causality, and current availability; the target reasons correctly about applicability | Registry/capability record must be validated; successful detector execution is not required | The Agent understands what the PIDS can and cannot offer |
| `successful_execution` | A real admitted committed or additional run produces a validated standardized result and public cost/state provenance used in the trajectory | Full Phase 1.6 admission for the exact PIDS/variant/config/dataset/role | The Agent can plan around and interpret a real successful execution |
| `failure_or_rejection` | A real typed execution failure or deterministic admission/tool rejection is presented, and the target chooses a correct fallback without fabricating output | The rejection rule or attempted use must be valid and reproducible; fabricated failures are forbidden | The Agent handles unavailability and failure safely |

The corpus coverage manifest records counts and source IDs by
`PIDS × coverage_type × role × environment`. All eight PIDS must have accepted
`capability_awareness` examples. `successful_execution` and
`failure_or_rejection` counts are reported separately and never inferred from
awareness coverage. Missing successful execution stays visible as an admission
gap, not a zero-valued success.

V1 design covers all eight PIDSMaker PIDS capability classes:

| PIDS | Capability represented in trajectories/offline table | Required coverage emphasis |
|---|---|---|
| VELOX | Lightweight pairwise event surprise | Fast-path preservation, threshold delivery, low-cost baseline, and additional-detector comparison |
| ORTHRUS | Temporal/local-graph event surprise | Explicit variant identity, temporal state/reset, default-versus-causal-variant compatibility, and switch decisions |
| MAGIC | Masked graph representation plus embedding-outlier scoring | Capability inspection, known causal limitation, unavailable/failure handling, and admitted execution only after test-information leakage is resolved |
| FLASH | Semantic/positional node-role surprise | Feature-corpus compatibility, fixed-threshold portability, node-role capability selection, and causal-fit gating |
| KAIROS | Stateful temporal event modeling | Ordering, reset/replay/warm-up, high resource/state cost, and temporal-capability orchestration |
| NODLINK | Semantic node-feature reconstruction | Reconstruction-versus-event-surprise investigation, undirected-graph semantics, and threshold behavior |
| ThreatRace | Graph-context node-role surprise | Stateless role-model comparison, fixed-threshold validation, and capability switching |
| R-CAID | Long-range causal-root-context anomaly | Pseudo-graph timing/expansion cost, transductive-feature gating, and root-context capability selection without claiming root-cause output |

The offline run table must include Environment–Behavior–PIDS compatibility records
for all eight systems, including cost, outcome, and failure-condition evidence. It
must also form multi-PIDS counterfactual groups where the same causally available
window/environment is evaluated under multiple admitted capability choices.

Coverage does not authorize unsupported execution. Every PIDS/variant/config/
dataset/role independently passes the causal config, checkpoint, threshold,
parser, resource profile, state/reset, real-smoke, and provenance admission gate.
Compatibility-baseline records remain explicitly separated from causal-main
student trajectories.

**Trajectory generation waits for admission validation.** Unavailable systems may
appear in capability-inspection, rejection, fallback, and failure-handling
trajectories, but successful execution/tool-result demonstrations are generated
only after the relevant use is admitted.

### 8.5 Included tasks

V1 trajectory tasks are:

1. retrieve or intentionally decline memory for triggered observable graph, score,
   trend, state, and resource symptoms;
2. reason about memory applicability using environment, historical/temporal
   context, observable behavior, PIDS capability, cost regime, failure conditions,
   recency, and evidence provenance;
3. resolve relevant, conflicting, inapplicable, stale, and empty retrieval results
   with an explicit `use`, `downweight`, or `ignore` decision per record;
4. create experience-distillation write candidates from deployment-visible
   action/tool outcomes while leaving sanitization, deduplication, scope, and actual
   writes to the harness;
5. ground every diagnosis in observable symptom, graph/score/trend/resource
   evidence, uncertainty, and an explicit action justification;
6. inspect and compare the actual capability, limitations, state requirements,
   availability, and cost of all eight PIDSs;
7. construct counterfactual PIDS comparison trajectories over the same
   environment/window without exposing not-yet-available alternative outcomes;
8. preserve the current config when visible evidence does not justify change;
9. select an approved validation-derived threshold candidate or preserve the
   current threshold;
10. load an approved config without exposing raw parameters or changing the current
   committed result;
11. request and interpret an approved additional detector investigation across
   different PIDS capability classes;
12. switch detector when environment/behavior/capability mismatch is supported by
   visible evidence and next-window semantics are satisfied;
13. request bounded retraining using an approved recipe, handle asynchronous or
    failed results, and avoid automatic candidate promotion;
14. select a validated resource preset after visible OOM/timeout/resource-pressure
    evidence without choosing CUDA/device or raw values;
15. compare committed/additional or offline public outcomes only through visible
    score/alert/cost/stability/failure evidence;
16. stop with `FINISH_DIAGNOSIS` when evidence is sufficient or a tool is
    unavailable/failed;
17. propose safe Working/Episode memory writes without claiming hidden correctness
    or unobserved tool success;
18. reject unavailable IDs, executor-owned parameters, current-window rewrites,
    unsupported paper-level outputs, and hidden-label justifications.

### 8.6 V1 turn scope

V1 follows the runtime-frozen two-assistant memory protocol:

| Trajectory form | Message sequence | Assistant/tool turns |
|---|---|---|
| Terminal no-tool action | `system → user prompt → assistant memory request → memory tool → assistant decision` | 2 assistant + 1 tool; 5 messages total |
| Terminal tool action | Base sequence plus the selected threshold/config/switch/retrain/resource action tool result | 2 assistant + 2 tool; 6 messages total when no result-dependent replanning is required |
| Additional-detector or tool-result replanning | Base sequence, action tool result, supplemental user prompt, then a new memory/decision cycle ending in a terminal action or another admitted request | 4 assistant + 3 tool for one supplemental no-tool terminal cycle; longer bounded traces retain the same repeated structure |

V1 includes both base and supplemental cycles across the action/PIDS coverage
matrix. The production and export maximum number of supplemental cycles remains
`UNRESOLVED_REQUIRES_EXPERIMENT`; the corpus must record the actual harness budget
rather than present one turn count as universally optimal.

Untriggered windows contribute episode chronology and state but no assistant
training target. V1 does not add a post-tool assistant message when the frozen
runtime would deterministically close after a terminal tool result.

### 8.7 V1 balance and quantity

The corpus must cover every PIDS capability and action class across successful,
unavailable, rejected, empty-memory, conflicting-memory, and bounded-failure cases
without making detector identity or failure text a shortcut to one action. It must
also control near duplicates from adjacent windows and repeated runs.

Sampling is frequency-stratified rather than exclusionary: routine keep/finish and
threshold decisions can be common; config load, additional investigation, and
switch decisions can be regular; retraining and resource recovery can be sparse
but must remain represented with both valid and fail-closed outcomes.

Exact trajectory counts, action proportions, environment proportions, prompt
lengths, memory top-k, trigger constants, and train/validation ratio are
`UNRESOLVED_REQUIRES_EXPERIMENT`. They must be set by a pre-registered pilot and
episode-level validation analysis, not asserted in this design.

## 9. Acceptance criteria for the dataset design

Before any corpus is called formal:

- every source PIDS/use passes the Phase 1.6 admission gate;
- the coverage manifest gives all eight PIDS accepted capability-awareness
  examples and reports successful-execution and failure/rejection coverage as
  separate, evidence-backed categories;
- the coverage manifest accounts for every Agent-controlled v0.4 action intent,
  while `INVOKE_SLOW_DIAGNOSIS` appears only as a harness trigger event;
- the offline run table contains versioned Environment–Behavior–PIDS compatibility,
  historical/temporal context, deployment-visible outcome, cost, and failure-
  condition fields with private evaluation kept behind references;
- canonical trajectory and export schemas are versioned and round-trip validated;
- program- and LLM-authored fields are mechanically distinguishable;
- episode-level partitions prevent environment/window/memory leakage;
- dialogue teachers receive only deployment-visible inputs;
- privileged selection/evaluation stays physically and schematically separate;
- every assistant claim closes over visible prompt/tool evidence;
- every target records observable symptom, graph/score/trend/resource evidence,
  uncertainty, and action justification, with no TP/FP/MCC or other hidden-label
  value used as a student target;
- `VisibleEvidenceGrounding` validates as a compact structured evidence summary
  and contains no teacher/model CoT or private scratch reasoning;
- memory trajectories cover applicability reasoning, conflict resolution, and
  experience distillation while preserving harness-owned retrieval/storage/write
  execution;
- counterfactual PIDS comparisons hold environment/window context fixed, preserve
  score-semantic comparability, and expose only causally available public evidence;
- historical/temporal features contain no attack phase, campaign label/mapping,
  future window, or hidden malicious-entity history;
- committed inference never appears as an assistant tool call;
- no persistent action affects the current window;
- OpenAI-compatible messages match the deployed prompt/tool turn protocol;
- assistant-only loss masking is verified after tokenizer rendering;
- synthetic fixtures remain non-formal;
- manifest, hashes, code/model/tool/prompt/sanitizer versions, rejections, and human
  review evidence are complete.

## 10. Phase 2 conclusion

APT-Agent should train on bounded multi-turn trajectories, grouped and split by
episode, then exported as OpenAI-compatible chat/tool JSONL from a richer canonical
JSONL source. The corpus teaches visible-evidence diagnosis, memory use,
investigation planning, and high-level orchestration—not intrusion classification
or detector internals.

The recommended teacher is a constrained expert-rule pipeline with a
deployment-view LLM and targeted human review, while a separate privileged
evaluator selects and audits agent-training trajectories. V1 covers all eight PIDS
capability classes and the complete Agent-controlled v0.4 action space using
frequency-stratified sampling; slow-diagnosis invocation remains a harness trigger
event. Trajectory generation for each successful PIDS use waits for that exact
variant/config/dataset/role to pass admission validation.
