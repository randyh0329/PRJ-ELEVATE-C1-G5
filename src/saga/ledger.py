"""
Saga Distributed Transaction Ledger Manager.
Compliant with SDD §2.2.1, §4.6, §5.4 (Firestore Multi-Region nam5 State).
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from src.core.state import (
    SagaStepRecord,
    SagaStepStatus,
    SagaWorkflowState,
)


class SagaLedgerManager:
    """
    Manages transactional state persistence in Firestore `sagas` collection.
    Provides RPO=0 synchronous step logging and state machine auditing.
    """

    def __init__(self, in_memory: bool = True, firestore_client: Any | None = None):
        self.in_memory = in_memory
        self.firestore_client = firestore_client
        self._memory_store: dict[str, dict[str, Any]] = {}

    def _get_timestamp(self) -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def init_saga(
        self,
        session_id: str,
        employee_id: str,
        workflow_type: str,
        saga_id: str | None = None,
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
            self._upsert(steps, step)
            self._memory_store[saga_id]["updatedAt"] = self._get_timestamp()
        else:
            doc_ref = self.firestore_client.collection("sagas").document(saga_id)
            doc = doc_ref.get().to_dict() or {}
            steps = doc.get("steps", [])
            self._upsert(steps, step)
            doc_ref.update({"steps": steps, "updatedAt": self._get_timestamp()})

    @staticmethod
    def _upsert(steps: list[dict[str, Any]], step: SagaStepRecord) -> None:
        """Replace the record at this step index, or append if it is new.

        Recording a step is idempotent by index because RPO=0 logging means the
        orchestrator writes before it acts and may re-enter the same step after a
        retry. Appending instead would leave two rows for one step, and the
        compensation walk (§5.4) would then try to reverse it twice.
        """
        for i, existing in enumerate(steps):
            if existing["stepIndex"] == step.step_index:
                steps[i] = step.to_dict()
                return
        steps.append(step.to_dict())

    def update_step_status(
        self,
        saga_id: str,
        step_index: int,
        status: SagaStepStatus,
        external_ref_id: str | None = None,
        compensation_payload: dict[str, Any] | None = None,
        follow_up_ref: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """
        Updates the status, external reference, or compensation payload of a specific step.
        """
        patch = {
            "status": status.value,
            "externalReferenceId": external_ref_id,
            "compensationPayload": compensation_payload,
            "followUpRef": follow_up_ref,
            "errorMessage": error_message,
        }

        if self.in_memory or not self.firestore_client:
            if saga_id not in self._memory_store:
                raise KeyError(f"Saga ID '{saga_id}' not found.")
            self._patch_step(self._memory_store[saga_id]["steps"], step_index, patch)
            self._memory_store[saga_id]["updatedAt"] = self._get_timestamp()
        else:
            doc_ref = self.firestore_client.collection("sagas").document(saga_id)
            doc = doc_ref.get().to_dict() or {}
            steps = doc.get("steps", [])
            self._patch_step(steps, step_index, patch)
            doc_ref.update({"steps": steps, "updatedAt": self._get_timestamp()})

    def _patch_step(
        self, steps: list[dict[str, Any]], step_index: int, patch: dict[str, Any]
    ) -> None:
        """Apply the non-empty fields of `patch` to the step at `step_index`.

        `None` fields are skipped rather than written: an update that only
        carries a status must not erase the external reference of the call that
        created the step, which is the handle compensation needs (§5.4).
        """
        for step in steps:
            if step["stepIndex"] == step_index:
                step.update({k: v for k, v in patch.items() if v is not None})
                step["timestamp"] = self._get_timestamp()

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

    def get_saga(self, saga_id: str) -> dict[str, Any]:
        """
        Retrieves the committed Saga document and step ledger.
        """
        if self.in_memory or not self.firestore_client:
            if saga_id not in self._memory_store:
                raise KeyError(f"Saga ID '{saga_id}' not found.")
            return self._memory_store[saga_id]
        else:
            return self.firestore_client.collection("sagas").document(saga_id).get().to_dict() or {}
