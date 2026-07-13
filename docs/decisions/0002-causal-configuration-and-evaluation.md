# ADR 0002: Causal configuration and evaluation

Status: accepted
Requirements: REQ-CAUSAL-001..004, REQ-CONFIG-001..003,
REQ-WINDOW-001..004, REQ-EVAL-001..006.

The main experiment uses aligned fixed `[start,end)` windows and frozen fitted state.
Each window first commits the configured fast-path result. It may trigger slow-path
investigation, but persistent reconfiguration applies from the next window and may
not rewrite the committed result.

Held-out runs select only frozen PIDS, ApprovedConfig entries, and thresholds.
Transductive PIDSMaker configurations remain explicit compatibility baselines and
are excluded from causal main results.

Campaign manifests, not individual label filenames, define attack evaluation.
Campaign/unique-node metrics and occurrence/edge/evidence/system metrics use
separate, versioned denominators.
