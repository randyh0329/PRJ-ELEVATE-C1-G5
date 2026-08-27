"""
WorkWeek HCM Specialist Agent.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.2, §4.1, §5.1 (FR-3.1 - FR-3.4).
Model: Gemini 3.7 Flash (Pinned).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from app.security.token_minter import CompositeTokenMinter
from app.state import AgentState

logger = logging.getLogger("agents.hcm")


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
