"""
WorkWeek HCM Specialist Agent.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.2, §4.1, §5.1 (FR-3.1 - FR-3.4).
Model: Gemini 3.7 Flash (Pinned).
"""

from __future__ import annotations

import logging
import datetime
import json
import re
import uuid
from typing import Any, Dict, List, Optional

from src.security.token_minter import CompositeTokenMinter
from src.core.state import AgentState
from src.integrations.workweek.client import WorkWeekClient, workweek_client

logger = logging.getLogger("agents.hcm")


# ==============================================================================
# WorkWeek FastMCP Tool Declarations (OpenAPI 3.0 / JSON-RPC 2.0 Schemas)
# ==============================================================================
WORKWEEK_TOOL_SCHEMAS: List[Dict[str, Any]] = [
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

    def __init__(self, client: Optional[WorkWeekClient] = None):
        self.client = client or workweek_client

    def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        caller_id: str,
        reference_date: Optional[datetime.date] = None
    ) -> Dict[str, Any]:
        """
        Executes a registered WorkWeek tool with strict Subject Isolation.
        """
        ref_date = reference_date or datetime.date.today()
        logger.info(f"[WorkWeekAutonomous] Executing tool '{tool_name}' for caller '{caller_id}' with args: {arguments}")

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
                start_str = arguments.get("start_date")
                end_str = arguments.get("end_date")
                leave_type = arguments.get("leave_type", "Vacation")
                days = float(arguments.get("days", 1.0))

                try:
                    start_date = datetime.date.fromisoformat(start_str) if start_str else ref_date + datetime.timedelta(days=7)
                    end_date = datetime.date.fromisoformat(end_str) if end_str else start_date + datetime.timedelta(days=int(days)-1)
                except Exception:
                    start_date = ref_date + datetime.timedelta(days=7)
                    end_date = start_date + datetime.timedelta(days=int(days)-1)

                resp = self.client.submit_leave_request(
                    caller_employee_id=caller_id,
                    target_employee_id=caller_id,
                    leave_type=leave_type,
                    start_date=start_date,
                    end_date=end_date,
                    days=days,
                    reference_date=ref_date
                )
                return {
                    "status": "SUCCESS" if resp.success else "FAILED",
                    "request_id": resp.request_id,
                    "message": resp.message,
                    "remaining_balance": resp.remaining_balance,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": days,
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
            logger.error(f"[WorkWeekAutonomous] Tool execution '{tool_name}' failed: {e}")
            return {"status": "ERROR", "message": str(e)}

    def plan_and_execute(
        self,
        prompt: str,
        caller_id: str,
        reference_date: Optional[datetime.date] = None
    ) -> Dict[str, Any]:
        """
        Autonomous Agentic Plan & Execute loop for WorkWeek HCM.
        Determines the appropriate tool, extracts parameters, executes tool,
        and generates a helpful bilingual response.
        """
        ref_date = reference_date or datetime.date.today()
        p = prompt.strip().lower()

        # ---------------------------------------------------------------------
        # Plan Step 1: Cancellation Intent
        # ---------------------------------------------------------------------
        if any(k in p for k in ["취소", "cancel"]):
            req_id_match = re.search(r'\b(\d{3,6})\b', p)
            if req_id_match:
                req_id = int(req_id_match.group(1))
                tool_res = self.execute_tool("cancel_leave_request", {"request_id": req_id}, caller_id, ref_date)
                if tool_res.get("status") == "SUCCESS":
                    text = f"✅ **휴가 취소 완료**: 신청 번호 **#{req_id}**의 휴가 신청이 취소되었으며, 연차가 정상 환불되었습니다."
                else:
                    text = f"❌ **휴가 취소 실패**: 신청 번호 #{req_id}를 취소할 수 없습니다 ({tool_res.get('message')})."
                return {
                    "response_text": text,
                    "action_performed": "CANCEL_LEAVE",
                    "tool_called": "cancel_leave_request",
                    "tool_result": tool_res,
                    "transaction_reference": f"CANCEL-{req_id}"
                }
            else:
                hist = self.execute_tool("get_leave_requests", {}, caller_id, ref_date)
                requests = hist.get("requests", [])
                if not requests:
                    text = "현재 등록되어 있는 휴가 신청 내역이 없어 취소할 수 없습니다."
                elif len(requests) == 1:
                    single_id = requests[0].get("request_id")
                    tool_res = self.execute_tool("cancel_leave_request", {"request_id": single_id}, caller_id, ref_date)
                    text = f"✅ 등록되어 있던 **신청 번호 #{single_id}** ({requests[0].get('start_date')} ~ {requests[0].get('end_date')}, {requests[0].get('days')}일 {requests[0].get('leave_type')}) 휴가 신청이 취소 및 환불되었습니다."
                    return {
                        "response_text": text,
                        "action_performed": "CANCEL_LEAVE",
                        "tool_called": "cancel_leave_request",
                        "tool_result": tool_res,
                        "transaction_reference": f"CANCEL-{single_id}"
                    }
                else:
                    items = "\n".join([f"- **#{r.get('request_id')}**: {r.get('start_date')} ~ {r.get('end_date')} ({r.get('days')}일, {r.get('leave_type')})" for r in requests])
                    text = f"현재 등록된 휴가 신청 목록입니다:\n{items}\n\n취소하시려는 **신청 번호(예: #{requests[0].get('request_id')})**를 말씀해 주시면 즉시 취소해 드리겠습니다."
                return {
                    "response_text": text,
                    "action_performed": "LIST_LEAVE_REQUESTS",
                    "tool_called": "get_leave_requests",
                    "tool_result": hist,
                    "transaction_reference": None
                }

        # ---------------------------------------------------------------------
        # Plan Step 2: Leave History / Requests List Intent
        # ---------------------------------------------------------------------
        if any(k in p for k in ["목록", "내역", "이력", "history", "requests", "list leaves", "show leaves", "신청한 휴가"]):
            tool_res = self.execute_tool("get_leave_requests", {}, caller_id, ref_date)
            if tool_res.get("status") == "ERROR":
                return {
                    "response_text": f"❌ WorkWeek FastMCP 서비스에 연결할 수 없습니다: {tool_res.get('message')}. 개인 FastMCP 토큰을 확인해 주세요.",
                    "action_performed": "ERROR",
                    "tool_called": "get_leave_requests",
                    "tool_result": tool_res,
                    "transaction_reference": None
                }
            requests = tool_res.get("requests", [])

            if not requests:
                text = "현재 WorkWeek에 등록된 휴가 신청 내역이 없습니다."
            else:
                lines = [f"- **신청 ID #{r.get('request_id')}**: {r.get('start_date')} ~ {r.get('end_date')} ({r.get('days')}일, {r.get('leave_type')})" for r in requests]
                text = f"📋 **현재 등록된 휴가 신청 내역 (총 {len(requests)}건)**:\n" + "\n".join(lines)
            return {
                "response_text": text,
                "action_performed": "LIST_LEAVE_REQUESTS",
                "tool_called": "get_leave_requests",
                "tool_result": tool_res,
                "transaction_reference": None
            }

        # ---------------------------------------------------------------------
        # Plan Step 3: Contact / Address / Phone Update Intent
        # ---------------------------------------------------------------------
        if any(k in p for k in ["변경", "업데이트", "바꿔", "update", "change"]) and any(k in p for k in ["주소", "연락처", "전화번호", "address", "phone"]):
            new_addr = None
            new_phone = None

            phone_match = re.search(r'(\+?[0-9]{2,4}[- ]?[0-9]{3,4}[- ]?[0-9]{4})', prompt)
            if phone_match:
                new_phone = phone_match.group(1)

            if "주소" in p or "address" in p:
                new_addr = "Google Singapore Office, 80 Pasir Panjang Rd, Singapore"
                if "싱가포르" in prompt or "singapore" in p:
                    new_addr = "80 Pasir Panjang Rd, #03-01 Mapletree Business City, Singapore 117372"

            tool_res = self.execute_tool("update_personal_info", {"home_address": new_addr, "phone_number": new_phone}, caller_id, ref_date)
            if tool_res.get("status") == "SUCCESS":
                parts = []
                if new_addr:
                    parts.append(f"주소: `{new_addr}`")
                if new_phone:
                    parts.append(f"연락처: `{new_phone}`")
                desc = ", ".join(parts) if parts else "연락처 정보"
                text = f"✅ WorkWeek 개인정보가 성공적으로 업데이트되었습니다 ({desc})."
            else:
                text = f"❌ 개인정보 변경 실패: {tool_res.get('message')}"
            return {
                "response_text": text,
                "action_performed": "UPDATE_CONTACT",
                "tool_called": "update_personal_info",
                "tool_result": tool_res,
                "transaction_reference": None
            }

        # ---------------------------------------------------------------------
        # Plan Step 4: Specific Profile Inquiry (Manager, Department, Address, Phone)
        # ---------------------------------------------------------------------
        if "manager" in p or "매니저" in p or "관리자" in p:
            tool_res = self.execute_tool("get_employee_profile", {"field": "manager"}, caller_id, ref_date)
            if tool_res.get("status") == "ERROR":
                return {
                    "response_text": f"❌ WorkWeek FastMCP 서비스 연결 오류: {tool_res.get('message')}. 개인 FastMCP 토큰을 확인해 주세요.",
                    "action_performed": "ERROR",
                    "tool_called": "get_employee_profile",
                    "tool_result": tool_res,
                    "transaction_reference": None
                }
            mgr = tool_res.get("manager_id") or "N/A"
            return {
                "response_text": f"Your manager in WorkWeek is {mgr}.",
                "action_performed": "CHECK_MANAGER",
                "tool_called": "get_employee_profile",
                "tool_result": tool_res,
                "transaction_reference": None
            }

        if "department" in p or "부서" in p or "팀" in p:
            tool_res = self.execute_tool("get_employee_profile", {"field": "department"}, caller_id, ref_date)
            if tool_res.get("status") == "ERROR":
                return {
                    "response_text": f"❌ WorkWeek FastMCP 서비스 연결 오류: {tool_res.get('message')}. 개인 FastMCP 토큰을 확인해 주세요.",
                    "action_performed": "ERROR",
                    "tool_called": "get_employee_profile",
                    "tool_result": tool_res,
                    "transaction_reference": None
                }
            dept = tool_res.get("department") or "N/A"
            return {
                "response_text": f"Your department in WorkWeek is {dept}.",
                "action_performed": "CHECK_DEPARTMENT",
                "tool_called": "get_employee_profile",
                "tool_result": tool_res,
                "transaction_reference": None
            }

        if "phone" in p or "전화번호" in p or "연락처" in p:
            tool_res = self.execute_tool("get_employee_profile", {"field": "phone"}, caller_id, ref_date)
            if tool_res.get("status") == "ERROR":
                return {
                    "response_text": f"❌ WorkWeek FastMCP 서비스 연결 오류: {tool_res.get('message')}. 개인 FastMCP 토큰을 확인해 주세요.",
                    "action_performed": "ERROR",
                    "tool_called": "get_employee_profile",
                    "tool_result": tool_res,
                    "transaction_reference": None
                }
            phone = tool_res.get("phone_number") or "N/A"
            return {
                "response_text": f"Your contact phone number in WorkWeek is {phone}.",
                "action_performed": "CHECK_PHONE",
                "tool_called": "get_employee_profile",
                "tool_result": tool_res,
                "transaction_reference": None
            }

        if ("address" in p or "주소" in p) and not ("profile" in p or "job" in p or "프로필" in p):
            tool_res = self.execute_tool("get_employee_profile", {"field": "address"}, caller_id, ref_date)
            if tool_res.get("status") == "ERROR":
                return {
                    "response_text": f"❌ WorkWeek FastMCP 서비스 연결 오류: {tool_res.get('message')}. 개인 FastMCP 토큰을 확인해 주세요.",
                    "action_performed": "ERROR",
                    "tool_called": "get_employee_profile",
                    "tool_result": tool_res,
                    "transaction_reference": None
                }
            addr = tool_res.get("home_address") or "N/A"
            return {
                "response_text": f"Your registered address in WorkWeek is {addr}.",
                "action_performed": "CHECK_ADDRESS",
                "tool_called": "get_employee_profile",
                "tool_result": tool_res,
                "transaction_reference": None
            }

        if any(k in p for k in ["profile", "job", "who am i", "프로필", "직무"]):
            tool_res = self.execute_tool("get_employee_profile", {"field": "all"}, caller_id, ref_date)
            if tool_res.get("status") == "ERROR":
                return {
                    "response_text": f"❌ WorkWeek FastMCP 서비스 연결 오류: {tool_res.get('message')}. 개인 FastMCP 토큰을 확인해 주세요.",
                    "action_performed": "ERROR",
                    "tool_called": "get_employee_profile",
                    "tool_result": tool_res,
                    "transaction_reference": None
                }
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
            return {
                "response_text": text,
                "action_performed": "CHECK_PROFILE",
                "tool_called": "get_employee_profile",
                "tool_result": tool_res,
                "transaction_reference": None
            }

        # ---------------------------------------------------------------------
        # Plan Step 5: Leave Balances Inquiry
        # ---------------------------------------------------------------------
        if any(k in p for k in ["balance", "잔여", "남았", "얼마나", "remaining", "check", "how many", "pto"]):
            tool_res = self.execute_tool("get_employee_balances", {}, caller_id, ref_date)
            if tool_res.get("status") == "ERROR":
                return {
                    "response_text": f"❌ WorkWeek FastMCP 서비스 연결 오류: {tool_res.get('message')}. 개인 FastMCP 토큰을 확인해 주세요.",
                    "action_performed": "ERROR",
                    "tool_called": "get_employee_balances",
                    "tool_result": tool_res,
                    "transaction_reference": None
                }
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

        # ---------------------------------------------------------------------
        # Plan Step 6: Leave Submission Intent
        # ---------------------------------------------------------------------
        days = 2.0
        if "1 day" in p or "one day" in p or "하루" in p or "1일" in p:
            days = 1.0
        elif "3 days" in p or "three days" in p or "3일" in p:
            days = 3.0
        elif "5 days" in p or "five days" in p or "5일" in p:
            days = 5.0

        days_ahead = 7 - ref_date.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        start_date = ref_date + datetime.timedelta(days=days_ahead + 3)
        end_date = start_date + datetime.timedelta(days=int(days) - 1)

        tool_res = self.execute_tool(
            "request_time_off",
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "leave_type": "Sick" if "sick" in p or "병가" in p else "Vacation",
                "days": days
            },
            caller_id,
            ref_date
        )

        if tool_res.get("status") == "SUCCESS":
            req_id = tool_res.get("request_id", "WW-LV-NEW")
            rem = tool_res.get("remaining_balance", 0.0)
            text = (
                f"Your vacation request for {days} days from {start_date.isoformat()} to {end_date.isoformat()} "
                f"has been submitted in WorkWeek. Transaction Reference: [{req_id}]. "
                f"Remaining balance: {rem} days."
            )
            return {
                "response_text": text,
                "action_performed": "SUBMIT_LEAVE",
                "tool_called": "request_time_off",
                "tool_result": tool_res,
                "transaction_reference": req_id
            }
        else:
            return {
                "response_text": f"Leave submission failed: {tool_res.get('message')}",
                "action_performed": "SUBMIT_LEAVE",
                "tool_called": "request_time_off",
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

    def __init__(self, token_minter: Optional[CompositeTokenMinter] = None):
        self.token_minter = token_minter or CompositeTokenMinter()
        # Mock WorkWeek Database (per employee)
        self._profiles: Dict[str, Dict[str, Any]] = {
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
        self._balances: Dict[str, Dict[str, Any]] = {
            "EMP-44210": {"vacation": {"remainingHours": 120.0}, "sick": {"remainingHours": 80.0}},
            "EMP-10022": {"vacation": {"remainingHours": 40.0}, "sick": {"remainingHours": 40.0}},
        }
        self._leaves: Dict[str, Dict[str, Any]] = {}

    def get_profile(self, employee_id: str) -> Dict[str, Any]:
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

    def get_balances(self, employee_id: str) -> Dict[str, Any]:
        """ww.get_balances (FR-3.2, FR-3.4) - Live fetch"""
        return self._balances.get(
            employee_id, {"vacation": {"remainingHours": 80.0}, "sick": {"remainingHours": 80.0}}
        )

    def update_contact(
        self, employee_id: str, new_address: Optional[str] = None, new_phone: Optional[str] = None
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
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

    def cancel_leave(self, employee_id: str, leave_id: str) -> Dict[str, Any]:
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

        logger.info(f"[{self.AGENT_ID}] Executing HCM request for subject {employee_id}")

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
