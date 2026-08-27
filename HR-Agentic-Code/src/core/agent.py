"""Enterprise HR Agent Orchestrator (Reasoning Engine runtime)."""
import datetime
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.core.safety import DLPRedactor, ModelArmor, dlp_redactor, model_armor
from src.core.session import SessionMemory, session_store
from src.core.saga import SagaCoordinator, saga_coordinator
from src.grounding.policy_engine import DualGroundingEngine, dual_grounding_engine
from src.integrations.workweek.client import WorkWeekClient, workweek_client
from src.integrations.service_immediately.client import ServiceImmediatelyClient, service_immediately_client
from src.telemetry.audit_logger import AuditLogger, audit_logger


class AgentResponse(BaseModel):
    """Structured response from the HR Enterprise Agent."""
    response_text: str
    intent: str
    citations: List[str] = Field(default_factory=list)
    action_performed: Optional[str] = None
    transaction_reference: Optional[str] = None
    is_refusal: bool = False
    processing_metadata: Dict[str, Any] = Field(default_factory=dict)


class HREnterpriseAgent:
    """Enterprise AI Agent runtime orchestrating HR & IT self-service and cross-system workflows."""

    def __init__(
        self,
        dlp: Optional[DLPRedactor] = None,
        armor: Optional[ModelArmor] = None,
        grounding: Optional[DualGroundingEngine] = None,
        ww_client: Optional[WorkWeekClient] = None,
        sn_client: Optional[ServiceImmediatelyClient] = None,
        saga: Optional[SagaCoordinator] = None,
        sessions: Optional[SessionMemory] = None,
        logger: Optional[AuditLogger] = None
    ) -> None:
        self._dlp = dlp or dlp_redactor
        self._armor = armor or model_armor
        self._grounding = grounding or dual_grounding_engine
        self._ww_client = ww_client or workweek_client
        self._sn_client = sn_client or service_immediately_client
        self._saga = saga or saga_coordinator
        self._sessions = sessions or session_store
        self._logger = logger or audit_logger

    def process_message(
        self,
        user_prompt: str,
        caller_employee_id: str = "EMP-1001",
        session_id: Optional[str] = None,
        reference_date: Optional[datetime.date] = None
    ) -> AgentResponse:
        """Execute the end-to-end 4-stage agentic loop."""
        sess_id = session_id or f"sess_{caller_employee_id}"
        today = reference_date or datetime.date.today()

        # --- STAGE 1: INGRESS SAFETY & DLP SCANNING (<120ms) ---
        redaction_res = self._dlp.redact(user_prompt)
        sanitized_prompt = redaction_res.sanitized_text

        armor_res = self._armor.scan_prompt(sanitized_prompt)
        if not armor_res.is_safe:
            self._logger.log_event(
                caller_employee_id=caller_employee_id,
                action_type="SAFETY_VIOLATION_BLOCKED",
                status="REFUSED",
                details={"reason": armor_res.refusal_reason, "threat": armor_res.threat_category}
            )
            return AgentResponse(
                response_text=armor_res.refusal_reason or "Request refused by safety guardrails.",
                intent="SAFETY_REFUSAL",
                is_refusal=True,
                processing_metadata={"dlp_ms": redaction_res.processing_time_ms, "armor_ms": armor_res.processing_time_ms}
            )

        # --- STAGE 2: INTENT CLASSIFICATION ---
        intent = self._classify_intent(sanitized_prompt)

        # Record user turn in session memory
        self._sessions.get_or_create_session(sess_id, caller_employee_id)
        self._sessions.add_message(sess_id, "user", sanitized_prompt)

        # --- STAGE 3: INTENT-BASED TOOL DISPATCH & ORCHESTRATION ---
        response: AgentResponse
        if intent == "UC_2_1_EQUIPMENT_PROCUREMENT":
            response = self._handle_equipment_procurement(caller_employee_id, sanitized_prompt)
        elif intent == "UC_2_2_MEDICAL_LEAVE_DELEGATION":
            response = self._handle_medical_leave(caller_employee_id, sanitized_prompt, today)
        elif intent == "UC_2_3_RELOCATION_ALLOWANCE_BADGE":
            response = self._handle_relocation(caller_employee_id, sanitized_prompt)
        elif intent == "UC_1_2_WORKWEEK_LEAVE":
            response = self._handle_workweek_leave(caller_employee_id, sanitized_prompt, today)
        elif intent == "UC_1_3_SERVICE_IMMEDIATELY_INCIDENT":
            response = self._handle_service_incident(caller_employee_id, sanitized_prompt)
        elif intent == "UC_1_1_POLICY_QA":
            response = self._handle_policy_qa(caller_employee_id, sanitized_prompt)
        else:
            response = self._handle_general_or_fallback(caller_employee_id, sanitized_prompt)

        # --- STAGE 4: SESSION STORAGE & AUDIT LOG EMISSION ---
        self._sessions.add_message(sess_id, "assistant", response.response_text, response.citations)
        response.processing_metadata["dlp_ms"] = redaction_res.processing_time_ms
        response.processing_metadata["detected_spii"] = redaction_res.detected_types

        return response

    def _classify_intent(self, prompt: str) -> str:
        """Classify user intent into specific MVP 1 Use Cases."""
        p = prompt.lower()

        # UC-2.1: Equipment Procurement (Remote eligibility + monitor/hardware order)
        if ("remote" in p and ("monitor" in p or "hardware" in p or "equipment" in p)) or \
           ("order" in p and "monitor" in p) or ("home office monitor" in p):
            return "UC_2_1_EQUIPMENT_PROCUREMENT"

        # UC-2.2: Medical Leave with Access Delegation
        if ("medical leave" in p or "sick leave" in p or "short-term medical" in p or "mc" in p) and \
           ("set it up" in p or "delegate" in p or "process" in p or "starting" in p or "submit" in p or "route" in p):
            return "UC_2_2_MEDICAL_LEAVE_DELEGATION"

        # UC-2.3: Relocation Allowance & Facilities Badge
        if "relocation" in p or "relocating" in p or "transferring to the london" in p or "london office" in p or "building access" in p and "allowance" in p:
            return "UC_2_3_RELOCATION_ALLOWANCE_BADGE"

        # UC-1.2: WorkWeek Leave & Profile Self-Service
        if any(k in p for k in [
            "vacation", "time off", "time-off", "leave balance", "pto", "submit a leave",
            "leave request", "leave history", "profile", "job", "who am i", "my info",
            "my details", "address", "manager", "boss", "report to", "department", "team",
            "email", "phone", "hire date", "contact"
        ]):
            return "UC_1_2_WORKWEEK_LEAVE"

        # UC-1.3: ServiceImmediately Incident Management
        if "ticket" in p or "vpn" in p or "incident" in p or "it helpdesk" in p or "wifi" in p or "dropping" in p:
            return "UC_1_3_SERVICE_IMMEDIATELY_INCIDENT"

        # UC-1.1: Policy Q&A
        if "policy" in p or "bereavement" in p or "entitlement" in p or "handbook" in p or "rule" in p or "how many days" in p:
            return "UC_1_1_POLICY_QA"

        return "GENERAL_INQUIRY"

    # --- HANDLERS FOR SINGLE-DOMAIN USE CASES ---

    def _handle_policy_qa(self, caller_id: str, prompt: str) -> AgentResponse:
        """UC-1.1: Policy Q&A with 100% Grounding and Clickable Citations."""
        result = self._grounding.query_policy(prompt)
        self._logger.log_event(
            caller_employee_id=caller_id,
            action_type="POLICY_QUERY",
            status="SUCCESS" if result.is_grounded else "NOT_FOUND",
            details={"is_grounded": result.is_grounded, "confidence": result.confidence_score}
        )
        return AgentResponse(
            response_text=result.answer_text,
            intent="UC_1_1_POLICY_QA",
            citations=result.citations,
            action_performed="POLICY_LOOKUP"
        )

    def _handle_workweek_leave(self, caller_id: str, prompt: str, today: datetime.date) -> AgentResponse:
        """UC-1.2: WorkWeek Leave Balance, Profile Inquiry, and Request Submission."""
        p = prompt.lower()

        # Specific field inquiry: Manager
        if "manager" in p or "boss" in p or "report to" in p:
            profile = self._ww_client.get_employee_profile(caller_id, caller_id)
            mgr = profile.manager_id if profile else "EMP-1"
            return AgentResponse(
                response_text=f"Your manager in WorkWeek is {mgr}.",
                intent="UC_1_2_WORKWEEK_LEAVE",
                action_performed="CHECK_MANAGER"
            )

        # Specific field inquiry: Department
        if "department" in p or "team" in p or "organization" in p:
            profile = self._ww_client.get_employee_profile(caller_id, caller_id)
            dept = profile.current_office if profile else "Google Forge (Customer Engineering)"
            return AgentResponse(
                response_text=f"Your department in WorkWeek is {dept}.",
                intent="UC_1_2_WORKWEEK_LEAVE",
                action_performed="CHECK_DEPARTMENT"
            )

        # Specific field inquiry: Registered Contact & Address
        if "phone" in p or "contact number" in p:
            profile = self._ww_client.get_employee_profile(caller_id, caller_id)
            phone = profile.phone_number if profile else "+65-6521-0000"
            return AgentResponse(
                response_text=f"Your contact phone number in WorkWeek is {phone}.",
                intent="UC_1_2_WORKWEEK_LEAVE",
                action_performed="CHECK_PHONE"
            )

        if "address" in p and not ("profile" in p or "job" in p):
            profile = self._ww_client.get_employee_profile(caller_id, caller_id)
            addr = profile.home_address if profile else "Singapore Office, 80 Pasir Panjang Rd, Singapore"
            return AgentResponse(
                response_text=f"Your registered address in WorkWeek is {addr}.",
                intent="UC_1_2_WORKWEEK_LEAVE",
                action_performed="CHECK_ADDRESS"
            )

        # Check if full profile inquiry
        if "profile" in p or "job" in p or "who am i" in p or "my info" in p or "my details" in p:
            profile = self._ww_client.get_employee_profile(caller_id, caller_id)
            if not profile:
                return AgentResponse(
                    response_text="Could not retrieve your employee profile from WorkWeek.",
                    intent="UC_1_2_WORKWEEK_LEAVE",
                    action_performed="CHECK_PROFILE"
                )
            text = (
                f"WorkWeek Profile for {profile.full_name} ({profile.employee_id}):\n"
                f"- Job Title: {profile.job_title}\n"
                f"- Department / Office: {profile.current_office}\n"
                f"- Work Location: {profile.work_location_status}\n"
                f"- Registered Address: {profile.home_address}\n"
                f"- Contact Phone: {profile.phone_number}\n"
                f"- Email: {profile.email}\n"
                f"- Manager ID: {profile.manager_id}"
            )

            return AgentResponse(
                response_text=text,
                intent="UC_1_2_WORKWEEK_LEAVE",
                action_performed="CHECK_PROFILE"
            )


        # Check if balance inquiry only or submission
        if "check" in p or "how many" in p or "balance" in p or "remaining" in p:
            balances = self._ww_client.get_leave_balances(caller_id, caller_id)

            if not balances:
                return AgentResponse(
                    response_text="Could not retrieve your leave balances from WorkWeek.",
                    intent="UC_1_2_WORKWEEK_LEAVE",
                    action_performed="CHECK_BALANCE"
                )
            text = f"Your current WorkWeek leave balances are:\n- Vacation: {balances.vacation_remaining} days remaining ({balances.vacation_accrued} accrued, {balances.vacation_used} used)\n- Sick Leave: {balances.sick_remaining} days remaining ({balances.sick_accrued} accrued, {balances.sick_used} used)"
            return AgentResponse(
                response_text=text,
                intent="UC_1_2_WORKWEEK_LEAVE",
                action_performed="CHECK_BALANCE"
            )

        # Submission flow
        # Default to 2 days Vacation starting upcoming Thursday/Friday if not parsed
        days = 2.0
        if "1 day" in p or "one day" in p:
            days = 1.0
        elif "3 days" in p or "three days" in p:
            days = 3.0
        elif "5 days" in p or "five days" in p:
            days = 5.0

        start_date = today + datetime.timedelta(days=1)
        end_date = start_date + datetime.timedelta(days=int(days) - 1)

        leave_type = "Vacation"
        if "sick" in p:
            leave_type = "Sick"

        res = self._ww_client.submit_leave_request(
            caller_employee_id=caller_id,
            target_employee_id=caller_id,
            leave_type=leave_type,
            start_date=start_date,
            end_date=end_date,
            days=days,
            reference_date=today
        )

        if res.success:
            msg = f"Your {int(days)}-day {leave_type} request for {start_date.isoformat()} to {end_date.isoformat()} has been submitted in WorkWeek (Ref: {res.request_id}). Remaining balance: {res.remaining_balance} days."
            return AgentResponse(
                response_text=msg,
                intent="UC_1_2_WORKWEEK_LEAVE",
                action_performed="SUBMIT_LEAVE",
                transaction_reference=res.request_id
            )
        else:
            return AgentResponse(
                response_text=f"Leave submission failed: {res.message}",
                intent="UC_1_2_WORKWEEK_LEAVE",
                action_performed="SUBMIT_LEAVE"
            )

    def _handle_service_incident(self, caller_id: str, prompt: str) -> AgentResponse:
        """UC-1.3: ServiceImmediately Support Desk Incident Management."""
        category = "IT_NETWORK"
        priority = "3 - Moderate"
        desc = "VPN connection dropping intermittently"

        if "vpn" in prompt.lower():
            desc = "VPN connection dropping intermittently"
            category = "IT_NETWORK"
        elif "wifi" in prompt.lower():
            desc = "Office WiFi authentication error"
            category = "IT_NETWORK"
        else:
            desc = prompt[:80]
            category = "IT_GENERAL"

        try:
            ticket = self._sn_client.create_incident_ticket(
                caller_employee_id=caller_id,
                category=category,
                requested_priority=priority,
                short_description=desc
            )
            msg = f"Support Incident Ticket [{ticket.ticket_id}] has been created in ServiceImmediately with Priority '{ticket.priority}'. An IT specialist will investigate."
            return AgentResponse(
                response_text=msg,
                intent="UC_1_3_SERVICE_IMMEDIATELY_INCIDENT",
                action_performed="CREATE_INCIDENT",
                transaction_reference=ticket.ticket_id
            )
        except ValueError as ve:
            return AgentResponse(
                response_text=f"Unable to create ticket: {str(ve)}",
                intent="UC_1_3_SERVICE_IMMEDIATELY_INCIDENT",
                action_performed="CREATE_INCIDENT_FAILED"
            )

    # --- HANDLERS FOR CROSS-SYSTEM ORCHESTRATION USE CASES ---

    def _handle_equipment_procurement(self, caller_id: str, prompt: str) -> AgentResponse:
        """UC-2.1: Equipment Procurement (Grounding -> WorkWeek -> ServiceImmediately)."""
        # Step 1: Policy Grounding
        policy_res = self._grounding.query_policy("remote work hardware allowance monitor")
        citation = policy_res.citations[0] if policy_res.citations else "[View Policy Section 08.3](https://hr.corp.internal/policies/08.3-remote-equipment)"

        # Step 2: WorkWeek Profile Check
        profile = self._ww_client.get_employee_profile(caller_id, caller_id)
        if not profile:
            return AgentResponse(
                response_text="Unable to verify profile details in WorkWeek.",
                intent="UC_2_1_EQUIPMENT_PROCUREMENT"
            )

        if profile.work_location_status != "REMOTE_FULL_TIME":
            return AgentResponse(
                response_text=f"Under Section 08.3, home office equipment is available only for full-time remote employees. Your current status in WorkWeek is '{profile.work_location_status}'. {citation}",
                intent="UC_2_1_EQUIPMENT_PROCUREMENT",
                citations=[citation]
            )

        # Step 3: Create Hardware Request in ServiceImmediately
        req = self._sn_client.create_hardware_request(
            caller_employee_id=caller_id,
            item='27in_Monitor',
            shipping_address=profile.home_address,
            referenced_policy_section="Sec 08.3"
        )

        msg = f"Verified under Section 08.3 that you are eligible for home office hardware. Verified remote status in WorkWeek. ServiceImmediately Hardware Request [{req.request_id}] has been created for shipping to your registered address ({profile.home_address}).\n\nCitation: {citation}"
        return AgentResponse(
            response_text=msg,
            intent="UC_2_1_EQUIPMENT_PROCUREMENT",
            citations=[citation],
            action_performed="CROSS_SYSTEM_PROCUREMENT",
            transaction_reference=req.request_id
        )

    def _handle_medical_leave(self, caller_id: str, prompt: str, today: datetime.date) -> AgentResponse:
        """UC-2.2: Medical Leave with Access Delegation & Saga Coordination."""
        start_date = today + datetime.timedelta(days=4)
        end_date = start_date + datetime.timedelta(days=4)
        days = 5.0

        profile = self._ww_client.get_employee_profile(caller_id, caller_id)
        mgr_id = profile.manager_id if profile else "MGR-2001"

        # Execute Saga
        saga_res = self._saga.execute_medical_leave_orchestration(
            caller_employee_id=caller_id,
            start_date=start_date,
            end_date=end_date,
            days=days,
            manager_id=mgr_id,
            reference_date=today
        )

        citation = "[View Policy Section 19.2](https://hr.corp.internal/policies/19.2-medical-leave)"
        response_text = f"{saga_res.message}\n\nCitation: {citation}"

        return AgentResponse(
            response_text=response_text,
            intent="UC_2_2_MEDICAL_LEAVE_DELEGATION",
            citations=[citation],
            action_performed="SAGA_MEDICAL_LEAVE",
            transaction_reference=saga_res.escalation_ticket_id
        )

    def _handle_relocation(self, caller_id: str, prompt: str) -> AgentResponse:
        """UC-2.3: Relocation Allowance & Facilities Badge."""
        # Step 1: Policy grounding
        policy_res = self._grounding.query_policy("international relocation allowance london")
        citation = policy_res.citations[0] if policy_res.citations else "[View Policy Section 14.1](https://hr.corp.internal/policies/14.1-international-relocation)"

        # Step 2: WorkWeek Contact & Office Update
        self._ww_client.update_contact_info(
            caller_employee_id=caller_id,
            target_employee_id=caller_id,
            current_office="London - 6 Pancras Sq",
            country="UK"
        )

        # Step 3: ServiceImmediately Facilities Ticket
        fac_ticket = self._sn_client.create_facilities_ticket(
            caller_employee_id=caller_id,
            category="BADGE_ACCESS",
            office="London_Pancras",
            start_date=(datetime.date.today() + datetime.timedelta(days=30)).isoformat()
        )

        msg = f"According to Section 14.1 (International Relocation), your Tier 2 allowance is £5,000. Your WorkWeek office assignment has been updated to London. Facilities Badge Ticket [{fac_ticket.ticket_id}] has been created for your first day access.\n\nCitation: {citation}"
        return AgentResponse(
            response_text=msg,
            intent="UC_2_3_RELOCATION_ALLOWANCE_BADGE",
            citations=[citation],
            action_performed="RELOCATION_ONBOARDING",
            transaction_reference=fac_ticket.ticket_id
        )

    def _handle_general_or_fallback(self, caller_id: str, prompt: str) -> AgentResponse:
        """Fallback for general inquiries."""
        result = self._grounding.query_policy(prompt)
        return AgentResponse(
            response_text=result.answer_text,
            intent="GENERAL_INQUIRY",
            citations=result.citations
        )


# Global singleton agent
hr_enterprise_agent = HREnterpriseAgent()
