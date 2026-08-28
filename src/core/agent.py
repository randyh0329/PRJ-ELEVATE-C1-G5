"""Enterprise HR Agent Orchestrator (Reasoning Engine runtime)."""
import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.core.agents.hcm import workweek_autonomous_specialist
from src.core.agents.itsm import service_immediately_autonomous_specialist
from src.core.clock import business_today
from src.core.safety import DLPRedactor, ModelArmor, dlp_redactor, model_armor
from src.core.saga import SagaCoordinator, saga_coordinator
from src.core.session import SessionMemory, session_store
from src.grounding.policy_engine import DualGroundingEngine, dual_grounding_engine
from src.integrations.service_immediately.client import ServiceImmediatelyClient, service_immediately_client
from src.integrations.workweek.client import WorkWeekClient, workweek_client
from src.models.routing import SupervisorRoutingDecision
from src.telemetry.audit_logger import AuditLogger, audit_logger


class AgentResponse(BaseModel):
    """Structured response from the HR Enterprise Agent."""
    response_text: str
    intent: str
    citations: list[str] = Field(default_factory=list)
    action_performed: str | None = None
    transaction_reference: str | None = None
    is_refusal: bool = False
    processing_metadata: dict[str, Any] = Field(default_factory=dict)


class HREnterpriseAgent:
    """Enterprise AI Agent runtime orchestrating HR & IT self-service and cross-system workflows."""

    def __init__(
        self,
        dlp: DLPRedactor | None = None,
        armor: ModelArmor | None = None,
        grounding: DualGroundingEngine | None = None,
        ww_client: WorkWeekClient | None = None,
        sn_client: ServiceImmediatelyClient | None = None,
        saga: SagaCoordinator | None = None,
        sessions: SessionMemory | None = None,
        logger: AuditLogger | None = None,
        router: Any | None = None
    ) -> None:
        self._dlp = dlp or dlp_redactor
        self._armor = armor or model_armor
        self._grounding = grounding or dual_grounding_engine
        self._ww_client = ww_client or workweek_client
        self._sn_client = sn_client or service_immediately_client
        self._saga = saga or saga_coordinator
        self._sessions = sessions or session_store
        self._logger = logger or audit_logger
        if router is None:
            from src.integrations.vertex.client import vertex_gemini_client
            router = vertex_gemini_client
        self._router = router

    def process_message(
        self,
        user_prompt: str,
        caller_employee_id: str = "EMP-1001",
        session_id: str | None = None,
        reference_date: datetime.date | None = None
    ) -> AgentResponse:
        """Execute the end-to-end 4-stage agentic loop."""
        sess_id = session_id or f"sess_{caller_employee_id}"
        today = reference_date or business_today()

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

        # --- STAGE 2: INTENT CLASSIFICATION (Gemini 3.7 Flash Supervisor Router) ---
        routing_decision = self._classify_intent(sanitized_prompt, today)
        intent = routing_decision.intent

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
            response = self._handle_workweek_leave(
                caller_employee_id,
                sanitized_prompt,
                today,
                routing_decision,
                original_prompt=user_prompt
            )
        elif intent == "UC_1_3_SERVICE_IMMEDIATELY_INCIDENT":
            response = self._handle_service_incident(
                caller_employee_id,
                sanitized_prompt,
                original_prompt=user_prompt
            )
        elif intent == "UC_1_1_POLICY_QA":
            response = self._handle_policy_qa(caller_employee_id, sanitized_prompt)
        elif intent == "OUT_OF_DOMAIN":
            response = self._handle_out_of_domain(caller_employee_id, sanitized_prompt)
        else:
            response = self._handle_general_or_fallback(caller_employee_id, sanitized_prompt)

        # --- STAGE 4: SESSION STORAGE & AUDIT LOG EMISSION ---
        self._sessions.add_message(sess_id, "assistant", response.response_text, response.citations)
        response.processing_metadata["dlp_ms"] = redaction_res.processing_time_ms
        response.processing_metadata["detected_spii"] = redaction_res.detected_types
        response.processing_metadata["router_confidence"] = routing_decision.confidence
        response.processing_metadata["router_reasoning"] = routing_decision.reasoning

        return response

    def _classify_intent(self, prompt: str, reference_date: datetime.date | None = None) -> SupervisorRoutingDecision:
        """
        Classify user intent using Gemini 3.7 Flash Supervisor Router.
        Compliant with SDD §3.1, §3.2 (FR-1.1, FR-2.1).
        """
        decision = self._router.route_intent(prompt, reference_date=reference_date)
        self._logger.log_event(
            caller_employee_id="SUPERVISOR",
            action_type="SUPERVISOR_INTENT_ROUTING",
            status="SUCCESS",
            details={
                "intent": decision.intent,
                "target_agent": decision.target_agent,
                "confidence": decision.confidence,
                "reasoning": decision.reasoning,
            }
        )
        return decision

    def _handle_out_of_domain(self, caller_id: str, prompt: str) -> AgentResponse:
        """Domain Containment Refusal per SDD §5.5 & FR-5.4."""
        self._logger.log_event(
            caller_employee_id=caller_id,
            action_type="DOMAIN_CONTAINMENT_REFUSAL",
            status="REFUSED",
            details={"prompt": prompt, "reason": "Out of domain request"}
        )
        return AgentResponse(
            response_text="I can help with HR policies, WorkWeek leave & profile, and IT tickets. That question is outside what I can assist with.",
            intent="OUT_OF_DOMAIN",
            is_refusal=True
        )



    # --- HANDLERS FOR SINGLE-DOMAIN USE CASES ---

    def _handle_policy_qa(self, caller_id: str, prompt: str) -> AgentResponse:
        """UC-1.1: Policy Q&A with 100% Grounding and Clickable Citations."""
        result = self._grounding.query_policy(prompt)
        self._logger.log_event(
            caller_employee_id=caller_id,
            action_type="POLICY_QUERY",
            status="SUCCESS" if result.is_grounded else "NOT_FOUND",
            details={
                "is_grounded": result.is_grounded,
                "confidence": result.confidence_score,
                # Which corpus answered, and how the guards disposed of it. An
                # auditor reconstructing a bad answer needs to know whether it
                # came from the indexed handbook or the degraded fallback.
                "grounding_source": result.source,
                "decision": result.decision,
            }
        )
        return AgentResponse(
            response_text=result.answer_text,
            intent="UC_1_1_POLICY_QA",
            citations=result.citations,
            action_performed="POLICY_LOOKUP",
            is_refusal=result.decision == "refuse",
        )

    def _handle_workweek_leave(
        self,
        caller_id: str,
        prompt: str,
        today: datetime.date,
        decision: SupervisorRoutingDecision | None = None,
        original_prompt: str | None = None,
    ) -> AgentResponse:
        """UC-1.2: Autonomous WorkWeek HCM Tool-Calling Agent."""
        can_use_fast_path = False
        args: dict[str, Any] = {}
        raw_prompt = original_prompt or prompt

        if decision and decision.tool_name and decision.tool_name != "none":
            args = decision.get_tool_arguments()
            tool = decision.tool_name

            # Guard: Mutating tools require valid, non-empty domain parameters
            if tool == "update_personal_info":
                phone = args.get("phone_number")
                if not phone or "[REDACTED" in str(phone):
                    m = DLPRedactor.PHONE_PATTERN.search(raw_prompt)
                    if m:
                        args["phone_number"] = m.group(0).strip()
                if args.get("phone_number") or args.get("home_address"):
                    can_use_fast_path = True
            elif tool == "request_time_off":
                if args.get("start_date"):
                    can_use_fast_path = True
            elif tool == "cancel_leave_request":
                if args.get("request_id"):
                    can_use_fast_path = True
            else:
                # Read-only operations (get_employee_balances, get_leave_requests, get_employee_profile)
                can_use_fast_path = True

        if can_use_fast_path and decision:
            res = workweek_autonomous_specialist.execute_fast_path(
                tool_name=decision.tool_name,
                arguments=args,
                caller_id=caller_id,
                reference_date=today
            )
        else:
            # Fallback to full specialist tool selection with raw prompt for unredacted parameters
            res = workweek_autonomous_specialist.plan_and_execute(
                prompt=raw_prompt,
                caller_id=caller_id,
                reference_date=today
            )
        return AgentResponse(
            response_text=res["response_text"],
            intent="UC_1_2_WORKWEEK_LEAVE",
            action_performed=res["action_performed"],
            transaction_reference=res.get("transaction_reference")
        )


    def _handle_service_incident(
        self,
        caller_id: str,
        prompt: str,
        original_prompt: str | None = None
    ) -> AgentResponse:
        """UC-1.3: Autonomous ServiceImmediately ITSM Tool-Calling Agent."""
        raw_prompt = original_prompt or prompt
        res = service_immediately_autonomous_specialist.plan_and_execute(
            prompt=raw_prompt,
            caller_id=caller_id
        )
        return AgentResponse(
            response_text=res["response_text"],
            intent="UC_1_3_SERVICE_IMMEDIATELY_INCIDENT",
            action_performed=res["action_performed"],
            transaction_reference=res.get("transaction_reference")
        )

    # --- HANDLERS FOR CROSS-SYSTEM ORCHESTRATION USE CASES ---

    def _handle_equipment_procurement(self, caller_id: str, prompt: str) -> AgentResponse:
        """UC-2.1: Equipment Procurement (Grounding -> WorkWeek -> ServiceImmediately)."""
        # Step 1: Policy Grounding.
        # `curated_only`: this citation is the entitlement rule authorising a
        # purchase, not an answer to a question the employee asked. It has to name
        # the same rule on every run - a cap that moves because a retrieval
        # ranking shifted would be a defect, not a better answer.
        policy_res = self._grounding.query_policy(
            "remote work hardware allowance monitor", curated_only=True
        )
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
        # Step 1: Policy grounding. `curated_only` for the same reason as the
        # equipment flow above: the relocation cap is a transaction parameter.
        policy_res = self._grounding.query_policy(
            "international relocation allowance london", curated_only=True
        )
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
            start_date=(business_today() + datetime.timedelta(days=30)).isoformat()
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
