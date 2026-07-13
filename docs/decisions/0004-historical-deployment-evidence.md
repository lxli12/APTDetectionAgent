# ADR 0004: Historical deployment scripts are evidence only

Status: accepted
Requirements: REQ-GOV-003, REQ-DB-003, REQ-WANDB-001, REQ-ENV-003.

The external historical `setup_server.sh` and `run_agent_server.sh` files are not
project entrypoints and must never be executed. Their paths, package versions,
ports, database names, GPU assignments, model arguments, and memory directories are
candidate inventory checks rather than current truth.

Installation commands, automatic service startup, database drop/create/restore or
data-directory migration, credential values, ChromaDB semantics, and historical
`learning/evaluation/max_runs/no_rules` behavior are rejected from the new runtime.

The scripts provide historical evidence for an initial GPU 0/vLLM and GPU 1/PIDS
profile and port 8000, but the scheduler owns devices and vLLM connection values are
environment-driven. SQLite FTS5 replaces the historical ChromaDB memory design.
