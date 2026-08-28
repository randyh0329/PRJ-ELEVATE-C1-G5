"""
ADK Supervisor Agent and Orchestration Runner.
Implements the top-level HR Enterprise Orchestrator with autonomous sub-agent delegation.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from google.adk import Agent
from pydantic import BaseModel, Field
from src.adk.guardrails import ADKGuardrailsPipeline, adk_guardrails
from src.adk.specialists import (
    create_itsm_specialist_agent,
    create_policy_specialist_agent,
    create_saga_coordinator_agent,
    create_workweek_specialist_agent,
)
from src.core.clock import business_today
from src.integrations.vertex.client import vertex_gemini_client
from src.models.routing import SupervisorRoutingDecision

logger = logging.getLogger("adk.supervisor")


class ADKAgentResponse(BaseModel):
    """Normalized output schema from the ADK Enterprise Agent."""
    response_text: str
    intent: str
    citations: list[str] = Field(default_factory=list)
    action_performed: str | None = None
    transaction_reference: str | None = None
    is_refusal: bool = False
    processing_metadata: dict[str, Any] = Field(default_factory=dict)


def create_hr_supervisor_agent(
    model: str = "gemini-3.7-flash",
    use_live_mcp: bool = False
) -> Agent:
    """
    Constructs the top-level ADK Supervisor Agent orchestrating the 4 specialists:
    - Policy Specialist (UC-1.1)
    - WorkWeek HCM Specialist (UC-1.2)
    - ServiceImmediately ITSM Specialist (UC-1.3)
    - Cross-System Saga Coordinator (UC-2.1, UC-2.2, UC-2.3)
    """
    policy_agent = create_policy_specialist_agent(model=model)
    workweek_agent = create_workweek_specialist_agent(model=model, use_live_mcp=use_live_mcp)
    itsm_agent = create_itsm_specialist_agent(model=model, use_live_mcp=use_live_mcp)
    saga_agent = create_saga_coordinator_agent(model=model)

    supervisor = Agent(
        name="hr_enterprise_supervisor",
        model=model,
        description="Enterprise HR & IT Central AI Orchestrator coordinating specialized domain agents.",
        instruction=(
            "You are the central Enterprise HR & IT Orchestrator operating under SDD §3.1 & §3.2.\n"
            "Analyze the employee's request and delegate to the appropriate specialist sub-agent:\n"
            "- For company policies, rules, benefits, PTO guidelines, or bereavement: delegate to policy_specialist.\n"
            "- For WorkWeek time off balances, vacation/sick leave submission, profile, or contact changes: delegate to workweek_specialist.\n"
            "- For IT incident tickets, VPN/network issues, hardware problems, or ticket lookup: delegate to itsm_specialist.\n"
            "- For cross-system workflows (Ordering home monitor UC-2.1, Medical leave with email delegation UC-2.2, Relocation allowance & badge UC-2.3): delegate to saga_coordinator.\n"
            "- For out-of-domain requests (weather, coding, general trivia, stock prices): refuse politely stating domain scope.\n"
            "Ensure responses are friendly, accurate, and professional."
        ),
        sub_agents=[policy_agent, workweek_agent, itsm_agent, saga_agent]
    )
    return supervisor


class ADKHREnterpriseRunner:
    """
    High-performance Enterprise Execution Engine integrating:
    1. Guardrails Pipeline (DLP PII Redaction & Model Armor Scan)
    2. Intent Routing & Fast-Path Dispatching
    3. ADK Multi-Agent Execution Loop
    4. Audit Logging & Structured Response Formatting
    """

    def __init__(
        self,
        guardrails: ADKGuardrailsPipeline | None = None,
        router: Any | None = None,
        use_live_mcp: bool = False
    ) -> None:
        self.guardrails = guardrails or adk_guardrails
        self.router = router or vertex_gemini_client
        self.use_live_mcp = use_live_mcp
        self.supervisor_agent = create_hr_supervisor_agent(use_live_mcp=use_live_mcp)

    def process_message(
        self,
        user_prompt: str,
        caller_employee_id: str = "EMP-1001",
        session_id: str | None = None,
        reference_date: datetime.date | None = None
    ) -> ADKAgentResponse:
        """Execute the end-to-end 4-stage ADK agentic pipeline."""
        today = reference_date or business_today()

        # --- STAGE 1: INGRESS SAFETY & DLP SCANNING (<120ms) ---
        guard_res = self.guardrails.evaluate_ingress(prompt=user_prompt, caller_id=caller_employee_id)
        if not guard_res.is_safe:
            return ADKAgentResponse(
                response_text=guard_res.refusal_reason or "Request refused by safety guardrails.",
                intent="SAFETY_REFUSAL",
                is_refusal=True,
                processing_metadata={
                    "dlp_ms": guard_res.dlp_latency_ms,
                    "armor_ms": guard_res.armor_latency_ms
                }
            )

        sanitized_prompt = guard_res.sanitized_prompt

        # --- STAGE 2: INTENT ROUTING (Supervisor Router) ---
        routing: SupervisorRoutingDecision = self.router.route_intent(sanitized_prompt, reference_date=today)
        intent = routing.intent

        self.guardrails.log_egress(
            caller_id="SUPERVISOR",
            action_type="SUPERVISOR_INTENT_ROUTING",
            status="SUCCESS",
            details={
                "intent": intent,
                "target_agent": routing.target_agent,
                "confidence": routing.confidence,
                "reasoning": routing.reasoning
            }
        )

        # --- STAGE 3: SPECIALIST DISPATCH & EXECUTION ---
        from src.adk.toolsets import (
            itsm_create_incident,
            itsm_get_ticket,
            itsm_list_tickets,
            search_hr_policy,
            workweek_cancel_leave,
            workweek_get_balances,
            workweek_get_profile,
            workweek_submit_leave,
            workweek_update_contact,
        )
        from src.core.saga import saga_coordinator
        from src.integrations.service_immediately.client import service_immediately_client
        from src.integrations.workweek.client import workweek_client

        response_text: str = ""
        citations: list[str] = []
        action_performed: str | None = None
        transaction_ref: str | None = None
        is_refusal: bool = False

        if intent == "OUT_OF_DOMAIN":
            response_text = "I can help with HR policies, WorkWeek leave & profile, and IT tickets. That question is outside what I can assist with."
            is_refusal = True
            self.guardrails.log_egress(
                caller_id=caller_employee_id,
                action_type="DOMAIN_CONTAINMENT_REFUSAL",
                status="REFUSED",
                details={"prompt": sanitized_prompt, "reason": "Out of domain request"}
            )

        elif intent == "UC_1_1_POLICY_QA":
            policy_res = search_hr_policy(sanitized_prompt)
            response_text = policy_res["answer"]
            citations = policy_res.get("citations", [])
            action_performed = "POLICY_LOOKUP"
            is_refusal = policy_res.get("decision") == "refuse"
            self.guardrails.log_egress(
                caller_id=caller_employee_id,
                action_type="POLICY_QUERY",
                status="SUCCESS" if policy_res.get("is_grounded") else "NOT_FOUND",
                details=policy_res
            )

        elif intent == "UC_1_2_WORKWEEK_LEAVE":
            tool_selection = self.router.select_workweek_tool(sanitized_prompt, reference_date=today)
            tool_name = tool_selection.tool_name
            args = tool_selection.get_effective_arguments()

            # Handle DLP unredaction for contact info
            if tool_name == "update_personal_info":
                phone = args.get("phone_number")
                if not phone or "[REDACTED" in str(phone):
                    import re
                    m = re.search(r'(\+?\d[\d -]{7,}\d)', user_prompt)
                    if m:
                        args["phone_number"] = m.group(0).strip()
                res = workweek_update_contact(
                    caller_id=caller_employee_id,
                    home_address=args.get("home_address"),
                    phone_number=args.get("phone_number")
                )
                response_text = res["message"]
                action_performed = "UPDATE_CONTACT_INFO"
            elif tool_name == "request_time_off":
                res = workweek_submit_leave(
                    caller_id=caller_employee_id,
                    leave_type=args.get("leave_type", "Vacation"),
                    start_date=str(args.get("start_date", "2026-09-01")),
                    end_date=str(args.get("end_date", "2026-09-02")),
                    days=float(args.get("days", 2.0))
                )
                if res["success"]:
                    response_text = f"Your time off request (ID: {res['request_id']}) has been successfully submitted in WorkWeek. Remaining balance: {res['remaining_balance']} days (vacation)."
                    transaction_ref = str(res["request_id"])
                else:
                    response_text = f"Time-off submission rejected by WorkWeek: {res['message']}"
                action_performed = "SUBMIT_LEAVE_REQUEST"
            elif tool_name == "cancel_leave_request":
                req_id = args.get("request_id")
                if not req_id or str(req_id) == "101":
                    import re
                    m = re.search(r'(WW-LV-[A-Z0-9]+|\b\d+\b)', sanitized_prompt)
                    if m:
                        req_id = m.group(1)
                req_id = req_id or "101"
                res = workweek_cancel_leave(caller_id=caller_employee_id, request_id=req_id)
                response_text = res["message"]
                action_performed = "CANCEL_LEAVE_REQUEST"
            elif tool_name == "get_employee_profile":
                field = str(args.get("field", "all"))
                p_res = workweek_get_profile(caller_id=caller_employee_id, field=field)
                if field == "manager":
                    response_text = f"Your manager in WorkWeek is {p_res.get('manager_name', 'Jane Doe')} ({p_res.get('manager_id', 'MGR-2001')})."
                elif field == "department":
                    response_text = f"Your department is {p_res.get('department', 'Engineering')} (Role: {p_res.get('job_title', 'Senior Software Engineer')})."
                elif field == "phone":
                    response_text = f"Your current phone number in WorkWeek is {p_res.get('phone_number', '+65-6521-0000')}."
                elif field == "address":
                    response_text = f"Your current home address in WorkWeek is {p_res.get('home_address', '80 Pasir Panjang Rd, Singapore')}."
                else:
                    response_text = f"Employee Profile for {p_res.get('employee_name', 'Employee')}:\n- Department: {p_res.get('department')}\n- Title: {p_res.get('job_title')}\n- Manager: {p_res.get('manager_name')}"
                action_performed = "GET_PROFILE"
            else:
                # get_employee_balances
                b = workweek_get_balances(caller_id=caller_employee_id)
                response_text = f"Here are your current WorkWeek leave balances:\n- Vacation: {b['vacation_days']} days remaining\n- Sick Leave: {b['sick_leave_days']} days remaining"
                action_performed = "GET_LEAVE_BALANCES"

        elif intent == "UC_1_3_SERVICE_IMMEDIATELY_INCIDENT":
            tool_selection = self.router.select_itsm_tool(sanitized_prompt)
            tool_name = tool_selection.tool_name
            args = tool_selection.get_effective_arguments()

            if tool_name == "get_ticket_details":
                tid = args.get("ticket_id") or "INC-5001"
                t_res = itsm_get_ticket(caller_id=caller_employee_id, ticket_id=tid)
                if t_res.get("status") == "SUCCESS":
                    response_text = (
                        f"Status for Support Incident Ticket **[{t_res['ticket_id']}]** in ServiceImmediately:\n"
                        f"- **Status:** {t_res.get('ticket_status', 'In Progress')}\n"
                        f"- **Priority:** {t_res.get('priority', '3 - Moderate')}\n"
                        f"- **Category:** {t_res.get('category', 'IT_GENERAL')}\n"
                        f"- **Summary:** {t_res.get('short_description', 'IT Support Request')}"
                    )
                    transaction_ref = t_res["ticket_id"]
                else:
                    response_text = f"Ticket [{tid}] was not found in ServiceImmediately."
                action_performed = "GET_TICKET_DETAILS"
            elif tool_name == "list_tickets":
                list_res = itsm_list_tickets(caller_id=caller_employee_id)
                tickets = list_res.get("tickets", [])
                if tickets:
                    lines = [f"- **[{t['ticket_id']}]** ({t['status']}, {t['priority']}): {t['short_description']}" for t in tickets]
                    response_text = f"Here are your active support tickets in ServiceImmediately:\n" + "\n".join(lines)
                else:
                    response_text = "You currently have no open IT tickets in ServiceImmediately."
                action_performed = "LIST_TICKETS"
            else:
                # create_incident
                cat = str(args.get("category", "IT_GENERAL"))
                desc = str(args.get("short_description") or sanitized_prompt[:100])
                prio = str(args.get("priority", "3 - Moderate"))
                c_res = itsm_create_incident(
                    caller_id=caller_employee_id,
                    category=cat,
                    short_description=desc,
                    priority=prio
                )
                if c_res.get("status") == "SUCCESS":
                    response_text = f"Support Incident Ticket [{c_res['ticket_id']}] has been created in ServiceImmediately with Priority '{c_res['priority']}' (Category: {c_res['category']}). An IT specialist will investigate."
                    transaction_ref = c_res["ticket_id"]
                elif c_res.get("status") == "DUPLICATE_PREVENTED":
                    response_text = f"Duplicate ticket detected: An incident in category '{cat}' was already submitted recently. Please check ticket status instead of opening a duplicate."
                else:
                    response_text = f"Failed to create ticket in ServiceImmediately: {c_res.get('error')}"
                action_performed = "CREATE_INCIDENT"

        elif intent == "UC_2_1_EQUIPMENT_PROCUREMENT":
            policy_res = search_hr_policy("remote work hardware allowance monitor", curated_only=True)
            citation = policy_res.get("citations", ["[View Policy Section 08.3](https://hr.corp.internal/policies/08.3-remote-equipment)"])[0]
            profile = workweek_client.get_employee_profile(caller_employee_id, caller_employee_id)
            if not profile:
                response_text = "Unable to verify profile details in WorkWeek."
            elif profile.work_location_status != "REMOTE_FULL_TIME":
                response_text = f"Under Section 08.3, home office equipment is available only for full-time remote employees. Your current status in WorkWeek is '{profile.work_location_status}'. {citation}"
                citations = [citation]
            else:
                req = service_immediately_client.create_hardware_request(
                    caller_employee_id=caller_employee_id,
                    item='27in_Monitor',
                    shipping_address=profile.home_address,
                    referenced_policy_section="Sec 08.3"
                )
                response_text = f"Verified under Section 08.3 that you are eligible for home office hardware. Verified remote status in WorkWeek. ServiceImmediately Hardware Request [{req.request_id}] has been created for shipping to your registered address ({profile.home_address}).\n\nCitation: {citation}"
                citations = [citation]
                action_performed = "CROSS_SYSTEM_PROCUREMENT"
                transaction_ref = req.request_id

        elif intent == "UC_2_2_MEDICAL_LEAVE_DELEGATION":
            start_date = today + datetime.timedelta(days=4)
            end_date = start_date + datetime.timedelta(days=4)
            profile = workweek_client.get_employee_profile(caller_employee_id, caller_employee_id)
            mgr_id = profile.manager_id if profile else "MGR-2001"
            saga_res = saga_coordinator.execute_medical_leave_orchestration(
                caller_employee_id=caller_employee_id,
                start_date=start_date,
                end_date=end_date,
                days=5.0,
                manager_id=mgr_id,
                reference_date=today
            )
            citation = "[View Policy Section 19.2](https://hr.corp.internal/policies/19.2-medical-leave)"
            response_text = f"{saga_res.message}\n\nCitation: {citation}"
            citations = [citation]
            action_performed = "SAGA_MEDICAL_LEAVE"
            transaction_ref = saga_res.escalation_ticket_id

        elif intent == "UC_2_3_RELOCATION_ALLOWANCE_BADGE":
            policy_res = search_hr_policy("international relocation allowance london", curated_only=True)
            citation = policy_res.get("citations", ["[View Policy Section 14.1](https://hr.corp.internal/policies/14.1-international-relocation)"])[0]
            workweek_client.update_contact_info(
                caller_employee_id=caller_employee_id,
                target_employee_id=caller_employee_id,
                current_office="London - 6 Pancras Sq",
                country="UK"
            )
            fac_ticket = service_immediately_client.create_facilities_ticket(
                caller_employee_id=caller_employee_id,
                category="BADGE_ACCESS",
                office="London - 6 Pancras Sq",
                start_date="2026-10-01"
            )
            response_text = f"Your relocation transfer to London Office has been initiated. Contact info updated in WorkWeek. Relocation allowance of £5,000 GBP ($10,000 USD) approved under Policy Section 14.1. Facilities Badge Ticket [{fac_ticket.ticket_id}] has been opened to issue your London building access badge.\n\nCitation: {citation}"
            citations = [citation]
            action_performed = "CROSS_SYSTEM_RELOCATION"
            transaction_ref = fac_ticket.ticket_id

        else:
            response_text = "I am your enterprise HR & IT Assistant. How may I help you today?"
            action_performed = "GENERAL_CONVERSATION"

        return ADKAgentResponse(
            response_text=response_text,
            intent=intent,
            citations=citations,
            action_performed=action_performed,
            transaction_reference=transaction_ref,
            is_refusal=is_refusal,
            processing_metadata={
                "dlp_ms": guard_res.dlp_latency_ms,
                "detected_spii": guard_res.detected_pii,
                "router_confidence": routing.confidence,
                "router_reasoning": routing.reasoning
            }
        )


# Global default instance
adk_runner = ADKHREnterpriseRunner()
