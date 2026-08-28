"""Unit and integration tests for Cross-System Orchestration (UC-2.1 and UC-2.3)."""
from src.core.agent import HREnterpriseAgent
from src.integrations.workweek.mock_service import workweek_mock_service


def test_uc_2_1_equipment_procurement_success(agent: HREnterpriseAgent):
    """UC-2.1: Verify cross-system equipment procurement for full-time remote worker."""
    prompt = "I just read the remote work policy and saw I'm eligible for a home office monitor. Can you verify my remote status and order one for me?"
    response = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")

    assert response.intent == "UC_2_1_EQUIPMENT_PROCUREMENT"
    assert "Section 08.3" in response.response_text
    assert "ServiceImmediately Hardware Request [REQ" in response.response_text
    assert "123 Tech Park Way, Austin, TX" in response.response_text
    assert len(response.citations) > 0
    assert "[View Policy Section 08.3](https://hr.corp.internal/policies/08.3-remote-equipment)" in response.response_text


def test_uc_2_1_equipment_procurement_ineligible_hybrid(agent: HREnterpriseAgent):
    """UC-2.1 Negative: Verify hybrid employee is rejected under Section 08.3 policy rules."""
    prompt = "Can you order a home office monitor for me?"
    # EMP-1002 is HYBRID
    response = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1002")

    assert response.intent == "UC_2_1_EQUIPMENT_PROCUREMENT"
    assert "available only for full-time remote employees" in response.response_text
    assert "HYBRID" in response.response_text


def test_uc_2_3_relocation_allowance_and_badge(agent: HREnterpriseAgent):
    """UC-2.3: Verify cross-system relocation quote, WorkWeek office update, and facilities ticket."""
    prompt = "I'm transferring to the London office next month. Can you tell me the relocation allowance, update my record, and get my building access sorted?"
    response = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")

    assert response.intent == "UC_2_3_RELOCATION_ALLOWANCE_BADGE"
    assert "Section 14.1" in response.response_text
    assert "£5,000" in response.response_text
    assert "Facilities Badge Ticket [FAC" in response.response_text
    assert "[View Policy Section 14.1](https://hr.corp.internal/policies/14.1-international-relocation)" in response.response_text

    # Verify WorkWeek state was updated
    updated_profile = workweek_mock_service.get_profile("EMP-1001")
    assert updated_profile.current_office == "London - 6 Pancras Sq"
    assert updated_profile.country == "UK"
