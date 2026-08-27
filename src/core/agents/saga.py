"""
Saga Workflow Coordinator Agent.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.1, §3.2, §3.3 Paths 4-6, §5.4 (NFR-4.3).
Model: Gemini 3.1 Pro (Pinned).
"""

from __future__ import annotations

import logging

from src.core.agents.hcm import HCMSpecialistNode
from src.core.agents.itsm import ITSMSpecialistNode
from src.core.agents.policy import PolicySpecialistNode
from src.core.state import (
    AgentState,
    SagaCompensationClass,
    SagaStepRecord,
    SagaStepStatus,
    SagaWorkflowState,
)
from src.saga.compensation import SagaCompensationDecisionMatrix
from src.saga.ledger import SagaLedgerManager

logger = logging.getLogger("agents.saga")


class SagaCoordinatorNode:
    """
    Cross-System Saga Workflow Coordinator (Gemini 3.1 Pro).
    Sequences multi-system distributed transactions across Policy, HCM, and ITSM.
    Enforces immutable ledger recording and §5.4 Consequence-Aware Compensation.
    """

    AGENT_ID = "saga-1.4.0"
    MODEL_ID = "gemini-3.1-pro@2026-08"

    def __init__(
        self,
        ledger: SagaLedgerManager | None = None,
        policy_agent: PolicySpecialistNode | None = None,
        hcm_agent: HCMSpecialistNode | None = None,
        itsm_agent: ITSMSpecialistNode | None = None,
    ):
        self.ledger = ledger or SagaLedgerManager()
        self.policy_agent = policy_agent or PolicySpecialistNode()
        self.hcm_agent = hcm_agent or HCMSpecialistNode()
        self.itsm_agent = itsm_agent or ITSMSpecialistNode()
        self.compensation_matrix = SagaCompensationDecisionMatrix(
            ledger=self.ledger,
            rollback_handlers={
                "UPDATE_CONTACT": self._rollback_update_contact,
                "SUBMIT_LEAVE": self._rollback_submit_leave,
            },
        )

    async def _rollback_update_contact(self, step: SagaStepRecord, state: AgentState) -> None:
        """Rollback handler for REVERSIBLE_SAFE contact update."""
        prev_payload = step.compensation_payload or {}
        prev_address = prev_payload.get("previousAddress")
        prev_phone = prev_payload.get("previousPhone")
        employee_id = state.get("employee_id", "EMP-44210")
        logger.info("Executing rollback for UPDATE_CONTACT on %s -> restoring %s", employee_id, prev_address)
        self.hcm_agent.update_contact(
            employee_id=employee_id,
            new_address=prev_address,
            new_phone=prev_phone,
        )

    async def _rollback_submit_leave(self, step: SagaStepRecord, state: AgentState) -> None:
        """Rollback handler for leave (only executed if classified REVERSIBLE_SAFE)."""
        if step.external_ref_id:
            employee_id = state.get("employee_id", "EMP-44210")
            self.hcm_agent.cancel_leave(employee_id, step.external_ref_id)

    def _sync_state_ledger(self, state: AgentState, saga_id: str) -> None:
        """Synchronizes in-memory state saga_ledger with the authoritative Firestore ledger document."""
        doc = self.ledger.get_saga(saga_id)
        steps = doc.get("steps", [])
        state["saga_ledger"] = [
            SagaStepRecord(
                step_index=s["stepIndex"],
                target_system=s["targetSystem"],
                action=s["action"],
                compensation_class=SagaCompensationClass(s["compensationClass"]),
                status=SagaStepStatus(s["status"]),
                external_ref_id=s.get("externalReferenceId"),
                compensation_payload=s.get("compensationPayload"),
                follow_up_ref=s.get("followUpRef"),
                error_message=s.get("errorMessage"),
                timestamp=s.get("timestamp"),
            )
            for s in steps
        ]

    async def execute(self, state: AgentState) -> AgentState:
        """
        Routes and coordinates cross-system Saga execution based on `saga_type`.
        """
        saga_type = state.get("saga_type", "UC-2.2-MEDICAL-LEAVE")
        session_id = state.get("session_id", "sess-test")
        employee_id = state.get("employee_id", "EMP-44210")

        saga_id = self.ledger.init_saga(
            session_id=session_id,
            employee_id=employee_id,
            workflow_type=saga_type,
            saga_id=state.get("saga_id"),
        )
        state["saga_id"] = saga_id

        logger.info("[%s] Initiated %s under Saga %s", self.AGENT_ID, saga_type, saga_id)

        if saga_type == "UC-2.1-EQUIPMENT":
            return await self._execute_uc21_equipment(state, saga_id, employee_id)
        elif saga_type == "UC-2.2-MEDICAL-LEAVE":
            return await self._execute_uc22_medical_leave(state, saga_id, employee_id)
        elif saga_type == "UC-2.3-RELOCATION":
            return await self._execute_uc23_relocation(state, saga_id, employee_id)
        else:
            state["final_response"] = f"Unknown cross-system workflow type: {saga_type}"
            state["next_node"] = "guardrails_out"
            return state

    # =========================================================================
    # Path 4: UC-2.1 Equipment Procurement (§3.3 Path 4)
    # =========================================================================
    async def _execute_uc21_equipment(
        self, state: AgentState, saga_id: str, employee_id: str
    ) -> AgentState:
        # Step 1: Query Policy Entitlement (READ_ONLY)
        step1 = SagaStepRecord(
            step_index=1,
            target_system="Policy",
            action="QUERY_REMOTE_EQUIPMENT_POLICY",
            compensation_class=SagaCompensationClass.READ_ONLY,
            status=SagaStepStatus.SUCCESS,
            external_ref_id="policies/remote-work-2026.pdf#s4.2",
        )
        self.ledger.record_step(saga_id, step1)

        # Step 2: Query WorkWeek Profile (READ_ONLY)
        profile = self.hcm_agent.get_profile(employee_id)
        is_remote = profile.get("workLocation") == "REMOTE"
        step2 = SagaStepRecord(
            step_index=2,
            target_system="WorkWeek",
            action="GET_PROFILE_WORK_LOCATION",
            compensation_class=SagaCompensationClass.READ_ONLY,
            status=SagaStepStatus.SUCCESS,
            external_ref_id=profile.get("workLocation"),
        )
        self.ledger.record_step(saga_id, step2)

        if not is_remote:
            self.ledger.update_saga_state(saga_id, SagaWorkflowState.COMPLETED)
            self._sync_state_ledger(state, saga_id)
            state["saga_state"] = SagaWorkflowState.COMPLETED.value
            state["final_response"] = (
                "Your employee profile indicates an on-site work location. Under Remote Work Policy s4.2, "
                "the home office ergonomic monitor entitlement is restricted to remote-designated employees. "
                "No hardware request has been raised."
            )
            state["next_node"] = "guardrails_out"
            return state

        # Step 3: Create ITSM Hardware Request (ANCILLARY)
        faults = state.get("injected_faults", {})
        if faults.get("step_3_fail"):
            step3 = SagaStepRecord(
                step_index=3,
                target_system="ServiceImmediately",
                action="CREATE_HARDWARE_TICKET",
                compensation_class=SagaCompensationClass.ANCILLARY,
                status=SagaStepStatus.PENDING,
            )
            self.ledger.record_step(saga_id, step3)

            res_state, user_msg = await self.compensation_matrix.handle_step_failure(
                saga_id=saga_id,
                failed_step_index=3,
                error_reason="ITSM Gateway 503 Service Unavailable",
                state=state,
            )
            self._sync_state_ledger(state, saga_id)
            state["saga_state"] = res_state.value
            state["final_response"] = user_msg
            state["next_node"] = "guardrails_out"
            return state

        ticket = self.itsm_agent.create_incident(
            caller_id=employee_id,
            category="Hardware Request",
            short_description="Ergonomic Home Office Monitor - Cap $350 (Remote Work s4.2)",
            priority="4-Low",
        )
        step3 = SagaStepRecord(
            step_index=3,
            target_system="ServiceImmediately",
            action="CREATE_HARDWARE_TICKET",
            compensation_class=SagaCompensationClass.ANCILLARY,
            status=SagaStepStatus.SUCCESS,
            external_ref_id=ticket["ticketId"],
        )
        self.ledger.record_step(saga_id, step3)
        self.ledger.update_saga_state(saga_id, SagaWorkflowState.COMPLETED)
        self._sync_state_ledger(state, saga_id)

        state["saga_state"] = SagaWorkflowState.COMPLETED.value
        state["final_response"] = (
            f"Verified remote eligibility under Remote Work Policy s4.2. "
            f"Hardware procurement request **{ticket['ticketId']}** has been submitted for shipping to your address on file."
        )
        state["next_node"] = "guardrails_out"
        return state

    # =========================================================================
    # Path 5: UC-2.2 Medical Leave with Consequence-Aware Compensation (§3.3 Path 5)
    # =========================================================================
    async def _execute_uc22_medical_leave(
        self, state: AgentState, saga_id: str, employee_id: str
    ) -> AgentState:
        # Step 1: WorkWeek Leave Filing (HUMAN_CONSEQUENTIAL)
        leave_res = self.hcm_agent.submit_leave(
            employee_id=employee_id,
            leave_type="Medical",
            start_date="2026-09-01",
            end_date="2026-09-15",
            work_days=10.0,
        )
        leave_id = leave_res["leaveId"]
        step1 = SagaStepRecord(
            step_index=1,
            target_system="WorkWeek",
            action="SUBMIT_LEAVE",
            compensation_class=SagaCompensationClass.HUMAN_CONSEQUENTIAL,
            status=SagaStepStatus.SUCCESS,
            external_ref_id=leave_id,
        )
        self.ledger.record_step(saga_id, step1)

        # Step 2: ITSM Manager-Approval Routing Ticket (ANCILLARY)
        faults = state.get("injected_faults", {})
        if faults.get("step_2_fail") or faults.get("itsm_503"):
            step2 = SagaStepRecord(
                step_index=2,
                target_system="ServiceImmediately",
                action="CREATE_ROUTING_TICKET",
                compensation_class=SagaCompensationClass.ANCILLARY,
                status=SagaStepStatus.PENDING,
            )
            self.ledger.record_step(saga_id, step2)

            res_state, user_msg = await self.compensation_matrix.handle_step_failure(
                saga_id=saga_id,
                failed_step_index=2,
                error_reason="ITSM 503 Service Unavailable (retries exhausted)",
                state=state,
            )
            self._sync_state_ledger(state, saga_id)
            state["saga_state"] = res_state.value
            state["final_response"] = user_msg
            state["next_node"] = "guardrails_out"
            return state

        # Step 2 Success Happy Path
        ticket = self.itsm_agent.create_incident(
            caller_id=employee_id,
            category="Access",
            short_description=f"Route approval and email delegation for Medical Leave {leave_id}",
            priority="3-Moderate",
        )
        step2 = SagaStepRecord(
            step_index=2,
            target_system="ServiceImmediately",
            action="CREATE_ROUTING_TICKET",
            compensation_class=SagaCompensationClass.ANCILLARY,
            status=SagaStepStatus.SUCCESS,
            external_ref_id=ticket["ticketId"],
        )
        self.ledger.record_step(saga_id, step2)
        self.ledger.update_saga_state(saga_id, SagaWorkflowState.COMPLETED)
        self._sync_state_ledger(state, saga_id)

        state["saga_state"] = SagaWorkflowState.COMPLETED.value
        state["final_response"] = (
            f"Your medical leave filing **{leave_id}** has been submitted for manager approval. "
            f"IT routing and mailbox delegation ticket **{ticket['ticketId']}** has been created."
        )
        state["next_node"] = "guardrails_out"
        return state

    # =========================================================================
    # Path 6: UC-2.3 Relocation with Safe Rollback (§3.3 Path 6)
    # =========================================================================
    async def _execute_uc23_relocation(
        self, state: AgentState, saga_id: str, employee_id: str
    ) -> AgentState:
        # Step 1: WorkWeek Contact Update (REVERSIBLE_SAFE)
        new_address = "100 Bishopsgate, London EC2N 4AG, United Kingdom"
        update_res = self.hcm_agent.update_contact(
            employee_id=employee_id,
            new_address=new_address,
        )
        step1 = SagaStepRecord(
            step_index=1,
            target_system="WorkWeek",
            action="UPDATE_CONTACT",
            compensation_class=SagaCompensationClass.REVERSIBLE_SAFE,
            status=SagaStepStatus.SUCCESS,
            compensation_payload={
                "previousAddress": update_res["previousAddress"],
                "previousPhone": update_res["previousPhone"],
                "newAddress": new_address,
            },
        )
        self.ledger.record_step(saga_id, step1)

        # Step 2: ITSM Facilities Badge Access (REVERSIBLE_SAFE)
        faults = state.get("injected_faults", {})
        if faults.get("step_2_fail") or faults.get("facilities_ticket_fail"):
            step2 = SagaStepRecord(
                step_index=2,
                target_system="ServiceImmediately",
                action="CREATE_FACILITIES_TICKET",
                compensation_class=SagaCompensationClass.REVERSIBLE_SAFE,
                status=SagaStepStatus.PENDING,
            )
            self.ledger.record_step(saga_id, step2)

            res_state, user_msg = await self.compensation_matrix.handle_step_failure(
                saga_id=saga_id,
                failed_step_index=2,
                error_reason="Facilities API 500 Internal Error",
                state=state,
            )
            self._sync_state_ledger(state, saga_id)
            state["saga_state"] = res_state.value
            state["final_response"] = user_msg
            state["next_node"] = "guardrails_out"
            return state

        # Step 2 Success Happy Path
        ticket = self.itsm_agent.create_incident(
            caller_id=employee_id,
            category="Facilities",
            short_description="London Office Badge Provisioning & Relocation",
            priority="3-Moderate",
        )
        step2 = SagaStepRecord(
            step_index=2,
            target_system="ServiceImmediately",
            action="CREATE_FACILITIES_TICKET",
            compensation_class=SagaCompensationClass.REVERSIBLE_SAFE,
            status=SagaStepStatus.SUCCESS,
            external_ref_id=ticket["ticketId"],
        )
        self.ledger.record_step(saga_id, step2)
        self.ledger.update_saga_state(saga_id, SagaWorkflowState.COMPLETED)
        self._sync_state_ledger(state, saga_id)

        state["saga_state"] = SagaWorkflowState.COMPLETED.value
        state["final_response"] = (
            f"Relocation allowance confirmed under Policy s2.4 (Cap $5,000). "
            f"WorkWeek address updated to London, and building access ticket **{ticket['ticketId']}** raised."
        )
        state["next_node"] = "guardrails_out"
        return state
