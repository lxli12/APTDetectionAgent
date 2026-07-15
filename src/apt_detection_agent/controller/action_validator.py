"""Validate proposed actions against the current tool capability set."""

from apt_detection_agent.schemas import Action, ActionType


class ActionValidator:
    def validate(self, action: Action, available_tools: tuple[str, ...]) -> None:
        if action.action_type is ActionType.CALL_TOOL:
            if action.tool_name not in available_tools:
                raise ValueError("action requests an unavailable tool")
        elif action.arguments:
            raise ValueError("only tool actions may carry arguments")
