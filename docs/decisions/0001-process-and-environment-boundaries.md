# ADR 0001: Process and environment boundaries

Status: accepted
Requirements: REQ-ENV-001..004, REQ-DB-001..003, REQ-LABEL-001.

The controller, PIDSMaker subprocess, vLLM server, PostgreSQL, hidden evaluator, and
case/memory store are separate runtime components. PIDSMaker executes through a
validated subprocess adapter in `pids`; vLLM is accessed through a localhost HTTP
endpoint in `vllm`. Neither environment imports the other.

The hidden evaluator has separate filesystem permissions and a private read-only
database role. `pids_worker` accesses provenance data; `agent_controller` has no
private-label access; administrative/migration access is manual only. SQLite FTS5 is
the initial case/memory backend.

The controller dependency set may include pinned Pydantic, PyYAML, and an HTTP
client after the Phase 1 audit, but excludes PyTorch, PyG, PIDSMaker, and vLLM.
