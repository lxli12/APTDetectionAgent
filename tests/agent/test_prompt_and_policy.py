import json
from datetime import datetime, timezone

import pytest

from apt_detection_agent.agent.policy import AgentPolicy
from apt_detection_agent.agent.prompt_loader import PromptLoader
from apt_detection_agent.schemas import ActionType, Observation


class FakeClient:
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        assert "shell commands" in system_prompt
        assert "available_tools" in user_prompt
        return json.dumps({
            "action_type": "call_tool",
            "rationale": "inspect the visible anomaly",
            "tool_name": "run_pids",
            "arguments": {"detector": "VELOX"},
            "memory_content": None,
        })


def test_prompt_loader_rejects_non_text_and_traversal(tmp_path):
    loader = PromptLoader(tmp_path)
    with pytest.raises(ValueError):
        loader.load("prompt.md")
    with pytest.raises(ValueError):
        loader.load("../prompt.txt")


def test_policy_returns_typed_action(tmp_path):
    prompt = tmp_path / "agent" / "system.txt"
    prompt.parent.mkdir()
    prompt.write_text("Never emit shell commands.")
    policy = AgentPolicy(FakeClient(), PromptLoader(tmp_path))
    observation = Observation("o1", "w1", datetime.now(timezone.utc))
    action = policy.propose(observation, ("run_pids",))
    assert action.action_type is ActionType.CALL_TOOL
    assert action.tool_name == "run_pids"
