"""Unit and integration tests for ServiceImmediately ITSM operations (UC-1.3)."""
from src.core.agent import HREnterpriseAgent


def test_service_immediately_create_vpn_incident(agent: HREnterpriseAgent):
    """UC-1.3: Verify creating IT support incident for VPN connection issue."""
    prompt = "Create an IT ticket because my VPN connection keeps dropping."
    response = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")

    assert response.intent == "UC_1_3_SERVICE_IMMEDIATELY_INCIDENT"
    assert "Support Incident Ticket [INC" in response.response_text
    assert "Priority '3 - Moderate'" in response.response_text
    assert response.transaction_reference is not None
    assert response.transaction_reference.startswith("INC")


def test_service_immediately_duplicate_prevention(agent: HREnterpriseAgent):
    """Verify 30-minute duplicate ticket mitigation."""
    prompt = "Create an IT ticket because my VPN connection keeps dropping."

    # Turn 1: Initial creation succeeds
    resp1 = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")
    assert "Support Incident Ticket [INC" in resp1.response_text

    # Turn 2: Duplicate creation within 30 minutes is rejected
    resp2 = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")
    assert "Duplicate ticket detected" in resp2.response_text
