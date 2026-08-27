"""
Saga Distributed Transaction Ledger Manager.
Compliant with SDD §2.2.1, §4.6, §5.4 (Firestore Multi-Region nam5 State).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional

from src.core.state import (
    SagaCompensationClass,
    SagaStepRecord,
    SagaStepStatus,
    SagaWorkflowState,
)


class SagaLedgerManager:
    """
    Manages transactional state persistence in Firestore `sagas` collection.
    Provides RPO=0 synchronous step logging and state machine auditing.
    """

    def __init__(self, in_memory: bool = True, firestore_client: Optional[Any] = None):
        self.in_memory = in_memory
        self.firestore_client = firestore_client
        self._memory_store: Dict[str, Dict[str, Any]] = {}

    def _get_timestamp(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def init_saga(
        self,
        session_id: str,
        employee_id: str,
        workflow_type: str,
        saga_id: Optional[str] = None,
    ) -> str:
        """
        Initializes a new distributed Saga workflow transaction in Firestore.
        """
        if not saga_id:
            saga_id = f"saga-{uuid.uuid4().hex[:8]}"

        now = self._get_timestamp()
        # 30-day TTL expiry per NFR-1.3 / §4.6
        ttl_expiry = (
            datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
        ).isoformat()

        saga_doc = {
            "_id": saga_id,
            "sessionId": session_id,
            "employeeId": employee_id,
            "workflowType": workflow_type,
            "currentState": SagaWorkflowState.STARTED.value,
            "steps": [],
            "createdAt": now,
            "updatedAt": now,
            "ttl_expiry": ttl_expiry,
        }

        if self.in_memory or not self.firestore_client:
            self._memory_store[saga_id] = saga_doc
        else:
            self.firestore_client.collection("sagas").document(saga_id).set(saga_doc)

        return saga_id

    def record_step(self, saga_id: str, step: SagaStepRecord) -> None:
        """
        Appends or registers a step record into the Saga ledger.
        """
        if not step.timestamp:
            step.timestamp = self._get_timestamp()

        if self.in_memory or not self.firestore_client:
            if saga_id not in self._memory_store:
                raise KeyError(f"Saga ID '{saga_id}' not found in ledger store.")
            steps = self._memory_store[saga_id]["steps"]
            # Replace existing or append
            for i, s in enumerate(steps):
                if s["stepIndex"] == step.step_index:
                    steps[i] = step.to_dict()
                    self._memory_store[saga_id]["updatedAt"] = self._get_timestamp()
                    return
            steps.append(step.to_dict())
            self._memory_store[saga_id]["updatedAt"] = self._get_timestamp()
        else:
            doc_ref = self.firestore_client.collection("sagas").document(saga_id)
            doc = doc_ref.get().to_dict() or {}
            steps = doc.get("steps", [])
            steps.append(step.to_dict())
            doc_ref.update({"steps": steps, "updatedAt": self._get_timestamp()})

    def update_step_status(
        self,
        saga_id: str,
        step_index: int,
        status: SagaStepStatus,
        external_ref_id: Optional[str] = None,
        compensation_payload: Optional[Dict[str, Any]] = None,
        follow_up_ref: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Updates the status, external reference, or compensation payload of a specific step.
        """
        if self.in_memory or not self.firestore_client:
            if saga_id not in self._memory_store:
                raise KeyError(f"Saga ID '{saga_id}' not found.")
            steps = self._memory_store[saga_id]["steps"]
            for step in steps:
                if step["stepIndex"] == step_index:
                    step["status"] = status.value
                    if external_ref_id:
                        step["externalReferenceId"] = external_ref_id
                    if compensation_payload:
                        step["compensationPayload"] = compensation_payload
                    if follow_up_ref:
                        step["followUpRef"] = follow_up_ref
                    if error_message:
                        step["errorMessage"] = error_message
                    step["timestamp"] = self._get_timestamp()
            self._memory_store[saga_id]["updatedAt"] = self._get_timestamp()
        else:
            doc_ref = self.firestore_client.collection("sagas").document(saga_id)
            doc = doc_ref.get().to_dict() or {}
            steps = doc.get("steps", [])
            for step in steps:
                if step["stepIndex"] == step_index:
                    step["status"] = status.value
                    if external_ref_id:
                        step["externalReferenceId"] = external_ref_id
                    if compensation_payload:
                        step["compensationPayload"] = compensation_payload
                    if follow_up_ref:
                        step["followUpRef"] = follow_up_ref
                    if error_message:
                        step["errorMessage"] = error_message
                    step["timestamp"] = self._get_timestamp()
            doc_ref.update({"steps": steps, "updatedAt": self._get_timestamp()})

    def update_saga_state(self, saga_id: str, state: SagaWorkflowState) -> None:
        """
        Transitions the overall Saga workflow state machine.
        """
        if self.in_memory or not self.firestore_client:
            if saga_id not in self._memory_store:
                raise KeyError(f"Saga ID '{saga_id}' not found.")
            self._memory_store[saga_id]["currentState"] = state.value
            self._memory_store[saga_id]["updatedAt"] = self._get_timestamp()
        else:
            self.firestore_client.collection("sagas").document(saga_id).update({
                "currentState": state.value,
                "updatedAt": self._get_timestamp(),
            })

    def get_saga(self, saga_id: str) -> Dict[str, Any]:
        """
        Retrieves the committed Saga document and step ledger.
        """
        if self.in_memory or not self.firestore_client:
            if saga_id not in self._memory_store:
                raise KeyError(f"Saga ID '{saga_id}' not found.")
            return self._memory_store[saga_id]
        else:
            return self.firestore_client.collection("sagas").document(saga_id).get().to_dict() or {}
