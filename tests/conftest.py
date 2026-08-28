"""Pytest test fixtures and configuration."""
import re

import pytest

from src.core.agent import HREnterpriseAgent
from src.core.models.routing import (
    ITSMToolSelection,
    SupervisorRoutingDecision,
    WorkWeekToolSelection,
)
from src.core.session import session_store
from src.integrations.service_immediately.mock_service import service_immediately_mock_service
from src.integrations.vertex.client import VertexGeminiClient
from src.integrations.workweek.mock_service import workweek_mock_service
from src.telemetry.audit_logger import audit_logger


class MockVertexGeminiClient:
    """Deterministic mock for Gemini 3.7 Flash in CI and offline unit testing (Approach B)."""

    def route_intent(self, prompt: str, **kwargs) -> SupervisorRoutingDecision:
        p = prompt.lower()

        # UC-2.1: Equipment Procurement
        if ("remote" in p and ("monitor" in p or "hardware" in p or "equipment" in p)) or \
           ("order" in p and "monitor" in p) or ("home office monitor" in p):
            return SupervisorRoutingDecision(
                intent="UC_2_1_EQUIPMENT_PROCUREMENT",
                target_agent="SAGA_COORDINATOR",
                confidence=0.99,
                reasoning="Mock: Remote equipment procurement saga."
            )

        # UC-2.2: Medical Leave Delegation
        if ("medical leave" in p or "sick leave" in p or "short-term medical" in p or "mc" in p) and \
           ("set it up" in p or "delegate" in p or "process" in p or "starting" in p or "submit" in p or "route" in p):
            return SupervisorRoutingDecision(
                intent="UC_2_2_MEDICAL_LEAVE_DELEGATION",
                target_agent="SAGA_COORDINATOR",
                confidence=0.99,
                reasoning="Mock: Medical leave with access delegation saga."
            )

        # UC-2.3: Relocation Allowance & Badge
        if "relocation" in p or "relocating" in p or "transferring to the london" in p or "london office" in p:
            return SupervisorRoutingDecision(
                intent="UC_2_3_RELOCATION_ALLOWANCE_BADGE",
                target_agent="SAGA_COORDINATOR",
                confidence=0.98,
                reasoning="Mock: Relocation allowance & badge saga."
            )

        # UC-1.1: Policy Q&A
        if any(k in p for k in ["policy", "bereavement", "entitlement", "handbook", "rule", "규정", "핸드북", "지침"]):
            return SupervisorRoutingDecision(
                intent="UC_1_1_POLICY_QA",
                target_agent="POLICY_SPECIALIST",
                confidence=0.99,
                reasoning="Mock: Policy Q&A inquiry."
            )

        # UC-1.3: ServiceImmediately Incident Management
        if any(k in p for k in ["ticket", "vpn", "incident", "it helpdesk", "wifi", "dropping", "network", "티켓", "장애"]):
            return SupervisorRoutingDecision(
                intent="UC_1_3_SERVICE_IMMEDIATELY_INCIDENT",
                target_agent="ITSM_SPECIALIST",
                confidence=0.98,
                reasoning="Mock: IT incident report."
            )

        # Out of Domain Refusal (FR-5.4)
        if any(k in p for k in ["weather", "stock", "recipe", "joke", "capital of", "who won", "python code", "write a"]):
            return SupervisorRoutingDecision(
                intent="OUT_OF_DOMAIN",
                target_agent="DOMAIN_CONTAINMENT",
                confidence=0.95,
                reasoning="Mock: Out of domain prompt."
            )

        # UC-1.2: WorkWeek Leave & Profile Self-Service (Default for HR HCM)
        return SupervisorRoutingDecision(
            intent="UC_1_2_WORKWEEK_LEAVE",
            target_agent="WORKWEEK_SPECIALIST",
            confidence=0.98,
            reasoning="Mock: WorkWeek HCM self-service operation."
        )

    def select_workweek_tool(self, prompt: str, **kwargs) -> WorkWeekToolSelection:
        p = prompt.lower()

        # Cancellation
        if any(k in p for k in ["취소", "cancel"]):
            req_match = re.search(r'\b(\d{3,6})\b', p)
            req_id = int(req_match.group(1)) if req_match else 101
            return WorkWeekToolSelection(
                tool_name="cancel_leave_request",
                arguments={"request_id": req_id},
                reasoning="Mock: Cancellation requested."
            )

        # Requests list
        if any(k in p for k in ["목록", "내역", "이력", "history", "requests", "list leaves", "show leaves", "신청한 휴가"]):
            return WorkWeekToolSelection(
                tool_name="get_leave_requests",
                arguments={},
                reasoning="Mock: Requests history list."
            )

        # Update contact info
        if any(k in p for k in ["변경", "업데이트", "바꿔", "update", "change"]) and any(k in p for k in ["주소", "연락처", "전화번호", "address", "phone"]):
            return WorkWeekToolSelection(
                tool_name="update_personal_info",
                arguments={
                    "home_address": "80 Pasir Panjang Rd, #03-01 Mapletree Business City, Singapore 117372",
                    "phone_number": "+65-6521-0000"
                },
                reasoning="Mock: Contact info update."
            )

        # Specific Profile
        if "manager" in p or "매니저" in p or "관리자" in p:
            return WorkWeekToolSelection(
                tool_name="get_employee_profile",
                arguments={"field": "manager"},
                reasoning="Mock: Profile manager query."
            )

        if "department" in p or "부서" in p or "팀" in p:
            return WorkWeekToolSelection(
                tool_name="get_employee_profile",
                arguments={"field": "department"},
                reasoning="Mock: Profile department query."
            )

        if "phone" in p or "전화번호" in p or "연락처" in p:
            return WorkWeekToolSelection(
                tool_name="get_employee_profile",
                arguments={"field": "phone"},
                reasoning="Mock: Profile phone query."
            )

        if ("address" in p or "주소" in p) and not ("profile" in p or "job" in p or "프로필" in p):
            return WorkWeekToolSelection(
                tool_name="get_employee_profile",
                arguments={"field": "address"},
                reasoning="Mock: Profile address query."
            )

        if any(k in p for k in ["profile", "job", "who am i", "프로필", "직무"]):
            return WorkWeekToolSelection(
                tool_name="get_employee_profile",
                arguments={"field": "all"},
                reasoning="Mock: Full profile query."
            )

        # Leave submission
        if any(k in p for k in ["신청", "submit", "request", "휴가 신청"]):
            days = 2.0
            if "1 day" in p or "one day" in p or "하루" in p or "1일" in p:
                days = 1.0
            elif "3 days" in p or "three days" in p or "3일" in p:
                days = 3.0
            elif "5 days" in p or "five days" in p or "5일" in p:
                days = 5.0
            return WorkWeekToolSelection(
                tool_name="request_time_off",
                arguments={
                    "start_date": "2026-09-03",
                    "end_date": "2026-09-04",
                    "days": days,
                    "leave_type": "Sick" if "sick" in p or "병가" in p else "Vacation",
                },
                reasoning="Mock: Time-off submission."
            )

        # Leave balances query (Default)
        return WorkWeekToolSelection(
            tool_name="get_employee_balances",
            arguments={},
            reasoning="Mock: Balances query."
        )

    def select_itsm_tool(self, prompt: str, **kwargs) -> ITSMToolSelection:
        """Delegate to the production offline router rather than restating it.

        This used to be a copy of `_fallback_select_itsm_tool`. Two copies of a
        routing table drift, and the drift is invisible in exactly the direction
        that matters: the suite goes green against the mock's rules while the
        rules that actually ship are wrong. That is not hypothetical - the copy
        reproduced a bug where "any open tickets for me?" filed a new ticket.

        Delegating keeps the determinism this fixture is for (the real method
        is pure and needs no network) and makes every ITSM turn in the suite an
        assertion about production routing.
        """
        return VertexGeminiClient._fallback_select_itsm_tool(prompt)


@pytest.fixture(autouse=True)
def mock_vertex_gemini(monkeypatch):
    """Automatically mock VertexGeminiClient in all pytest tests for deterministic CI execution."""
    mock_client = MockVertexGeminiClient()
    monkeypatch.setattr(VertexGeminiClient, "route_intent", lambda self, prompt, **kwargs: mock_client.route_intent(prompt, **kwargs))
    monkeypatch.setattr(VertexGeminiClient, "select_workweek_tool", lambda self, prompt, **kwargs: mock_client.select_workweek_tool(prompt, **kwargs))
    monkeypatch.setattr(VertexGeminiClient, "select_itsm_tool", lambda self, prompt, **kwargs: mock_client.select_itsm_tool(prompt, **kwargs))


@pytest.fixture(autouse=True)
def reset_system_state():
    """Reset all in-memory databases and logs before each test run."""
    workweek_mock_service.init_mock_data()
    service_immediately_mock_service.init_mock_data()
    audit_logger.clear()
    session_store.clear()
    yield


@pytest.fixture
def agent():
    """Return a clean instance of the HR Enterprise Agent."""
    return HREnterpriseAgent()
