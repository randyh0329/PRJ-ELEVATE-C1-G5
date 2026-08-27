import pytest
from datetime import datetime, timedelta
from src.agent_core.graph import orchestration_graph
from src.agent_core.saga import saga_coordinator
from src.mocks.app import mock_app
from src.mocks.state_manager import state_manager
from src.mocks.fidelity import fidelity_engine
from src.storage.firestore import firestore_store
from src.telemetry.logger import telemetry_logger


@pytest.fixture(autouse=True)
def setup_test_state():
    fidelity_engine.set_profile("unit")
    state_manager.reset_state()
    telemetry_logger.clear()
    firestore_store.clear()



@pytest.mark.asyncio
async def test_supervisor_routes_policy():
    res = await orchestration_graph.run(
        user_message="How many days of bereavement leave do I get for immediate family?",
        session_id="test-sess-policy",
        employee_id="EMP-44210"
    )
    assert "5 consecutive" in res["content"]
    assert len(res["citations"]) > 0
    assert any("Leave" in c.documentTitle for c in res["citations"])


@pytest.mark.asyncio
async def test_supervisor_routes_hcm_balance():
    res = await orchestration_graph.run(
        user_message="What is my remaining vacation balance?",
        session_id="test-sess-bal",
        employee_id="EMP-44210"
    )
    assert "56.0 hours" in res["content"]
    assert "Vacation Leave" in res["content"]


@pytest.mark.asyncio
async def test_supervisor_routes_hcm_profile():
    res = await orchestration_graph.run(
        user_message="Show my profile and role",
        session_id="test-sess-prof",
        employee_id="EMP-44210"
    )
    assert "Alex Morgan" in res["content"]
    assert "EMP-44210" in res["content"]


@pytest.mark.asyncio
async def test_supervisor_routes_itsm_ticket():
    res = await orchestration_graph.run(
        user_message="What is the current status of incident INC123456?",
        session_id="test-sess-itsm",
        employee_id="EMP-44210"
    )
    assert "INC123456" in res["content"]
    assert "In Progress" in res["content"]


@pytest.mark.asyncio
async def test_supervisor_out_of_domain_containment():
    res = await orchestration_graph.run(
        user_message="Can you write a python script to parse CSV files?",
        session_id="test-sess-ood",
        employee_id="EMP-44210"
    )
    assert "I can help with HR policies, WorkWeek and IT tickets" in res["content"]


@pytest.mark.asyncio
async def test_saga_equipment_workflow_uc21():
    res = await saga_coordinator.execute_equipment_workflow(
        session_id="test-sess-eq",
        employee_id="EMP-44210",
        device_type="monitor"
    )
    assert "Equipment Request Submitted Successfully" in res["content"]
    assert "INC" in res["ticketId"]

    # Verify ticket created in ITSM
    inc = state_manager.get_incident(res["ticketId"])
    assert inc is not None
    assert inc["category"] == "Hardware"


@pytest.mark.asyncio
async def test_saga_medical_leave_workflow_uc22_success():
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    two_weeks = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    res = await saga_coordinator.execute_medical_leave_workflow(
        session_id="test-sess-med",
        employee_id="EMP-44210",
        start_date=tomorrow,
        end_date=two_weeks,
        work_days=10.0,
        simulate_ancillary_failure=False
    )
    assert "Medical Leave Setup Complete" in res["content"]
    assert res["leaveId"].startswith("LV-")
    assert res["ticketId"].startswith("INC")

    # Verify saga record in firestore
    saga = firestore_store.get_saga(res["sagaId"])
    assert saga["currentState"] == "COMPLETED"
    assert len(saga["steps"]) == 3


@pytest.mark.asyncio
async def test_saga_medical_leave_workflow_uc22_ancillary_failure_compensation_policy():
    """
    CRITICAL TEST: SDD §5.4 & NFR-4.3
    When Step 3 (ANCILLARY IT routing ticket) fails, the prior Step 2
    (HUMAN_CONSEQUENTIAL Medical Leave in WorkWeek) MUST NOT BE CANCELLED.
    State must become PARTIALLY_COMPLETED_MANUAL_FOLLOWUP, and a zero-PII
    SagaCompensationEvent must be emitted!
    """
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    two_weeks = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")

    res = await saga_coordinator.execute_medical_leave_workflow(
        session_id="test-sess-med-fail",
        employee_id="EMP-44210",
        start_date=tomorrow,
        end_date=two_weeks,
        work_days=10.0,
        simulate_ancillary_failure=True
    )
    assert "Partially Completed - Manual Follow-up Needed" in res["content"]
    assert "Your medical leave request is active and preserved" in res["content"]
    assert res["leaveId"].startswith("LV-")
    assert res.get("partialFailure") is True

    # 1. Verify WorkWeek leave was NOT cancelled
    emp = state_manager.get_employee("EMP-44210")
    leaves = [l for l in emp.get("leaves", []) if l["leaveId"] == res["leaveId"]]
    assert len(leaves) == 1
    assert leaves[0]["status"] == "PENDING_APPROVAL"  # Preserved!

    # 2. Verify Saga Record state
    saga = firestore_store.get_saga(res["sagaId"])
    assert saga["currentState"] == "PARTIALLY_COMPLETED_MANUAL_FOLLOWUP"
    assert saga["steps"][1]["status"] == "SUCCESS"
    assert saga["steps"][2]["status"] == "FAILED_HANDED_TO_HUMAN"

    # 3. Verify Zero-PII SagaCompensationEvent emitted (SDD §4.11)
    events = telemetry_logger.get_events("saga_compensation_event")
    assert len(events) == 1
    comp_event = events[0]
    assert comp_event["compensation_decision"] == "DO_NOT_COMPENSATE_PRESERVE_AND_ALERT"
    assert comp_event["field_names_only"] == ["startDate", "endDate", "leaveType", "workDays"]
    assert "EMP-44210" not in str(comp_event["employee_id_hash"]) # SHA256 hashed!


@pytest.mark.asyncio
async def test_saga_relocation_workflow_uc23():
    res = await saga_coordinator.execute_relocation_workflow(
        session_id="test-sess-reloc",
        employee_id="EMP-44210",
        new_address="221B Baker Street, London, UK",
        destination_city="London"
    )
    assert "Relocation Workflow Complete" in res["content"]
    assert res["ticketId"].startswith("INC")

    # Verify address updated in WorkWeek
    emp = state_manager.get_employee("EMP-44210")
    assert emp["homeAddress"] == "221B Baker Street, London, UK"
