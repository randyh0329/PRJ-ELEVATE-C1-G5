"""Unit and integration tests for Policy Q&A with clickable citations (UC-1.1)."""
import pytest
from src.core.agent import HREnterpriseAgent


def test_bereavement_leave_policy_qa(agent: HREnterpriseAgent):
    """UC-1.1: Verify Bereavement Leave inquiry returns accurate policy and clickable citation."""
    prompt = "What is the company's bereavement leave policy?"
    response = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")

    assert response.intent == "UC_1_1_POLICY_QA"
    assert "Section 04.2" in response.response_text
    assert "5 consecutive days" in response.response_text
    assert len(response.citations) > 0
    assert "[View Policy Section 04.2](https://hr.corp.internal/policies/04.2-bereavement)" in response.response_text


def test_ungrounded_policy_inquiry_no_hallucination(agent: HREnterpriseAgent):
    """Verify agent gracefully refuses ungrounded policy without hallucinating."""
    prompt = "What is the corporate policy regarding bringing pet dragons into the office?"
    response = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")

    assert "could not find an approved policy" in response.response_text.lower()
    assert len(response.citations) == 0
