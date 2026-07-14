# Frozen runtime contract acceptance — 2026-07-14

Requirements: REQ-RUNTIME-001..006, REQ-PIDS-006, REQ-TOOL-001..005,
REQ-CONFIG-001..003, REQ-LABEL-001..004, REQ-SFT-001..004.

## Accepted implementation scope

The post-design-review runtime now has a separate implementation path under
`src/apt_detection_agent/controller/frozen_runtime.py`; the legacy
`controller/core.py` remains only for compatibility. The new path enforces this
order: committed fast-path execution, exactly-once committed ledger append,
deterministic canonical observation, validation-frozen trigger, optional prompt,
frozen two-turn memory exchange, one exact frozen action, optional high-level tool,
and future-window pending activation.

Implemented contract evidence:

- `schemas/agent_runtime.py`: committed/additional result separation, three
  observation layers, eight frozen actions, decision source, typed tool outcome,
  pending state, and transaction record;
- `controller/observation_builders.py`: deterministic canonical, trigger, and
  prompt builders with content hashes; prompt overflow fails closed while
  truncation policy remains `UNRESOLVED_REQUIRES_EXPERIMENT`;
- `schemas/memory_runtime.py` and `controller/memory_protocol.py`: the required two
  assistant turns plus deterministic retrieval tool turn, including the
  `needed=false` empty result;
- `schemas/admission.py`: causal config, checkpoint, threshold, parser, resource,
  state/reset, real smoke, and provenance gates;
- `tooling/runtime_tools.py`: unified capability/state inspection, additional
  detector, comparison, threshold, config, switch, retrain, and resource-preset
  interfaces using opaque IDs; unavailable choices return sanitized blocked
  outcomes at the dispatch boundary;
- `sft/frozen_*`: v2 student/teacher, group partition, admission, sanitizer, hash,
  and trainer dry-run contracts tied to the same canonical/prompt/memory/action
  schemas.

## AutoDL evidence

At commit `5b5bfa583ef0e6d0f1a32e9560137f39c1561360` in the existing `pids`
environment:

- full suite: 268/268 passed in 11.309 seconds;
- PIDSMaker remained pinned at
  `32602734bc9f896be5fc0f03f0a185c967cd6624` and clean;
- synthetic frozen-runtime smoke:
  `/root/autodl-tmp/apt-agent/frozen-runtime-runs/frozen-runtime-synthetic-20260714-001`.

The smoke has two committed results for two windows. Window 0 has no prompt,
policy, memory, or assistant turn. Window 1 has one deterministic prompt and one
persisted frozen memory exchange. It explicitly records
`formal_performance_claim=false` and
`pids_admitted_for_formal_trajectory=false`.

## Non-claims and remaining gates

This is contract and synthetic protocol acceptance, not real PIDS admission or
formal trajectory evidence. The dynamic discovery bridge retains every source
config from the pinned PIDSMaker commit but marks all generated runtime candidates
unavailable or unverified. No real PIDS/config/dataset/use currently has an
all-eight-gates `PIDSAdmissionRecord`.

Formal trajectory collection therefore remains blocked until at least one scoped
combination has reviewed real evidence for every gate. Prompt truncation, trigger
constants, memory retrieval limits, additional-cycle limits, resource presets,
state warm-up, retries, and real-smoke bounds remain validation decisions rather
than claimed optimal defaults. The user-provided formal SFT dataset must then pass
the frozen v2 validator; no weight update or deployment promotion is claimed here.
