"""
WorkWeek HCM Specialist Agent.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.2, §4.1, §5.1 (FR-3.1 - FR-3.4).
Model: Gemini 3.7 Flash (Pinned).
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from src.core.clock import business_today
from src.core.leave_request import Clarification, parse_leave_date, resolve_leave_span
from src.core.state import AgentState
from src.integrations.workweek.client import WorkWeekClient, workweek_client
from src.security.token_minter import CompositeTokenMinter

logger = logging.getLogger("agents.hcm")


# ==============================================================================
# WorkWeek FastMCP Tool Declarations (OpenAPI 3.0 / JSON-RPC 2.0 Schemas)
# ==============================================================================
WORKWEEK_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_employee_balances",
        "description": "Fetch current remaining, accrued, and used vacation and sick leave balances for the authenticated employee.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_leave_requests",
        "description": "Retrieve the history of all submitted, pending, or approved leave requests/time-off records for the authenticated employee.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "request_time_off",
        "description": "Submit a new time-off / leave request for the authenticated employee.",
        "parameters": {
            "type": "object",
            "required": ["start_date", "end_date", "days"],
            "properties": {
                "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                "leave_type": {"type": "string", "enum": ["Vacation", "Sick"], "description": "Type of leave (default: Vacation)"},
                "days": {"type": "number", "description": "Number of working days requested"},
                "reason": {"type": "string", "description": "Optional reason or note"}
            }
        },
    },
    {
        "name": "cancel_leave_request",
        "description": "Cancel a previously submitted or pending leave request and refund the days back to the employee.",
        "parameters": {
            "type": "object",
            "required": ["request_id"],
            "properties": {
                "request_id": {"type": "integer", "description": "The numeric ID of the leave request to cancel (e.g. 2094)"}
            }
        },
    },
    {
        "name": "update_personal_info",
        "description": "Update personal contact details such as home address and/or phone number in the employee record.",
        "parameters": {
            "type": "object",
            "properties": {
                "home_address": {"type": "string", "description": "The new physical home address"},
                "phone_number": {"type": "string", "description": "The new contact telephone number"}
            }
        },
    },
    {
        "name": "get_employee_profile",
        "description": "Fetch core employee profile details including job title, department, manager, work location, home address, and contact information.",
        "parameters": {
            "type": "object",
            "properties": {
                "field": {"type": "string", "description": "Specific field: 'manager', 'department', 'job_title', 'address', 'phone', 'all'"}
            }
        },
    }
]


class WorkWeekAutonomousSpecialist:
    """
    Autonomous WorkWeek Specialist that executes LLM Tool Calling over FastMCP.
    Enforces Server-Side Subject Binding (SDD §4.1) so employee_id cannot be spoofed.
    """

    def __init__(
        self,
        client: WorkWeekClient | None = None,
        llm_client: Any | None = None
    ):
        self.client = client or workweek_client
        if llm_client is None:
            from src.integrations.vertex.client import vertex_gemini_client
            llm_client = vertex_gemini_client
        self._llm = llm_client

    def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        caller_id: str,
        reference_date: datetime.date | None = None
    ) -> dict[str, Any]:
        """
        Executes a registered WorkWeek tool with strict Subject Isolation.
        """
        ref_date = reference_date or business_today()
        logger.info("[WorkWeekAutonomous] Executing tool '%s' for caller '%s' with args: %s", tool_name, caller_id, arguments)

        try:
            # 1. get_employee_balances
            if tool_name == "get_employee_balances":
                balances = self.client.get_leave_balances(caller_employee_id=caller_id, target_employee_id=caller_id)
                if not balances:
                    return {"status": "ERROR", "message": "Could not fetch leave balances from WorkWeek."}
                return {
                    "status": "SUCCESS",
                    "vacation_remaining": balances.vacation_remaining,
                    "vacation_accrued": balances.vacation_accrued,
                    "vacation_used": balances.vacation_used,
                    "sick_remaining": balances.sick_remaining,
                    "sick_accrued": balances.sick_accrued,
                    "sick_used": balances.sick_used,
                }

            # 2. get_leave_requests
            elif tool_name == "get_leave_requests":
                requests = self.client.get_leave_requests(caller_employee_id=caller_id, target_employee_id=caller_id)
                return {"status": "SUCCESS", "requests": requests, "count": len(requests)}

            # 3. request_time_off
            elif tool_name == "request_time_off":
                raw_type = str(arguments.get("leave_type", "Vacation")).lower()
                leave_type = "Sick" if any(k in raw_type for k in ["sick", "병가", "medical"]) else "Vacation"

                # Nothing here invents a missing parameter.
                #
                # This branch used to default `days` to 1.0, `start_date` to
                # tomorrow and `end_date` to the start date. Between them those
                # three defaults could manufacture an entire leave request out of
                # an empty argument dict and write it to the HR system of record:
                # asked for "999 days off from tomorrow", the extractor returned
                # no duration at all and the employee was told "your vacation
                # request for 1.0 days from 2026-08-29 to 2026-08-29 has been
                # submitted". The 999 never reached the balance guardrail, which
                # would have refused it.
                #
                # A request we cannot read is not a one-day request. It is a
                # question - see `src.core.leave_request`, shared with the ADK
                # runtime so the two cannot drift back apart.
                resolved = resolve_leave_span(
                    start_date=arguments.get("start_date"),
                    end_date=arguments.get("end_date"),
                    days=arguments.get("days"),
                    today=ref_date,
                )
                if isinstance(resolved, Clarification):
                    return self._clarify(resolved.question)

                resp = self.client.submit_leave_request(
                    caller_employee_id=caller_id,
                    target_employee_id=caller_id,
                    leave_type=leave_type,
                    start_date=resolved.start_date,
                    end_date=resolved.end_date,
                    days=resolved.days,
                    reference_date=ref_date
                )
                return {
                    "status": "SUCCESS" if resp.success else "FAILED",
                    "request_id": resp.request_id,
                    "message": resp.message,
                    "remaining_balance": resp.remaining_balance,
                    "start_date": resolved.start_date.isoformat(),
                    "end_date": resolved.end_date.isoformat(),
                    "days": resolved.days,
                    "leave_type": leave_type
                }

            # 4. cancel_leave_request
            elif tool_name == "cancel_leave_request":
                req_id = str(arguments.get("request_id", "")).strip()
                if not req_id:
                    return {"status": "ERROR", "message": "Missing request_id for leave cancellation."}
                success = self.client.cancel_leave_request(caller_employee_id=caller_id, request_id=req_id)
                return {
                    "status": "SUCCESS" if success else "FAILED",
                    "request_id": req_id,
                    "message": f"Leave request {req_id} cancelled and days refunded." if success else f"Failed to cancel leave request {req_id}."
                }

            # 5. update_personal_info
            elif tool_name == "update_personal_info":
                addr = arguments.get("home_address")
                phone = arguments.get("phone_number")
                resp = self.client.update_contact_info(
                    caller_employee_id=caller_id,
                    target_employee_id=caller_id,
                    home_address=addr,
                    phone_number=phone
                )
                return {
                    "status": "SUCCESS" if resp.success else "FAILED",
                    "updated_fields": resp.updated_fields,
                    "message": resp.message
                }

            # 6. get_employee_profile
            elif tool_name == "get_employee_profile":
                profile = self.client.get_employee_profile(caller_employee_id=caller_id, target_employee_id=caller_id)
                if not profile:
                    return {"status": "ERROR", "message": "Profile not found."}
                return {
                    "status": "SUCCESS",
                    "employee_id": profile.employee_id,
                    "full_name": profile.full_name,
                    "job_title": profile.job_title,
                    "department": profile.current_office,
                    "manager_id": profile.manager_id,
                    "work_location_status": profile.work_location_status,
                    "home_address": profile.home_address,
                    "phone_number": profile.phone_number,
                    "email": profile.email,
                }

            else:
                return {"status": "ERROR", "message": f"Unknown tool '{tool_name}'."}
        except Exception as e:
            logger.error("[WorkWeekAutonomous] Tool execution '%s' failed: %s", tool_name, e)
            return {"status": "ERROR", "message": str(e)}

    @staticmethod
    def _clarify(question: str) -> dict[str, Any]:
        """Stop and ask, having written nothing.

        The alternative this replaces is guessing a parameter and submitting, and
        leave is a write to the system of record: an employee who is told their
        request was submitted stops thinking about it. Being asked one more
        question costs a turn. Being booked for the wrong dates costs a day off
        that has to be discovered and unwound.
        """
        logger.info("[WorkWeekAutonomous] Leave request underspecified; asking: %s", question)
        return {"status": "NEEDS_CLARIFICATION", "message": question}

    _parse_date = staticmethod(parse_leave_date)
    """An ISO date, or `None` when the model supplied something unusable.

    Kept as a name on the specialist because callers and tests reach for it here;
    the implementation lives in `src.core.leave_request` alongside the rest of
    the argument handling it belongs to.
    """

    def plan_and_execute(
        self,
        prompt: str,
        caller_id: str,
        reference_date: datetime.date | None = None
    ) -> dict[str, Any]:
        """
        Autonomous Agentic Plan & Execute loop for WorkWeek HCM.
        Uses Gemini 3.7 Flash Function Calling to select the FastMCP tool and extract arguments,
        executes the tool against WorkWeek FastMCP, and returns the response.
        """
        ref_date = reference_date or business_today()

        # Step 1: Gemini Function Calling for FastMCP Tool Selection & Argument Extraction
        selection = self._llm.select_workweek_tool(prompt, reference_date=ref_date)
        tool_name = selection.tool_name
        args = selection.get_effective_arguments()

        if tool_name == "none":
            return {
                "response_text": selection.direct_response or "How can I help you with your WorkWeek self-service today?",
                "action_performed": "CONVERSATION",
                "tool_called": "none",
                "tool_result": {},
                "transaction_reference": None
            }

        return self.execute_fast_path(tool_name, args, caller_id, ref_date)

    def execute_fast_path(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        caller_id: str,
        reference_date: datetime.date | None = None
    ) -> dict[str, Any]:
        """Directly executes WorkWeek tool without a redundant 2nd LLM round-trip."""
        ref_date = reference_date or business_today()
        tool_res = self.execute_tool(tool_name, arguments, caller_id, ref_date)
        if tool_res.get("status") == "ERROR":
            return {
                "response_text": f"❌ WorkWeek FastMCP communication error: {tool_res.get('message')}. Please verify your FastMCP token.",
                "action_performed": "ERROR",
                "tool_called": tool_name,
                "tool_result": tool_res,
                "transaction_reference": None
            }
        return self._format_tool_response(tool_name, arguments, tool_res)

    def _format_tool_response(
        self,
        tool_name: str,
        args: dict[str, Any],
        tool_res: dict[str, Any]
    ) -> dict[str, Any]:
        """Format domain response based on executed tool."""
        if tool_name == "cancel_leave_request":
            req_id = args.get("request_id") or tool_res.get("request_id", "")
            if tool_res.get("status") == "SUCCESS":
                text = f"Leave request #{req_id} has been cancelled successfully, and the days have been refunded to your leave balance."
            else:
                text = f"Failed to cancel leave request #{req_id}: {tool_res.get('message', 'Unknown error')}."
            return {
                "response_text": text,
                "action_performed": "CANCEL_LEAVE",
                "tool_called": "cancel_leave_request",
                "tool_result": tool_res,
                "transaction_reference": f"CANCEL-{req_id}" if req_id else None
            }

        elif tool_name == "get_leave_requests":
            requests = tool_res.get("requests", [])
            if not requests:
                text = "You currently have no leave requests registered in WorkWeek."
            else:
                lines = [
                    f"- Request #{r.get('request_id')}: {r.get('start_date')} to {r.get('end_date')} ({r.get('days')} days, {r.get('leave_type')})"
                    for r in requests
                ]
                text = f"Current registered WorkWeek leave requests ({len(requests)} total):\n" + "\n".join(lines)
            return {
                "response_text": text,
                "action_performed": "LIST_LEAVE_REQUESTS",
                "tool_called": "get_leave_requests",
                "tool_result": tool_res,
                "transaction_reference": None
            }

        elif tool_name == "update_personal_info":
            if tool_res.get("status") == "SUCCESS":
                addr = args.get("home_address")
                phone = args.get("phone_number")
                parts = []
                if addr:
                    parts.append(f"address: '{addr}'")
                if phone:
                    parts.append(f"phone: '{phone}'")
                desc = ", ".join(parts) if parts else "contact details"
                text = f"Your personal contact information has been updated successfully in WorkWeek ({desc})."
            else:
                text = f"Failed to update personal contact info in WorkWeek: {tool_res.get('message')}"
            return {
                "response_text": text,
                "action_performed": "UPDATE_CONTACT",
                "tool_called": "update_personal_info",
                "tool_result": tool_res,
                "transaction_reference": None
            }

        elif tool_name == "get_employee_profile":
            field = args.get("field", "all")
            if field == "manager":
                text = f"Your manager in WorkWeek is {tool_res.get('manager_id', 'N/A')}."
                action = "CHECK_MANAGER"
            elif field == "department":
                text = f"Your department in WorkWeek is {tool_res.get('department', 'N/A')}."
                action = "CHECK_DEPARTMENT"
            elif field == "phone":
                text = f"Your contact phone number in WorkWeek is {tool_res.get('phone_number', 'N/A')}."
                action = "CHECK_PHONE"
            elif field == "address":
                text = f"Your registered address in WorkWeek is {tool_res.get('home_address', 'N/A')}."
                action = "CHECK_ADDRESS"
            else:
                text = (
                    f"WorkWeek Profile for {tool_res.get('full_name')} ({tool_res.get('employee_id')}):\n"
                    f"- Job Title: {tool_res.get('job_title')}\n"
                    f"- Department / Office: {tool_res.get('department')}\n"
                    f"- Work Location: {tool_res.get('work_location_status')}\n"
                    f"- Registered Address: {tool_res.get('home_address')}\n"
                    f"- Contact Phone: {tool_res.get('phone_number')}\n"
                    f"- Email: {tool_res.get('email')}\n"
                    f"- Manager ID: {tool_res.get('manager_id')}"
                )
                action = "CHECK_PROFILE"
            return {
                "response_text": text,
                "action_performed": action,
                "tool_called": "get_employee_profile",
                "tool_result": tool_res,
                "transaction_reference": None
            }

        elif tool_name == "get_employee_balances":
            vac = tool_res.get("vacation_remaining", 0.0)
            vac_acc = tool_res.get("vacation_accrued", 0.0)
            vac_used = tool_res.get("vacation_used", 0.0)
            sick = tool_res.get("sick_remaining", 0.0)
            sick_acc = tool_res.get("sick_accrued", 0.0)
            sick_used = tool_res.get("sick_used", 0.0)
            text = (
                f"Your current WorkWeek leave balances are:\n"
                f"- Vacation: {vac} days remaining ({vac_acc} accrued, {vac_used} used)\n"
                f"- Sick Leave: {sick} days remaining ({sick_acc} accrued, {sick_used} used)"
            )
            return {
                "response_text": text,
                "action_performed": "CHECK_BALANCE",
                "tool_called": "get_employee_balances",
                "tool_result": tool_res,
                "transaction_reference": None
            }

        elif tool_name == "request_time_off":
            status = tool_res.get("status")
            if status == "NEEDS_CLARIFICATION":
                # Distinct from a failure: nothing was attempted, so there is
                # nothing to retry or unwind - we just do not know enough yet.
                return {
                    "response_text": tool_res.get("message", "Could you tell me the dates you need?"),
                    "action_performed": "CLARIFY_LEAVE",
                    "tool_called": "request_time_off",
                    "tool_result": tool_res,
                    "transaction_reference": None
                }
            if status == "SUCCESS":
                req_id = tool_res.get("request_id")
                rem = tool_res.get("remaining_balance")
                days_val = tool_res.get("days")
                s_date = tool_res.get("start_date")
                e_date = tool_res.get("end_date")
                leave_word = "sick leave" if tool_res.get("leave_type") == "Sick" else "vacation"

                text = (
                    f"Your {leave_word} request for {days_val} days from {s_date} to {e_date} "
                    f"has been submitted in WorkWeek."
                )
                # A reference we made up is worse than none: the employee quotes
                # it to HR and no such record exists. Say so instead.
                text += (
                    f" Transaction Reference: [{req_id}]."
                    if req_id
                    else " WorkWeek did not return a reference number for it; "
                         "you can find the request under your leave history."
                )
                # Likewise the balance - reported only when WorkWeek told us.
                if rem is not None:
                    text += f" Remaining balance: {rem} days."
            else:
                text = f"Leave submission failed: {tool_res.get('message')}"
            return {
                "response_text": text,
                "action_performed": "SUBMIT_LEAVE",
                "tool_called": "request_time_off",
                "tool_result": tool_res,
                "transaction_reference": tool_res.get("request_id")
            }

        return {
            "response_text": "Processed WorkWeek request successfully.",
            "action_performed": "UNKNOWN",
            "tool_called": tool_name,
            "tool_result": tool_res,
            "transaction_reference": None
        }



workweek_autonomous_specialist = WorkWeekAutonomousSpecialist()



class HCMSpecialistNode:
    """
    WorkWeek HCM Specialist Agent node (Gemini 3.7 Flash).
    Executes employee self-service operations against WorkWeek adapter.
    Enforces server-side subject binding - never accepts an employee_id argument (§4.1).
    """

    AGENT_ID = "hcm-1.4.0"
    MODEL_ID = "gemini-3.7-flash@2026-08"
    ADAPTER_URL = "https://workweek-adapter-prod-uc.a.run.app"

    def __init__(self, token_minter: CompositeTokenMinter | None = None):
        self.token_minter = token_minter or CompositeTokenMinter()
        # Mock WorkWeek Database (per employee)
        self._profiles: dict[str, dict[str, Any]] = {
            "EMP-44210": {
                "employeeId": "EMP-44210",
                "name": "Sarah Chen",
                "email": "sarah.chen@elevate-corp.internal",
                "department": "Engineering",
                "role": "Senior Staff Architect",
                "workLocation": "REMOTE",
                "homeAddress": "742 Evergreen Terrace, Springfield, OR",
                "phoneNumber": "+15550198234",
                "manager": "Alex Mercer",
                "hireDate": "2022-03-15",
            },
            "EMP-10022": {
                "employeeId": "EMP-10022",
                "name": "David Miller",
                "email": "david.miller@elevate-corp.internal",
                "department": "Sales",
                "role": "Account Executive",
                "workLocation": "ON_SITE",
                "homeAddress": "100 Market St, San Francisco, CA",
                "phoneNumber": "+15550191122",
                "manager": "Maria Garcia",
                "hireDate": "2023-01-10",
            }
        }
        self._balances: dict[str, dict[str, Any]] = {
            "EMP-44210": {"vacation": {"remainingHours": 120.0}, "sick": {"remainingHours": 80.0}},
            "EMP-10022": {"vacation": {"remainingHours": 40.0}, "sick": {"remainingHours": 40.0}},
        }
        self._leaves: dict[str, dict[str, Any]] = {}

    def get_profile(self, employee_id: str) -> dict[str, Any]:
        """ww.get_profile (FR-3.2)"""
        return self._profiles.get(
            employee_id,
            {
                "employeeId": employee_id,
                "name": "Corporate Employee",
                "email": f"{employee_id.lower()}@elevate-corp.internal",
                "workLocation": "REMOTE",
                "homeAddress": "100 Main St, New York, NY",
                "phoneNumber": "+15550100000",
            },
        )

    def get_balances(self, employee_id: str) -> dict[str, Any]:
        """ww.get_balances (FR-3.2, FR-3.4) - Live fetch"""
        return self._balances.get(
            employee_id, {"vacation": {"remainingHours": 80.0}, "sick": {"remainingHours": 80.0}}
        )

    def update_contact(
        self, employee_id: str, new_address: str | None = None, new_phone: str | None = None
    ) -> dict[str, Any]:
        """
        ww.update_contact (FR-3.2)
        Captures previous values to enable REVERSIBLE_SAFE compensation (§5.4).
        """
        profile = self.get_profile(employee_id)
        prev_address = profile.get("homeAddress")
        prev_phone = profile.get("phoneNumber")

        updated_fields = []
        if new_address:
            profile["homeAddress"] = new_address
            updated_fields.append("homeAddress")
        if new_phone:
            profile["phoneNumber"] = new_phone
            updated_fields.append("phoneNumber")

        return {
            "status": "SUCCESS",
            "updated": updated_fields,
            "previousAddress": prev_address,
            "previousPhone": prev_phone,
            "currentAddress": profile.get("homeAddress"),
            "currentPhone": profile.get("phoneNumber"),
        }

    def submit_leave(
        self, employee_id: str, leave_type: str, start_date: str, end_date: str, work_days: float
    ) -> dict[str, Any]:
        """ww.submit_leave (FR-3.2) - Class: HUMAN_CONSEQUENTIAL"""
        leave_id = f"LV-{uuid.uuid4().hex[:4].upper()}"
        leave_doc = {
            "leaveId": leave_id,
            "employeeId": employee_id,
            "leaveType": leave_type,
            "startDate": start_date,
            "endDate": end_date,
            "workDays": work_days,
            "status": "PENDING_APPROVAL",
        }
        self._leaves[leave_id] = leave_doc
        return {"status": "SUCCESS", "leaveId": leave_id, "leaveStatus": "PENDING_APPROVAL"}

    def cancel_leave(self, employee_id: str, leave_id: str) -> dict[str, Any]:
        """ww.cancel_leave - REVERSIBLE_SAFE compensation only"""
        if leave_id in self._leaves:
            self._leaves[leave_id]["status"] = "CANCELLED"
            return {"status": "SUCCESS", "cancelledLeaveId": leave_id}
        return {"status": "NOT_FOUND"}

    async def execute(self, state: AgentState) -> AgentState:
        """
        Processes single-system HCM requests (e.g. balance check, profile read).
        """
        employee_id = state.get("employee_id", "EMP-44210")
        query = state.get("masked_input", state.get("user_input", "")).lower()

        logger.info("[%s] Executing HCM request for subject %s", self.AGENT_ID, employee_id)

        if "balance" in query or "pto" in query:
            balances = self.get_balances(employee_id)
            vac_rem = balances["vacation"]["remainingHours"]
            sick_rem = balances["sick"]["remainingHours"]
            state["final_response"] = (
                f"Your current WorkWeek balances are: "
                f"**{vac_rem} hours** of Vacation PTO remaining, and **{sick_rem} hours** of Sick Leave remaining."
            )
        else:
            profile = self.get_profile(employee_id)
            state["final_response"] = (
                f"WorkWeek Profile for {profile.get('name')}: Department: {profile.get('department')}, "
                f"Location: {profile.get('workLocation')}, Address: {profile.get('homeAddress')}."
            )

        state["next_node"] = "guardrails_out"
        return state
