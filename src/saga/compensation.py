"""
Saga Consequence-Aware Compensation Decision Matrix.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §5.4 (NFR-4.3).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from src.core.state import (
    AgentState,
    SagaCompensationClass,
    SagaStepRecord,
    SagaStepStatus,
    SagaWorkflowState,
)
from src.saga.ledger import SagaLedgerManager
from src.telemetry.compensation_event import (
    PriorStepRef,
    SagaCompensationEvent,
    emit_compensation_event,
    field_names_only,
    payload_digest,
    surrogate,
)

logger = logging.getLogger("saga.compensation")


class SagaCompensationDecisionMatrix:
    """
    Evaluates failure transitions and orchestrates safe compensation policies.
    Guarantees:
    1. Zero auto-reversals of HUMAN_CONSEQUENTIAL steps (e.g., Medical Leave filings).
    2. Automatic rollback of REVERSIBLE_SAFE steps with captured prior state (e.g., Address update).
    3. Safe handoff to human operations for ANCILLARY step failures with primary state preservation.
    """

    def __init__(
        self,
        ledger: SagaLedgerManager,
        rollback_handlers: dict[str, Callable[[SagaStepRecord, AgentState], Any]] | None = None,
    ):
        self.ledger = ledger
        self.rollback_handlers = rollback_handlers or {}
        self.ops_queue: list[dict[str, Any]] = []

    def _emit_audit_event(
        self,
        *,
        saga_id: str,
        state: AgentState,
        failed_step_dict: dict[str, Any],
        failed_class: SagaCompensationClass,
        prior_steps: list[dict[str, Any]],
        rolled_back_indices: set[int],
        decision: str,
        outcome: str,
        follow_up_ref: str | None,
    ) -> SagaCompensationEvent:
        """Emit the §4.11 Z2 audit record for this compensation decision.

        Assembled in one place rather than at each branch, so that "can a raw
        value reach the audit archive?" is a question with a single place to
        read for the answer. The failed step's payload is reduced to a pointer,
        a digest and its field *names* before it gets anywhere near the record.
        """
        payload = failed_step_dict.get("compensationPayload")
        return emit_compensation_event(
            SagaCompensationEvent(
                saga_id=saga_id,
                session_id=state.get("session_id"),
                employee_id_hash=surrogate(state.get("employee_id")),
                failed_step_index=failed_step_dict["stepIndex"],
                failed_step_action=failed_step_dict["action"],
                compensation_class=failed_class.value,
                compensation_decision=decision,
                compensation_target_system=failed_step_dict.get("targetSystem"),
                external_reference_id=failed_step_dict.get("externalReferenceId"),
                prior_step_refs=[
                    PriorStepRef(
                        index=p["stepIndex"],
                        system=p["targetSystem"],
                        ref=p.get("externalReferenceId"),
                        step_class=p["compensationClass"],
                        action_taken=(
                            "ROLLED_BACK" if p["stepIndex"] in rolled_back_indices else "LEFT_IN_PLACE"
                        ),
                    )
                    for p in prior_steps
                ],
                payload_pointer=f"firestore://sagas/{saga_id}/steps/{failed_step_dict['stepIndex']}",
                payload_digest=payload_digest(payload),
                field_names_only=field_names_only(payload),
                human_followup_ticket=follow_up_ref,
                outcome=outcome,
            )
        )

    def register_rollback_handler(
        self, action: str, handler: Callable[[SagaStepRecord, AgentState], Any]
    ) -> None:
        self.rollback_handlers[action] = handler

    async def handle_step_failure(
        self,
        saga_id: str,
        failed_step_index: int,
        error_reason: str,
        state: AgentState,
    ) -> tuple[SagaWorkflowState, str]:
        """
        Executes the §5.4 compensation decision tree upon permanent failure of step N.

        Returns:
            (resulting_saga_state, user_explanation_message)
        """
        ledger_doc = self.ledger.get_saga(saga_id)
        steps = ledger_doc.get("steps", [])

        # Locate failed step
        failed_step_dict = None
        for s in steps:
            if s["stepIndex"] == failed_step_index:
                failed_step_dict = s
                break

        if not failed_step_dict:
            raise ValueError(f"Step {failed_step_index} not found in saga {saga_id}")

        failed_class = SagaCompensationClass(failed_step_dict["compensationClass"])

        # Prior steps that succeeded
        prior_steps = [
            s for s in steps
            if s["stepIndex"] < failed_step_index and s["status"] == SagaStepStatus.SUCCESS.value
        ]

        logger.info(
            "Evaluating Saga compensation for %s at Step %s (Action: %s, Class: %s)",
            saga_id, failed_step_index, failed_step_dict["action"], failed_class.value,
        )

        # -------------------------------------------------------------
        # Branch 1: The failed step N itself is ANCILLARY (e.g., UC-2.2 Medical Leave Step 2)
        # -------------------------------------------------------------
        if failed_class == SagaCompensationClass.ANCILLARY:
            follow_up_ref = f"OPS-{uuid.uuid4().hex[:6].upper()}"
            self.ledger.update_step_status(
                saga_id=saga_id,
                step_index=failed_step_index,
                status=SagaStepStatus.FAILED_HANDED_TO_HUMAN,
                follow_up_ref=follow_up_ref,
                error_message=error_reason,
            )

            resulting_state = SagaWorkflowState.PARTIALLY_COMPLETED_MANUAL_FOLLOWUP
            self.ledger.update_saga_state(saga_id, resulting_state)

            # Raise P2 Operations follow-up task
            ops_task = {
                "followUpRef": follow_up_ref,
                "sagaId": saga_id,
                "workflowType": state.get("saga_type"),
                "employeeId": state.get("employee_id"),
                "failedStep": failed_step_dict,
                "preservedSteps": prior_steps,
                "severity": "P2",
                "reason": f"Ancillary step failure: {error_reason}",
            }
            self.ops_queue.append(ops_task)

            # Retrieve primary reference if available
            primary_ref = None
            for p in prior_steps:
                if p.get("externalReferenceId"):
                    primary_ref = p["externalReferenceId"]
                    break

            self._emit_audit_event(
                saga_id=saga_id,
                state=state,
                failed_step_dict=failed_step_dict,
                failed_class=failed_class,
                prior_steps=prior_steps,
                rolled_back_indices=set(),
                decision="FLAG_AND_ESCALATE",
                outcome="ESCALATED_TO_HUMAN",
                follow_up_ref=follow_up_ref,
            )

            ref_str = f" {primary_ref}" if primary_ref else ""
            user_message = (
                f"Your primary request{ref_str} has been filed successfully and stands unaffected. "
                f"However, the automated follow-up step ({failed_step_dict['action']}) could not complete, "
                f"so it has been routed to the service operations team under reference {follow_up_ref}. "
                f"No further action is required from you."
            )
            return resulting_state, user_message

        # -------------------------------------------------------------
        # Branch 2: ALL prior steps are READ_ONLY or REVERSIBLE_SAFE
        # (e.g., UC-2.3 Relocation Address update rolled back on badge failure)
        # -------------------------------------------------------------
        all_prior_reversible = all(
            p["compensationClass"] in [SagaCompensationClass.READ_ONLY.value, SagaCompensationClass.REVERSIBLE_SAFE.value]
            for p in prior_steps
        )

        if all_prior_reversible and prior_steps:
            # Rollback in reverse order
            reversed_indices: set[int] = set()
            for p in reversed(prior_steps):
                if p["compensationClass"] == SagaCompensationClass.REVERSIBLE_SAFE.value:
                    action = p["action"]
                    step_record = SagaStepRecord(
                        step_index=p["stepIndex"],
                        target_system=p["targetSystem"],
                        action=action,
                        compensation_class=SagaCompensationClass(p["compensationClass"]),
                        status=SagaStepStatus(p["status"]),
                        external_ref_id=p.get("externalReferenceId"),
                        compensation_payload=p.get("compensationPayload"),
                    )

                    handler = self.rollback_handlers.get(action)
                    if handler:
                        await handler(step_record, state)

                    self.ledger.update_step_status(
                        saga_id=saga_id,
                        step_index=p["stepIndex"],
                        status=SagaStepStatus.ROLLED_BACK,
                    )
                    reversed_indices.add(p["stepIndex"])

            self.ledger.update_step_status(
                saga_id=saga_id,
                step_index=failed_step_index,
                status=SagaStepStatus.FAILED,
                error_message=error_reason,
            )

            resulting_state = SagaWorkflowState.COMPENSATED_ROLLED_BACK
            self.ledger.update_saga_state(saga_id, resulting_state)

            self._emit_audit_event(
                saga_id=saga_id,
                state=state,
                failed_step_dict=failed_step_dict,
                failed_class=failed_class,
                prior_steps=prior_steps,
                rolled_back_indices=reversed_indices,
                decision="ROLLBACK_REVERSIBLE",
                outcome="ROLLED_BACK",
                follow_up_ref=None,
            )

            user_message = (
                "We encountered an issue completing your multi-system request. "
                "To prevent inconsistent records, prior reversible changes have been safely restored. "
                "Please retry or contact support if the issue persists."
            )
            return resulting_state, user_message

        # -------------------------------------------------------------
        # Branch 3: Mixed prior steps containing HUMAN_CONSEQUENTIAL
        # -------------------------------------------------------------
        # Compensate ONLY REVERSIBLE_SAFE steps, never HUMAN_CONSEQUENTIAL
        reversed_indices = set()
        for p in reversed(prior_steps):
            if p["compensationClass"] == SagaCompensationClass.REVERSIBLE_SAFE.value:
                action = p["action"]
                step_record = SagaStepRecord(
                    step_index=p["stepIndex"],
                    target_system=p["targetSystem"],
                    action=action,
                    compensation_class=SagaCompensationClass(p["compensationClass"]),
                    status=SagaStepStatus(p["status"]),
                    external_ref_id=p.get("externalReferenceId"),
                    compensation_payload=p.get("compensationPayload"),
                )
                handler = self.rollback_handlers.get(action)
                if handler:
                    await handler(step_record, state)
                self.ledger.update_step_status(
                    saga_id=saga_id,
                    step_index=p["stepIndex"],
                    status=SagaStepStatus.ROLLED_BACK,
                )
                reversed_indices.add(p["stepIndex"])

        follow_up_ref = f"OPS-{uuid.uuid4().hex[:6].upper()}"
        self.ledger.update_step_status(
            saga_id=saga_id,
            step_index=failed_step_index,
            status=SagaStepStatus.FAILED_HANDED_TO_HUMAN,
            follow_up_ref=follow_up_ref,
            error_message=error_reason,
        )

        resulting_state = SagaWorkflowState.PARTIALLY_COMPLETED_MANUAL_FOLLOWUP
        self.ledger.update_saga_state(saga_id, resulting_state)

        self._emit_audit_event(
            saga_id=saga_id,
            state=state,
            failed_step_dict=failed_step_dict,
            failed_class=failed_class,
            prior_steps=prior_steps,
            rolled_back_indices=reversed_indices,
            decision="PRESERVE_AND_ESCALATE",
            outcome="ESCALATED_TO_HUMAN",
            follow_up_ref=follow_up_ref,
        )

        user_message = (
            f"Your request was partially completed. Consequential records have been preserved, "
            f"while outstanding items have been routed to HR/IT operations (Ref: {follow_up_ref})."
        )
        return resulting_state, user_message
