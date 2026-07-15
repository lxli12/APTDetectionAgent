import json
import pytest

from apt_detection_agent.agent.policy import AgentPolicy
from apt_detection_agent.agent.prompt_loader import PromptLoader
from apt_detection_agent.schemas import ActionType
from tests.test_contracts import action, observation


class FakeClient:
    def complete(self, system_prompt: str, user_prompt: str) -> str:
        assert "shell commands" in system_prompt
        assert "available_tools" in user_prompt
        return action().to_json()


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
    proposed = policy.propose(observation(), ("run_current_pids",))
    assert proposed.action_type is ActionType.KEEP_AND_INFER
    assert proposed.tool_name == "run_current_pids"
