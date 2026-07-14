"""Frozen two-turn memory protocol and transaction integration tests."""

from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError

from apt_detection_agent.runtime import (
    CommittedResultLedger,
    FrozenRuntimeConfig,
    FrozenRuntimeController,
    FrozenTransactionLogger,
)
from apt_detection_agent.memory import FrozenMemoryProtocol
from apt_detection_agent.schemas import (
    DataSplit,
    FrozenActionType,
    MemoryActionResponse,
    MemoryDisposition,
    MemoryLayer,
    MemoryReadRequest,
    MemoryRecord,
    MemoryRetrievalResult,
    MemoryUseDecision,
    MemoryWriteCandidate,
    RunStatus,
)
from tests.test_agent_runtime_contract import NOW, canonical_observation, window
from tests.test_frozen_runtime import action, case, committed_bundle, prompt, trigger
from tests.test_schemas import valid_memory


SHA = "a" * 64


def empty_read(prompt_id: str = "prompt-0") -> MemoryReadRequest:
    return MemoryReadRequest(
        request_id="memory-read-1",
        prompt_id=prompt_id,
        case_id="case-1",
        needed=False,
        reason_code="no-applicable-memory-needed",
        visible_evidence_ids=("observation-1",),
    )


def empty_result() -> MemoryRetrievalResult:
    return MemoryRetrievalResult(
        result_id="memory-result-1",
        request_id="memory-read-1",
        needed=False,
        status=RunStatus.SUCCEEDED,
        candidate_count=0,
        estimated_tokens=0,
        truncated=False,
        policy_validation_status="unvalidated-engineering-default",
    )


class MemoryProtocolTests(unittest.TestCase):
    def test_needed_false_still_has_two_turn_shape_and_empty_tool_result(self) -> None:
        model_prompt = prompt(canonical_observation(), trigger(True), ())
        terminal = action(FrozenActionType.FINISH_DIAGNOSIS)
        tool_calls = 0

        def retrieval(request, state):
            nonlocal tool_calls
            tool_calls += 1
            return empty_result()

        protocol = FrozenMemoryProtocol(
            read_policy=lambda prompt_value, state: empty_read(prompt_value.prompt_id),
            retrieval_tool=retrieval,
            action_policy=lambda prompt_value, result, state: MemoryActionResponse(
                response_id="memory-response-1",
                prompt_id=prompt_value.prompt_id,
                retrieval_result_id=result.result_id,
                use_decisions=(),
                diagnosis_code="no-change-needed",
                action=terminal,
            ),
        )
        decision = protocol(model_prompt, case())
        self.assertEqual(tool_calls, 1)
        self.assertFalse(decision.exchange.read_request.needed)
        self.assertEqual(decision.exchange.retrieval_result.records, ())
        self.assertEqual(decision.action, terminal)

    def test_every_retrieved_record_gets_exact_disposition_and_used_id_is_cited(self) -> None:
        model_prompt = prompt(canonical_observation(), trigger(True), ())
        record = valid_memory()
        result = MemoryRetrievalResult(
            result_id="memory-result-1",
            request_id="memory-read-1",
            needed=True,
            status=RunStatus.SUCCEEDED,
            records=(record,),
            candidate_count=1,
            estimated_tokens=10,
            truncated=False,
            policy_validation_status="unvalidated-engineering-default",
        )
        action_payload = action(FrozenActionType.FINISH_DIAGNOSIS).model_dump()
        action_payload["visible_evidence_ids"] = (record.memory_id,)
        terminal = type(action(FrozenActionType.FINISH_DIAGNOSIS)).model_validate(action_payload)
        protocol = FrozenMemoryProtocol(
            read_policy=lambda prompt_value, state: MemoryReadRequest(
                request_id="memory-read-1",
                prompt_id=prompt_value.prompt_id,
                case_id=state.case_id,
                needed=True,
                query="observable score shift",
                reason_code="prior-case-may-apply",
                visible_evidence_ids=("observation-1",),
            ),
            retrieval_tool=lambda request, state: result,
            action_policy=lambda prompt_value, retrieved, state: MemoryActionResponse(
                response_id="memory-response-1",
                prompt_id=prompt_value.prompt_id,
                retrieval_result_id=retrieved.result_id,
                use_decisions=(
                    MemoryUseDecision(
                        memory_id=record.memory_id,
                        disposition=MemoryDisposition.USE,
                        reason_code="same-visible-symptom",
                        visible_evidence_ids=("observation-1",),
                    ),
                ),
                diagnosis_code="memory-supported-no-change",
                action=terminal,
            ),
        )
        exchange = protocol(model_prompt, case()).exchange
        self.assertEqual(exchange.response.use_decisions[0].disposition, MemoryDisposition.USE)
        bad_response = exchange.response.model_copy(update={"use_decisions": ()})
        with self.assertRaises(ValidationError):
            type(exchange).model_validate(
                {**exchange.model_dump(), "response": bad_response.model_dump()}
            )

    def test_privileged_retrieval_and_pre_outcome_success_claim_fail_closed(self) -> None:
        leaked = valid_memory(
            content="Teacher rationale reveals the target.",
            normalized_content_hash=SHA,
        )
        with self.assertRaises(ValidationError):
            MemoryRetrievalResult(
                result_id="memory-result-leaked",
                request_id="memory-read-1",
                needed=True,
                status=RunStatus.SUCCEEDED,
                records=(leaked,),
                candidate_count=1,
                estimated_tokens=10,
                truncated=False,
                policy_validation_status="unvalidated-engineering-default",
            )
        with self.assertRaises(ValidationError):
            MemoryWriteCandidate(
                candidate_id="write-1",
                layer=MemoryLayer.EPISODE,
                observable_behavior="score shift",
                pids_id="velox",
                intended_action="run additional detector",
                content="The detector succeeded and should always be reused.",
                evidence_artifact_ids=("observation-1",),
            )

    def test_formal_runtime_persists_memory_exchange_separately(self) -> None:
        terminal = action(FrozenActionType.FINISH_DIAGNOSIS)
        protocol = FrozenMemoryProtocol(
            read_policy=lambda prompt_value, state: empty_read(prompt_value.prompt_id),
            retrieval_tool=lambda request, state: empty_result(),
            action_policy=lambda prompt_value, result, state: MemoryActionResponse(
                response_id="memory-response-1",
                prompt_id=prompt_value.prompt_id,
                retrieval_result_id=result.result_id,
                use_decisions=(),
                diagnosis_code="no-change-needed",
                action=terminal,
            ),
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            controller = FrozenRuntimeController(
                config=FrozenRuntimeConfig(
                    trigger_profile_id="validated-trigger-v1",
                    trigger_source_split=DataSplit.VALIDATION,
                    max_additional_detector_cycles=1,
                    require_frozen_memory_protocol=True,
                ),
                committed_executor=committed_bundle,
                canonical_builder=lambda bundle, state: canonical_observation(),
                trigger_policy=lambda observation: trigger(True),
                prompt_builder=prompt,
                policy=protocol,
                action_executor=lambda *args: (_ for _ in ()).throw(
                    AssertionError("terminal action called executor")
                ),
                committed_ledger=CommittedResultLedger(root / "committed.jsonl"),
                transaction_logger=FrozenTransactionLogger(root / "transactions.jsonl"),
            )
            step = controller.run_window(
                case=case(),
                window=window(),
                started_at=NOW,
                ended_at=NOW + timedelta(seconds=1),
            )
            self.assertEqual(step.record.memory_protocol_status, "frozen-two-turn")
            self.assertEqual(len(step.record.memory_exchange_ids), 1)
            self.assertEqual(len((root / "memory_exchanges.jsonl").read_text().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
