# Data Protocol

Mapped requirements: REQ-CAUSAL-001..004, REQ-LABEL-001..004,
REQ-WINDOW-001..004, REQ-MEMORY-001..004, REQ-EVAL-004.

## Dataset inventory before selection

No train/validation/held-out dataset list is fixed until inventory and checkpoint
smoke tests are complete. Each inventory record contains dataset, OS, CDM/schema,
date range, available PIDS, checkpoint status, ground-truth format, campaign mapping,
exclusions, PostgreSQL dependency, estimated storage, and estimated runtime.

## Time and fitted state

- Formal windows are fixed aligned `[start,end)` buckets with explicit origin,
  timezone, and size.
- Events and windows are processed chronologically. A current computation cannot
  read a later event, window, prediction, evaluator result, or memory record.
- Vocabulary, normalizer, IDF, fitted feature statistics, embeddings, models, and
  thresholds are fitted only on declared training/validation inputs and frozen
  before held-out use.
- Parameter-free features may be computed on a current graph only after that window
  is available.
- Existing approximate/transductive PIDSMaker behavior is retained only as a
  labeled compatibility baseline.

## Labels and campaign truth

Raw provenance and deployment-visible detector outputs are physically separate from
labels, campaign mappings, evaluator annotations, and teacher rationale. Agent
processes receive only the former. Campaigns are defined by versioned manifests with
included windows, malicious entities, sources, corrections, and exclusions; a
ground-truth filename is not a campaign identifier.

## Splits and memory

Working memory, episode memory, and case state reset between splits, scenarios, and
held-out episodes. A sanitized, signed, frozen static LTM may cross into validation
or held-out as a training artifact. Validation/held-out episode state cannot update
that snapshot.

Primary experimental tiers are strict within-dataset temporal splits followed by
leave-one-dataset or leave-one-OS/schema-out evaluation selected after inventory.

## Implemented Phase 3 enforcement

- `src/apt_detection_agent/data/stream.py` accepts only deployment-visible events,
  enforces chronological current-window batches, prohibits skipped/replayed
  windows, and requires an append-only formal prediction before advancing.
- The same stream binds each formal prediction to the committed fast-path config;
  a current-window slow-path result cannot retroactively replace that config.
- `src/apt_detection_agent/data/causal.py` records fitted-state source split,
  fit cutoff, freeze time, hash, code commit, and transductive status. Vocabulary,
  normalization, IDF, statistics, featurizers, embeddings, and models are
  agent-training products; validation may additionally produce thresholds.
- Current-graph parameter-free computation is admitted only after the window end
  and receives only event IDs whose timestamps are within that exact half-open
  window.
- Rolling-range sizes are versioned validation candidates rather than controller
  constants. Validation experiments still determine which candidate is approved.
