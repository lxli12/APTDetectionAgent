# Controller protocol

Requirements: REQ-TOOL-001..005, REQ-CONFIG-001..003,
REQ-RESOURCE-001..003, REQ-REPRO-001..003, REQ-LABEL-004.

`src/apt_detection_agent/controller/core.py` implements one frozen-policy
Observe–Think–Act–Reflect step. The committed fast path always produces the formal
current-window prediction before any slow-path action. A persistent configuration
can only be scheduled for `current_sequence + 1`; it cannot rewrite that prediction.

Slow-path triggers use only alert volume, observable failure strings, and a frozen
periodic health-check candidate. The trigger profile must be validation-derived.
Policy actions remain strict `AgentAction` values, and tool execution accepts only a
typed `ToolRequest`. Tool failure retries are bounded to at most three attempts and
end in an explicit fallback reflection.

`src/apt_detection_agent/controller/scheduler.py` reads the project resource profile,
not host-visible capacity. The initial executor assignment is GPU 0 for vLLM and GPU
1 for one unknown PIDSMaker GPU workload. CPU and memory use are admitted against
32 vCPU and 240 GiB minus the explicit reserve. The Agent never selects CUDA IDs.

`src/apt_detection_agent/controller/trajectory.py` writes immutable, contiguous
JSONL records containing the full public observation, formal prediction, action,
tool results, reflection, and timing. Runtime run-directory completeness and tmux
ownership remain part of the later entrypoint/remote-run phase.
