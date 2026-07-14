#!/usr/bin/env bash
# Formal chronological evaluation entrypoint. Requirements: REQ-CAUSAL-001..004,
# REQ-LABEL-001..004, REQ-EVAL-001..006, REQ-REPRO-001..003.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ROOT="${APT_AGENT_RUN_ROOT:-/root/autodl-tmp/apt-agent/experiments/runs}"
PRIVATE_BASE="${APT_EVALUATOR_PRIVATE_ROOT:-/root/autodl-tmp/apt-agent/evaluator-private}"
RUN_ID=""
MODE="synthetic"
PYTHON_BIN="${APT_AGENT_PYTHON:-python}"

STAGES=(validate_frozen_bundle validate_hidden_evaluator_isolation load_chronological_scenario reset_episode_state run_window_stream update_case_and_memory compute_campaign_metrics compute_node_edge_evidence_metrics generate_report write_reproducibility_manifest)
while [[ $# -gt 0 ]]; do
  case "$1" in
    --run-id) RUN_ID="$2"; shift 2 ;;
    --run-root) RUN_ROOT="$2"; shift 2 ;;
    --private-root) PRIVATE_BASE="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    *) echo "usage: $0 --run-id ID [--mode synthetic|real] [--run-root PATH] [--private-root PATH]" >&2; exit 2 ;;
  esac
done
[[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || exit 2
mkdir -p "$RUN_ROOT" "$PRIVATE_BASE"
RUN_DIR="$RUN_ROOT/$RUN_ID"
PRIVATE_ROOT="$PRIVATE_BASE/$RUN_ID"
[[ ! -e "$RUN_DIR" && ! -e "$PRIVATE_ROOT" ]] || { echo "run already exists" >&2; exit 2; }

if [[ "$MODE" == "real" ]]; then
  mkdir "$RUN_DIR"
  printf '{"stage":"validate_frozen_bundle","status":"blocked","reason":"BLOCKED_BY_PHASE8_REAL_PIDS_GATES"}\n' >"$RUN_DIR/stages.jsonl"
  "$PYTHON_BIN" "$ROOT/scripts/finalize_stage_run.py" --run-dir "$RUN_DIR" --status blocked --reason BLOCKED_BY_PHASE8_REAL_PIDS_GATES --evidence-class real_data_preflight
  exit 3
fi
[[ "$MODE" == "synthetic" ]] || exit 2
mkdir "$PRIVATE_ROOT"

PYTHONPATH="$ROOT/src" "$PYTHON_BIN" "$ROOT/scripts/run_synthetic_agent_scenario.py" --run-id "$RUN_ID" --run-root "$RUN_ROOT" --project-root "$ROOT"
(cd "$ROOT" && PYTHONPATH="$ROOT/src:$ROOT" "$PYTHON_BIN" -m unittest tests.test_hidden_evaluator.FeedbackIsolationTests.test_separate_process_emits_only_sanitized_feedback >/dev/null)
HIDDEN_EVALUATOR_PRIVATE_ROOT="$PRIVATE_ROOT" PYTHONPATH="$ROOT/src" "$PYTHON_BIN" "$ROOT/scripts/build_synthetic_hidden_fixture.py" --private-output "$PRIVATE_ROOT/request.json"
HIDDEN_EVALUATOR_PRIVATE_ROOT="$PRIVATE_ROOT" AGENT_FEEDBACK_ROOT="$RUN_DIR" PYTHONPATH="$ROOT/src" "$PYTHON_BIN" "$ROOT/scripts/run_hidden_evaluator.py" --private-input "$PRIVATE_ROOT/request.json" --private-output "$PRIVATE_ROOT/metrics.json" --public-feedback "$RUN_DIR/evaluation_feedback.json"

for item in "${STAGES[@]}"; do
  printf '{"stage":"%s","status":"succeeded","evidence_class":"synthetic_integration_only"}\n' "$item" >>"$RUN_DIR/stages.jsonl"
done
PYTHONPATH="$ROOT/src" "$PYTHON_BIN" "$ROOT/scripts/finalize_public_report.py" --run-dir "$RUN_DIR" --feedback "$RUN_DIR/evaluation_feedback.json" --project-root "$ROOT"
"$PYTHON_BIN" -c 'import json,pathlib,sys; r=pathlib.Path(sys.argv[1]); s=json.loads((r/"run_status.json").read_text()); assert s["status"]=="succeeded" and not s["formal_performance_claim"]' "$RUN_DIR"
echo "$RUN_DIR"
