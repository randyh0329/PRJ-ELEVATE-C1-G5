"""
Unit and integration tests for LLM-based Supervisor Router and Tool Calling.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.1 & §3.2 (FR-1.1, FR-2.1).
"""

from src.core.agent import HREnterpriseAgent
from src.core.agents.hcm import workweek_autonomous_specialist


def test_supervisor_routing_intents(agent: HREnterpriseAgent):
    """Verify Gemini 3.7 Flash Supervisor routes correctly across all use cases."""
    # Policy Q&A
    res_policy = agent.process_message("What is the parental leave policy?", caller_employee_id="EMP-1001")
    assert res_policy.intent == "UC_1_1_POLICY_QA"

    # WorkWeek HCM
    res_hcm = agent.process_message("Check my vacation and sick balances", caller_employee_id="EMP-1001")
    assert res_hcm.intent == "UC_1_2_WORKWEEK_LEAVE"
    assert "Vacation:" in res_hcm.response_text

    # ITSM Incident
    res_itsm = agent.process_message("My VPN keeps dropping, please open an IT ticket", caller_employee_id="EMP-1001")
    assert res_itsm.intent == "UC_1_3_SERVICE_IMMEDIATELY_INCIDENT"
    assert "INC" in res_itsm.response_text

    # Cross-System Saga: UC-2.1 Equipment
    res_eq = agent.process_message("Order a home office monitor under remote policy", caller_employee_id="EMP-1001")
    assert res_eq.intent == "UC_2_1_EQUIPMENT_PROCUREMENT"

    # Cross-System Saga: UC-2.2 Medical Leave
    res_med = agent.process_message("I need medical leave and please delegate and set it up", caller_employee_id="EMP-1001")
    assert res_med.intent == "UC_2_2_MEDICAL_LEAVE_DELEGATION"

    # Cross-System Saga: UC-2.3 Relocation
    res_relo = agent.process_message("I am relocating to the london office and need my allowance and badge", caller_employee_id="EMP-1001")
    assert res_relo.intent == "UC_2_3_RELOCATION_ALLOWANCE_BADGE"


def test_supervisor_out_of_domain_containment(agent: HREnterpriseAgent):
    """Verify FR-5.4 Domain Containment Refusal for irrelevant prompts."""
    res_weather = agent.process_message("What's the weather today in Tokyo?", caller_employee_id="EMP-1001")
    assert res_weather.intent == "OUT_OF_DOMAIN"
    assert res_weather.is_refusal is True
    assert "outside what I can assist with" in res_weather.response_text


def test_workweek_specialist_tool_calling():
    """Verify WorkWeekAutonomousSpecialist executes tools based on LLM tool selection."""
    # Test balance inquiry
    res_bal = workweek_autonomous_specialist.plan_and_execute(
        prompt="How much vacation do I have left?",
        caller_id="EMP-1001"
    )
    assert res_bal["action_performed"] == "CHECK_BALANCE"
    assert res_bal["tool_called"] == "get_employee_balances"
    assert "Vacation: 14.0 days remaining" in res_bal["response_text"]

    # Test profile manager inquiry
    res_mgr = workweek_autonomous_specialist.plan_and_execute(
        prompt="Who is my manager?",
        caller_id="EMP-1001"
    )
    assert res_mgr["action_performed"] == "CHECK_MANAGER"
    assert res_mgr["tool_called"] == "get_employee_profile"
    assert "MGR-2001" in res_mgr["response_text"]

    # Test leave submission
    res_sub = workweek_autonomous_specialist.plan_and_execute(
        prompt="Submit 3 days vacation request",
        caller_id="EMP-1001"
    )
    assert res_sub["action_performed"] == "SUBMIT_LEAVE"
    assert res_sub["tool_called"] == "request_time_off"
    assert res_sub["transaction_reference"].startswith("WW-LV-")
