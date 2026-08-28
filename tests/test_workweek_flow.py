"""Unit and integration tests for WorkWeek HCM operations (UC-1.2)."""
import datetime

import pytest

from src.core.agent import HREnterpriseAgent
from src.integrations.workweek.client import workweek_client


def test_workweek_balance_inquiry(agent: HREnterpriseAgent):
    """UC-1.2: Verify employee can query their real-time leave balance."""
    prompt = "What is my current leave balance?"
    response = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")

    assert response.intent == "UC_1_2_WORKWEEK_LEAVE"
    assert "Vacation: 14.0 days remaining" in response.response_text
    assert "Sick Leave: 12.0 days remaining" in response.response_text


def test_workweek_leave_submission(agent: HREnterpriseAgent):
    """UC-1.2: Verify leave submission deducts balance and returns transaction reference."""
    today = datetime.date(2026, 8, 27)
    prompt = "Please submit a vacation request for 2 days next week."
    response = agent.process_message(
        user_prompt=prompt,
        caller_employee_id="EMP-1001",
        reference_date=today
    )

    assert response.intent == "UC_1_2_WORKWEEK_LEAVE"
    assert "submitted in WorkWeek" in response.response_text
    assert response.transaction_reference is not None
    assert response.transaction_reference.startswith("WW-LV-")
    assert "Remaining balance: 12.0 days" in response.response_text


def test_workweek_caller_isolation_security():
    """Verify FR-1.5: Cross-employee profile and balance lookups are blocked."""
    with pytest.raises(PermissionError) as exc_info:
        workweek_client.get_employee_profile(
            caller_employee_id="EMP-1001",
            target_employee_id="EMP-1002"
        )
    assert "Access Denied" in str(exc_info.value)
