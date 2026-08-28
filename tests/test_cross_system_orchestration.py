"""Unit and integration tests for Cross-System Orchestration (UC-2.1 and UC-2.3).

Both handlers write to WorkWeek and ServiceImmediately on the strength of an
entitlement, so what they assert about that entitlement is load-bearing. These
tests pin it to the handbook: Section 5.4 grants a US$500 home office allowance
to Remote *or* Hybrid staff, and Section 4 caps international relocation at
US$10,000. The versions of these tests that this file replaced asserted
"Section 08.3", a hybrid refusal, "Section 14.1" and a "Tier 2 allowance of
£5,000" - none of which appear anywhere in the corpus, and all of which were
cited to `hr.corp.internal` URLs that resolve to nothing.
"""
from src.core.agent import HREnterpriseAgent
from src.integrations.workweek.mock_service import workweek_mock_service

CORPUS_BASE = "https://github.com/randyh0329/PRJ-ELEVATE-C1-G5/blob/main/okf/altostrat-sg-handbook/"


def test_uc_2_1_equipment_procurement_success(agent: HREnterpriseAgent):
    """UC-2.1: Verify cross-system equipment procurement for full-time remote worker."""
    prompt = "I just read the remote work policy and saw I'm eligible for a home office monitor. Can you verify my remote status and order one for me?"
    response = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")

    assert response.intent == "UC_2_1_EQUIPMENT_PROCUREMENT"
    assert "Section 5.4" in response.response_text
    assert "US$500 allowance" in response.response_text
    assert "ServiceImmediately Hardware Request [REQ" in response.response_text
    assert "123 Tech Park Way, Austin, TX" in response.response_text
    assert len(response.citations) > 0
    assert CORPUS_BASE + "workplace/remote-and-hybrid-work.md" in response.response_text


def test_uc_2_1_hybrid_staff_are_eligible_because_the_handbook_says_so(
    agent: HREnterpriseAgent,
):
    """The rule grants the allowance to "an approved 'Remote' or 'Hybrid'" status.

    This used to be a *negative* test: the handler hard-coded
    `!= "REMOTE_FULL_TIME"` and refused every hybrid employee, under a section
    number the handbook does not have. The citation printed beside that refusal
    contradicted it, which is the failure mode the corpus rewrite exists to stop.
    """
    # EMP-1002 is HYBRID
    response = agent.process_message(
        user_prompt="Can you order a home office monitor for me?", caller_employee_id="EMP-1002"
    )

    assert response.intent == "UC_2_1_EQUIPMENT_PROCUREMENT"
    assert "ServiceImmediately Hardware Request [REQ" in response.response_text
    assert "does not apply to you" not in response.response_text


def test_uc_2_1_refuses_a_status_the_rule_does_not_name(agent: HREnterpriseAgent, monkeypatch):
    """An on-site employee is outside the quoted rule, so no hardware is ordered."""
    profile = workweek_mock_service.get_profile("EMP-1001").model_copy(
        update={"work_location_status": "ONSITE_FULL_TIME"}
    )
    monkeypatch.setattr(
        agent._ww_client, "get_employee_profile", lambda caller, target: profile
    )

    response = agent.process_message(
        user_prompt="Can you order a home office monitor for me?", caller_employee_id="EMP-1001"
    )

    assert "does not apply to you" in response.response_text
    assert "ONSITE_FULL_TIME" in response.response_text
    assert "Hardware Request" not in response.response_text


def test_uc_2_1_orders_nothing_when_the_rule_cannot_be_grounded(
    agent: HREnterpriseAgent, monkeypatch
):
    """FR-5.2 applies to a transaction as much as to an answer: no rule, no write."""
    monkeypatch.setattr(HREnterpriseAgent, "_entitlement_rule", staticmethod(lambda *a: None))

    response = agent.process_message(
        user_prompt="Can you order a home office monitor for me?", caller_employee_id="EMP-1001"
    )

    assert response.action_performed == "PROCUREMENT_UNGROUNDED"
    assert "could not locate" in response.response_text
    assert response.transaction_reference is None


def test_uc_2_3_relocation_allowance_and_badge(agent: HREnterpriseAgent):
    """UC-2.3: Verify cross-system relocation quote, WorkWeek office update, and facilities ticket."""
    prompt = "I'm transferring to the London office next month. Can you tell me the relocation allowance, update my record, and get my building access sorted?"
    response = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")

    assert response.intent == "UC_2_3_RELOCATION_ALLOWANCE_BADGE"
    # Handbook Section 4 (Travel & Expense), where relocation actually lives.
    assert "Section 4" in response.response_text
    assert "capped at US$10,000" in response.response_text
    assert "£5,000" not in response.response_text
    assert "Facilities Badge Ticket [FAC" in response.response_text
    assert CORPUS_BASE + "workplace/travel-and-expense.md" in response.response_text

    # Verify WorkWeek state was updated
    updated_profile = workweek_mock_service.get_profile("EMP-1001")
    assert updated_profile.current_office == "London - 6 Pancras Sq"
    assert updated_profile.country == "UK"


def test_uc_2_3_writes_nothing_when_the_cap_cannot_be_grounded(
    agent: HREnterpriseAgent, monkeypatch
):
    """SDD §3.4 Path 6 quotes the allowance before it touches WorkWeek, so an
    ungroundable cap has to stop the saga rather than proceed silently: the
    record change and the badge ticket are both downstream of a figure nobody
    can source."""
    monkeypatch.setattr(HREnterpriseAgent, "_entitlement_rule", staticmethod(lambda *a: None))
    before = workweek_mock_service.get_profile("EMP-1001").current_office

    response = agent.process_message(
        user_prompt="I'm transferring to the London office next month, what is my relocation allowance?",
        caller_employee_id="EMP-1001",
    )

    assert response.action_performed == "RELOCATION_UNGROUNDED"
    assert "have not changed your record" in response.response_text
    assert workweek_mock_service.get_profile("EMP-1001").current_office == before
