"""Evaluator-private links for demonstration selection; never public exports."""

from __future__ import annotations

import json

from pydantic import Field

from apt_detection_agent.schemas.common import Identifier, StrictModel


class PrivateDatasetCompanionManifest(StrictModel):
    private_manifest_id: Identifier
    public_dataset_manifest_id: Identifier
    campaign_manifest_ids: tuple[Identifier, ...]
    ground_truth_artifact_refs: tuple[str, ...]
    evaluator_role_id: Identifier
    permission_profile_id: Identifier


class HiddenOfflineRunEvaluationLink(StrictModel):
    link_id: Identifier
    public_run_record_id: Identifier
    private_evaluation_ref: Identifier
    private_counterfactual_group_ref: Identifier | None = None


class PrivateTeacherSelectionRecord(StrictModel):
    selection_id: Identifier
    candidate_trajectory_ids: tuple[Identifier, ...] = Field(min_length=1)
    selected_trajectory_id: Identifier | None = None
    private_reason_codes: tuple[Identifier, ...]
    ambiguous_public_choice: bool


class StrictTeacherSelectionParser:
    """Parse only an opaque candidate choice; private rationale stays evaluator-side."""

    @staticmethod
    def parse(
        *,
        selection_id: str,
        candidate_trajectory_ids: tuple[str, ...],
        response_text: str,
        private_reason_codes: tuple[str, ...],
    ) -> PrivateTeacherSelectionRecord:
        try:
            payload = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise ValueError("teacher response must be strict JSON") from exc
        if set(payload) != {"selected_trajectory_id", "ambiguous_public_choice"}:
            raise ValueError("teacher response contains undeclared fields")
        selected = payload["selected_trajectory_id"]
        ambiguous = payload["ambiguous_public_choice"]
        if selected is not None and selected not in candidate_trajectory_ids:
            raise ValueError("teacher selected a candidate outside the supplied set")
        if not isinstance(ambiguous, bool):
            raise ValueError("ambiguous_public_choice must be boolean")
        if ambiguous and selected is not None:
            raise ValueError("ambiguous public evidence cannot select a unique target")
        if not ambiguous and selected is None:
            raise ValueError("unambiguous selection requires a target")
        return PrivateTeacherSelectionRecord(
            selection_id=selection_id,
            candidate_trajectory_ids=candidate_trajectory_ids,
            selected_trajectory_id=selected,
            private_reason_codes=private_reason_codes,
            ambiguous_public_choice=ambiguous,
        )
