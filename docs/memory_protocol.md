# Memory protocol

Requirements: REQ-MEMORY-001..007, REQ-LABEL-002, REQ-REPRO-001.

The first implementation is the fixed harness in
`src/apt_detection_agent/memory/store.py`: SQLite persistence, SQLite FTS5 lexical
retrieval, normalized-content SHA-256 exact deduplication, and the structured key
`environment + observable_behavior + pids + action`. Dense embeddings are disabled.

Runtime records use the exact namespace
`split + scenario_id + episode_id`. Writes that disagree with any namespace field
fail closed. Episode reset removes Working/Episode records and Case State only from
that namespace; it never removes a released static LTM snapshot. No capacity
eviction occurs inside an episode.

Conflicting records coexist. Each retains its environment, applicability
conditions, timestamp, evidence artifact IDs, and explicit `conflicts_with` links.
The harness does not silently merge or choose a winner.

Static LTM is loaded only through `StaticLTMSnapshot`, whose schema requires an
agent-training origin, deterministic sanitizer version, provenance hash, hidden
evaluator signature, freeze time, and recorded human sample review. Runtime writes
cannot target the static layer. The deterministic sanitizer rejects privileged
field names, common teacher/answer phrases, and mismatched normalized hashes.

The 2048-token budget and 20-candidate cap are explicitly marked
`unvalidated_engineering_default`. They are not a method optimum and remain subject
to the validation sensitivity experiment required by REQ-MEMORY-007.

The Agent-facing boundary is `MemoryCaseToolService` in
`src/apt_detection_agent/tooling/memory_tools.py`. The LLM supplies only observable
query/write content or a next-window configuration identifier. The executor, not
the LLM, supplies the database-backed store, exact namespace, environment profile,
timestamp, record identifier, normalized hash, report path, and append-only audit
path. `write_memory` is restricted to Working or Episode layers; released static
LTM remains an offline, reviewed training artifact and has no runtime write tool.
