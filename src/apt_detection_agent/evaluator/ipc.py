"""Filesystem IPC and database-role policy for the isolated evaluator process.

Requirements: REQ-LABEL-001..004, REQ-EVAL-006, REQ-DB-001..003.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import model_validator

from apt_detection_agent.schemas.common import Identifier, StrictModel


class DatabaseRolePolicy(StrictModel):
    admin_role: Identifier
    pids_worker_role: Identifier
    hidden_evaluator_role: Identifier
    agent_controller_role: Identifier
    hidden_evaluator_read_only: bool = True
    agent_private_schema_access: bool = False

    @model_validator(mode="after")
    def roles_are_separated(self) -> "DatabaseRolePolicy":
        roles = {
            self.admin_role,
            self.pids_worker_role,
            self.hidden_evaluator_role,
            self.agent_controller_role,
        }
        if len(roles) != 4:
            raise ValueError("admin, PIDS, evaluator, and controller roles must be distinct")
        if not self.hidden_evaluator_read_only:
            raise ValueError("hidden evaluator private-label access must be read-only")
        if self.agent_private_schema_access:
            raise ValueError("agent controller cannot access private-label schema")
        return self


class EvaluatorIPCPaths(StrictModel):
    private_input: Path
    private_output: Path
    public_feedback: Path
    private_root: Path
    public_root: Path

    @model_validator(mode="after")
    def paths_respect_permission_roots(self) -> "EvaluatorIPCPaths":
        private_root = self.private_root.resolve()
        public_root = self.public_root.resolve()
        private_input = self.private_input.resolve()
        private_output = self.private_output.resolve()
        public_feedback = self.public_feedback.resolve()
        if not private_input.is_relative_to(private_root):
            raise ValueError("evaluator input must remain under the private root")
        if not private_output.is_relative_to(private_root):
            raise ValueError("full metrics must remain under the private root")
        if not public_feedback.is_relative_to(public_root):
            raise ValueError("sanitized feedback must remain under the public root")
        if private_root == public_root or private_root.is_relative_to(public_root):
            raise ValueError("private evaluator root cannot be inside the Agent-visible root")
        return self

    @classmethod
    def from_environment(
        cls, *, private_input: Path, private_output: Path, public_feedback: Path
    ) -> "EvaluatorIPCPaths":
        private_root = os.environ.get("HIDDEN_EVALUATOR_PRIVATE_ROOT")
        public_root = os.environ.get("AGENT_FEEDBACK_ROOT")
        if not private_root or not public_root:
            raise ValueError("evaluator private/public roots require explicit environment injection")
        return cls(
            private_input=private_input,
            private_output=private_output,
            public_feedback=public_feedback,
            private_root=Path(private_root),
            public_root=Path(public_root),
        )
