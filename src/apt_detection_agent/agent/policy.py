"""LLM policy that proposes typed actions without executing them."""

from __future__ import annotations

import json
from typing import Protocol, Sequence
from uuid import uuid4

from apt_detection_agent.schemas import Action, Observation

from .prompt_loader import PromptLoader


class CompletionClient(Protocol):
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class PolicyError(ValueError):
    pass


class AgentPolicy:
    def __init__(self, client: CompletionClient, prompts: PromptLoader) -> None:
        self.client = client
        self.prompts = prompts

    def propose(self, observation: Observation, available_tools: Sequence[str]) -> Action:
        system = self.prompts.load("agent/system.txt")
        user = json.dumps({
            "observation": observation.to_dict(),
            "available_tools": list(available_tools),
        }, sort_keys=True)
        raw = self.client.complete(system, user)
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise TypeError("action payload must be an object")
            payload.setdefault("schema_version", "1.0")
            payload.setdefault("action_id", str(uuid4()))
            return Action.from_dict(payload)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PolicyError("LLM response is not a valid Agent action") from exc
