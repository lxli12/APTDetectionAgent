# APTDetectionAgent Project Architecture Design v1.1

Status: **frozen**
Scope: repository structure, module responsibility, dependency boundary, and data ownership

## 1. Overview

APTDetectionAgent is an LLM-based autonomous APT detection framework built on top
of existing provenance-based intrusion detection systems (PIDS). It observes
evolving provenance evidence, selects and orchestrates detection capabilities,
maintains long-horizon context, reasons over multi-stage evidence, and produces
analyst-facing decisions.

The project does not replace a PIDS model. PIDSMaker is an independent detection
backend; APTDetectionAgent is the Agent orchestration layer above it.

```text
Agent policy <-> Controller <-> Memory
                       |
                       v
                 Tool layer
                       |
                       v
              PIDSMaker adapter
                       |
                       v
                  PIDSMaker
             (independent backend)
```

## 2. Frozen design principles

1. `PIDSMaker/` is a pinned git submodule. Its source and internal layout are not
   refactored or copied into this project.
2. APTDetectionAgent is an orchestration layer, not another PIDS implementation.
3. No separate "Agent artifact layer" is created.
4. PIDSMaker owns its preprocessing, features, intermediate artifacts, detector
   outputs, model checkpoints, training, inference, and backend evaluation.
5. Agent code can use PIDSMaker only through `pidsmaker_adapter/` and typed tools.
6. SFT adapts the Agent. It never modifies or trains PIDSMaker.
7. `experiment/` owns the complete Agent experiment lifecycle; domain modules do
   not invent their own run directories.
8. Prompt templates are dynamically loaded plain `.txt` files. Prompts are not
   embedded in Python source or stored as Markdown/YAML.

## 3. Repository structure

```text
APTDetectionAgent/
├── PIDSMaker/                         # unchanged pinned submodule
├── src/apt_detection_agent/
│   ├── agent/                         # decision policy and LLM boundary
│   ├── controller/                    # Observe/Think/Act/Reflect loop
│   ├── memory/                        # fixed Agent memory subsystem
│   ├── tools/                         # typed tool registry and execution
│   ├── pidsmaker_adapter/             # only PIDSMaker integration boundary
│   ├── schemas/                       # cross-module public contracts
│   ├── sft/                           # reserved; Agent adaptation, not yet built
│   ├── evaluation/                    # Agent evaluation
│   └── experiment/                    # Agent experiment lifecycle
├── data/                              # Agent-owned datasets only
├── checkpoints/                       # Agent checkpoints only
├── experiments/                       # Agent run definitions and outputs
├── configs/                           # stable YAML configuration
├── prompts/                           # plain-text prompt templates
├── scripts/                           # thin reproducible entry points
├── tests/                             # tests arranged by architecture domain
└── docs/
    ├── architecture/
    ├── design/
    └── archive/
```

Empty or generated directories are represented by a README rather than committed
generated data. The repository contains no copied PIDSMaker artifacts or
checkpoints.

## 4. PIDSMaker boundary

`PIDSMaker/` remains responsible for raw provenance preprocessing, graph and
feature construction, PIDS model implementation, training, detection, evaluation,
backend artifacts, and PIDS checkpoints. Its exact internal tree is defined by
the pinned upstream revision and is deliberately not repeated here as an Agent
architecture contract.

APTDetectionAgent must not import PIDSMaker modules into the controller process.
The adapter validates an admitted capability, builds a bounded backend request,
invokes the backend process, and normalizes its output. This preserves environment
and ownership boundaries.

## 5. Agent source modules

### 5.1 `agent/`

```text
agent/
├── policy.py
├── llm_client.py
└── prompt_loader.py
```

`policy.py` maps an Observation, memory context, and available tools to a proposed
typed Action. It does not execute tools. `llm_client.py` owns LLM transport and
generation settings. `prompt_loader.py` safely loads only `.txt` templates under
`prompts/`.

### 5.2 `controller/`

```text
controller/
├── agent_loop.py
├── observation_builder.py
├── action_validator.py
├── execution_trace_recorder.py
└── scheduler.py
```

The controller implements Observe -> Think -> Act -> Reflect. It builds visible
observations, invokes the policy, validates actions, dispatches tools, updates
memory, and records the trace. The scheduler decides when a detection window is
ready; it does not contain Agent policy.

### 5.3 `memory/`

```text
memory/
├── memory_manager.py
├── memory_store.py
└── memory_retriever.py
```

Memory stores historical Agent-visible context, retrieves relevant evidence, and
controls lifecycle/reset. During the initial SFT stage its mechanism is fixed;
SFT may learn how to use memory, not replace its implementation.

### 5.4 `tools/`

```text
tools/
├── tool_interface.py
├── tool_registry.py
└── tool_executor.py
```

Tools expose typed names and argument contracts. The registry describes available
capabilities, the executor validates and dispatches calls, and results are returned
as typed envelopes. The LLM cannot construct shell commands or arbitrary paths.

### 5.5 `pidsmaker_adapter/`

```text
pidsmaker_adapter/
├── adapter.py
├── registry.py
├── admission.py
└── result_parser.py
```

The registry describes VELOX, ORTHRUS, MAGIC, FLASH, KAIROS, NODLINK,
ThreatRace, and RCAID. Registry membership is descriptive; admission explicitly
controls executable configurations. The adapter invokes an admitted backend and
the parser converts backend output to the common `PIDSResult` contract.

### 5.6 `schemas/`

```text
schemas/
├── observation_schema.py
├── action_schema.py
├── tool_schema.py
├── memory_schema.py
├── pids_schema.py
└── execution_schema.py
```

Schemas are serializable contracts crossing module boundaries: Observation,
Action, tool request/result, memory exchange, PIDS result, and execution trace.
SFT dataset schemas and evaluation metric internals do not belong here.

### 5.7 `sft/` (reserved)

The namespace is reserved for future Agent SFT construction:
`sft_schema.py`, `manifest_loader.py`, `execution_trace_loader.py`,
`training_example_builder.py`, `training_example_validator.py`,
`data_sanitizer.py`, and `dataset_exporter.py`. These files are intentionally not
implemented in v1.1. Future SFT consumes Agent execution traces, removes
deployment-invisible information, and exports training rows; it must not reach
into PIDSMaker internals.

### 5.8 `evaluation/`

```text
evaluation/
├── evaluator.py
├── detection_metrics.py
├── cost_metrics.py
└── report_generator.py
```

Evaluation computes Agent-level TP, FP, precision, coverage, runtime, and token
cost and produces reports. Evaluation truth does not enter online observations.

### 5.9 `experiment/`

```text
experiment/
├── experiment_runner.py
├── result_tracker.py
└── artifact_manager.py
```

The experiment package is the composition root. It creates a unique Agent run,
snapshots resolved configuration, launches the controller lifecycle, tracks
results, and manages run outputs. It does not manage PIDSMaker artifacts.

## 6. Data, checkpoints, and experiments

`data/` stores only Agent datasets:

```text
data/
├── agent_training/
├── sft/{manifests,examples,validated,exports}/
└── evaluation/
```

`checkpoints/agent/sft/` is reserved for Agent checkpoints. PIDSMaker checkpoints
remain owned by PIDSMaker.

Agent run outputs live under `experiments/runs/<run_id>/`:

```text
config.yaml
command.sh
logs/
execution_traces/
metrics/
reports/
```

Generated data and outputs are ignored by Git. Only documentation and approved
experiment definitions are versioned.

## 7. Configuration, prompts, scripts, and tests

Stable settings use YAML under `configs/{model,dataset,pidsmaker_adapter,sft,evaluation,experiment}/`.
CLI values may override experiment-specific settings, but resolved configuration
must be snapshotted in the run directory.

Prompts use `.txt` files under `prompts/{agent,sft,evaluation}/` and are loaded at
runtime. Scripts are thin entry points: `build_sft_dataset.sh`,
`train_agent_sft.sh`, `run_agent.sh`, and `evaluate_agent.sh`.

Tests mirror the source domains under
`tests/{agent,controller,memory,tools,pidsmaker_adapter,sft,evaluation}/`. Tests
must exercise public interfaces and boundary failures; legacy implementation-era
tests are not retained.

## 8. Dependency rules

```text
schemas <- agent
schemas <- memory
schemas <- pidsmaker_adapter <- tools
agent + memory + tools + schemas <- controller
controller + evaluation <- experiment
execution traces -> future sft -> Agent checkpoint
```

- `schemas` depends only on the Python standard library.
- `agent` cannot import controller, tools implementations, or PIDSMaker.
- `controller` depends on interfaces, not PIDSMaker internals.
- `pidsmaker_adapter` is the only module aware of backend invocation.
- `evaluation` consumes recorded results and ground truth offline.
- `experiment` composes modules but owns no domain algorithm.
- SFT remains offline and Agent-only.

## 9. Overall data flow

```text
PIDSMaker raw data -> PIDSMaker preprocessing -> PIDS models
                                              -> PIDSMaker artifacts/checkpoints
                                                           |
                                                           v
Agent observation -> Controller -> typed Tool -> PIDSMaker adapter
       ^                 |                                |
       |                 v                                v
     Memory       execution trace <- normalized PIDS result
                         |
                         +-> evaluation
                         +-> future SFT -> Agent checkpoint
```

## 10. Acceptance criteria

The architecture is satisfied when: PIDSMaker remains an unchanged submodule; no
PIDSMaker source/artifact/checkpoint is duplicated; Agent modules match the owners
above; all prompts are `.txt`; generated outputs are ignored; SFT contains no
implementation yet; tests mirror the target modules; and controller-level tests
pass without importing PIDSMaker.
