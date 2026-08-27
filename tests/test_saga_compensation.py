"""Unit and integration tests for Saga pattern cross-system compensation (UC-2.2)."""
import datetime
import pytest
from src.core.agent import HREnterpriseAgent
from src.integrations.workweek.mock_service import workweek_mock_service
from src.integrations.service_immediately.mock_service import service_immediately_mock_service


def test_uc_2_2_medical_leave_saga_success(agent: HREnterpriseAgent):
    """UC-2.2: Verify end-to-end happy path for medical leave + email routing ticket."""
    today = datetime.date(2026, 8, 27)
    prompt = "I need to take short-term medical leave starting next Monday. What is the process, and can you set it up for me?"
    
    response = agent.process_message(
        user_prompt=prompt,
        caller_employee_id="EMP-1001",
        reference_date=today
    )

    assert response.intent == "UC_2_2_MEDICAL_LEAVE_DELEGATION"
    assert "Medical leave booked in WorkWeek (Ref: WW-LV-" in response.response_text
    assert "ServiceImmediately ticket [INC" in response.response_text
    assert "route email access to your manager" in response.response_text
    assert "[View Policy Section 19.2](https://hr.corp.internal/policies/19.2-medical-leave)" in response.response_text

    # Verify balance was deducted (Sick balance 12.0 - 5.0 = 7.0)
    balances = workweek_mock_service.get_balances("EMP-1001")
    assert balances.sick_remaining == 7.0


def test_uc_2_2_medical_leave_saga_backward_compensation(agent: HREnterpriseAgent):
    """UC-2.2 Failure & Rollback: Verify 500 error triggers WorkWeek rollback and escalation ticket."""
    today = datetime.date(2026, 8, 27)
    prompt = "I need to take short-term medical leave starting next Monday. What is the process, and can you set it up for me?"

    # Inject simulated 500 error in ServiceImmediately
    service_immediately_mock_service.set_simulate_error(True)

    response = agent.process_message(
        user_prompt=prompt,
        caller_employee_id="EMP-1001",
        reference_date=today
    )

    assert response.intent == "UC_2_2_MEDICAL_LEAVE_DELEGATION"
    assert "Service is temporarily unavailable" in response.response_text
    assert "Your pending leave has been rolled back to maintain consistency" in response.response_text
    assert "Support Ticket [INC" in response.response_text

    # Verify WorkWeek leave balance was RESTORED back to 12.0 days
    balances = workweek_mock_service.get_balances("EMP-1001")
    assert balances.sick_remaining == 12.0
    assert balances.sick_used == 2.0
