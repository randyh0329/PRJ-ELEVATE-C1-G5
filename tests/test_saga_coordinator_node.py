"""The graph-path saga coordinator and the §5.4 compensation decision matrix.

`SagaCoordinatorNode` runs the three cross-system workflows (§3.3 Paths 4-6) and
hands any step failure to `SagaCompensationDecisionMatrix`. The matrix is where
the SDD's one non-negotiable rule lives: a step's *consequence class* decides
what may be undone, and `HUMAN_CONSEQUENTIAL` may never be undone automatically.

The distinction the tests keep returning to is between the three outcomes:

* `ANCILLARY` failure - the primary record stands, the follow-up is queued for a
  human, and the employee is told no action is required of them.
* all-`REVERSIBLE_SAFE` prior steps - everything is put back and the saga reads
  as rolled back.
* a mixed history containing `HUMAN_CONSEQUENTIAL` - the reversible parts are
  undone, the consequential ones are *preserved*, and the remainder escalates.

Un-filing someone's medical leave because a badge ticket failed is the failure
mode all of this exists to prevent, so several tests assert on what was *not*
called as much as on what was.
"""

from __future__ import annotations

import pytest

from src.core.agents.saga import SagaCoordinatorNode
from src.core.state import (
    SagaCompensationClass,
    SagaStepRecord,
    SagaStepStatus,
    SagaWorkflowState,
)
from src.saga.compensation import SagaCompensationDecisionMatrix
from src.saga.ledger import SagaLedgerManager


class FakeHCM:
    """Stands in for the WorkWeek specialist, recording every write."""

    def __init__(self, work_location: str = "REMOTE"):
        self.work_location = work_location
        self.contact_updates: list[dict] = []
        self.leaves: list[dict] = []
        self.cancellations: list[tuple[str, str]] = []

    def get_profile(self, employee_id: str) -> dict:
        return {"employeeId": employee_id, "workLocation": self.work_location}

    def update_contact(self, employee_id, new_address=None, new_phone=None):
        self.contact_updates.append(
            {"employee_id": employee_id, "address": new_address, "phone": new_phone}
        )
        return {
            "previousAddress": "1 Raffles Place, Singapore 048616",
            "previousPhone": "+65 6555 0100",
        }

    def submit_leave(self, **kwargs):
        self.leaves.append(kwargs)
        return {"leaveId": "WW-LV-778899"}

    def cancel_leave(self, employee_id, leave_id):
        self.cancellations.append((employee_id, leave_id))
        return {"status": "CANCELLED"}


class FakeITSM:
    def __init__(self):
        self.created: list[dict] = []

    def create_incident(self, **kwargs):
        self.created.append(kwargs)
        return {"ticketId": f"REQ-{len(self.created):04d}"}


@pytest.fixture
def hcm() -> FakeHCM:
    return FakeHCM()


@pytest.fixture
def itsm() -> FakeITSM:
    return FakeITSM()


@pytest.fixture
def node(hcm, itsm) -> SagaCoordinatorNode:
    return SagaCoordinatorNode(
        ledger=SagaLedgerManager(in_memory=True),
        policy_agent=object(),
        hcm_agent=hcm,
        itsm_agent=itsm,
    )


def _state(saga_type: str, **overrides) -> dict:
    state = {
        "saga_type": saga_type,
        "session_id": "sess-1",
        "employee_id": "EMP-44210",
        "user_input": "please arrange it",
    }
    state.update(overrides)
    return state


# --- dispatch -----------------------------------------------------------------


@pytest.mark.parametrize(
    "saga_type", ["UC-2.1-EQUIPMENT", "UC-2.2-MEDICAL-LEAVE", "UC-2.3-RELOCATION"]
)
async def test_every_workflow_opens_a_ledger_entry_before_it_acts(node, saga_type):
    """§4.6 RPO=0: the saga must be recoverable from the moment the first write
    is possible, so the ledger entry precedes any call to a backend."""
    state = await node.execute(_state(saga_type))

    assert node.ledger.get_saga(state["saga_id"])["workflowType"] == saga_type


async def test_a_caller_supplied_saga_id_is_reused_rather_than_replaced(node):
    """A retried turn must land on the existing saga, not open a second one."""
    state = await node.execute(_state("UC-2.1-EQUIPMENT", saga_id="saga-fixed"))

    assert state["saga_id"] == "saga-fixed"


async def test_an_unrecognised_workflow_type_is_declined_without_touching_a_backend(
    node, hcm, itsm
):
    """Defensive: the supervisor names the workflow, so an unknown one is a bug
    upstream. Guessing at it would mean writing to a system nobody asked for."""
    state = await node.execute(_state("UC-9.9-TIME-TRAVEL"))

    assert "Unknown cross-system workflow type: UC-9.9-TIME-TRAVEL" in state["final_response"]
    assert state["next_node"] == "guardrails_out"
    assert hcm.leaves == [] and hcm.contact_updates == [] and itsm.created == []


async def test_the_workflow_defaults_to_medical_leave_when_none_is_named(node, hcm):
    state = await node.execute({"session_id": "s", "employee_id": "EMP-44210"})

    assert hcm.leaves[0]["leave_type"] == "Medical"
    assert state["saga_state"] == SagaWorkflowState.COMPLETED.value


def test_the_node_builds_its_own_collaborators_when_given_none():
    from src.core.agents.hcm import HCMSpecialistNode
    from src.core.agents.itsm import ITSMSpecialistNode
    from src.core.agents.policy import PolicySpecialistNode

    built = SagaCoordinatorNode()

    assert isinstance(built.ledger, SagaLedgerManager)
    assert isinstance(built.policy_agent, PolicySpecialistNode)
    assert isinstance(built.hcm_agent, HCMSpecialistNode)
    assert isinstance(built.itsm_agent, ITSMSpecialistNode)
    assert set(built.compensation_matrix.rollback_handlers) == {"UPDATE_CONTACT", "SUBMIT_LEAVE"}


# --- Path 4: UC-2.1 equipment procurement -------------------------------------


async def test_a_remote_employee_gets_a_hardware_request(node, itsm):
    state = await node.execute(_state("UC-2.1-EQUIPMENT"))

    assert itsm.created[0]["category"] == "Hardware Request"
    assert itsm.created[0]["caller_id"] == "EMP-44210"
    assert state["saga_state"] == SagaWorkflowState.COMPLETED.value
    assert "REQ-0001" in state["final_response"]


async def test_an_on_site_employee_is_refused_and_no_ticket_is_raised(itsm):
    """The entitlement is conditional on the profile, so the read gates the write."""
    on_site = FakeHCM(work_location="HYBRID")
    coordinator = SagaCoordinatorNode(
        ledger=SagaLedgerManager(in_memory=True),
        policy_agent=object(),
        hcm_agent=on_site,
        itsm_agent=itsm,
    )

    state = await coordinator.execute(_state("UC-2.1-EQUIPMENT"))

    assert itsm.created == []
    assert "restricted to remote-designated employees" in state["final_response"]
    assert state["saga_state"] == SagaWorkflowState.COMPLETED.value


async def test_the_entitlement_lookup_and_the_profile_read_are_both_recorded(node):
    """Both are READ_ONLY, so neither is compensable - but §4.6 still wants them
    in the ledger, because they are what the decision was based on."""
    state = await node.execute(_state("UC-2.1-EQUIPMENT"))

    steps = node.ledger.get_saga(state["saga_id"])["steps"]
    assert [s["targetSystem"] for s in steps[:2]] == ["Policy", "WorkWeek"]
    assert {s["compensationClass"] for s in steps[:2]} == {
        SagaCompensationClass.READ_ONLY.value
    }


async def test_a_hardware_ticket_failure_leaves_the_read_only_history_in_place(node):
    """Steps 1 and 2 read nothing into existence, so escalating is the whole of
    the compensation; there is no undo to perform."""
    state = await node.execute(
        _state("UC-2.1-EQUIPMENT", injected_faults={"step_3_fail": True})
    )

    assert state["saga_state"] == (
        SagaWorkflowState.PARTIALLY_COMPLETED_MANUAL_FOLLOWUP.value
    )
    assert "routed to the service operations team" in state["final_response"]
    assert [s.status for s in state["saga_ledger"][:2]] == [
        SagaStepStatus.SUCCESS,
        SagaStepStatus.SUCCESS,
    ]
    assert state["saga_ledger"][2].status == SagaStepStatus.FAILED_HANDED_TO_HUMAN
    assert state["next_node"] == "guardrails_out"


async def test_the_failed_hardware_step_carries_its_reason_and_follow_up_ref(node):
    state = await node.execute(
        _state("UC-2.1-EQUIPMENT", injected_faults={"step_3_fail": True})
    )

    failed = state["saga_ledger"][2]
    assert failed.error_message == "ITSM Gateway 503 Service Unavailable"
    assert failed.follow_up_ref.startswith("OPS-")
    assert failed.follow_up_ref in node.compensation_matrix.ops_queue[0]["followUpRef"]


# --- Path 5: UC-2.2 medical leave ---------------------------------------------


async def test_the_leave_is_filed_before_the_routing_ticket(node, hcm, itsm):
    state = await node.execute(_state("UC-2.2-MEDICAL-LEAVE"))

    assert hcm.leaves[0]["leave_type"] == "Medical"
    assert itsm.created[0]["category"] == "Access"
    assert "WW-LV-778899" in state["final_response"]
    assert state["saga_state"] == SagaWorkflowState.COMPLETED.value


@pytest.mark.parametrize("fault", ["step_2_fail", "itsm_503"])
async def test_a_routing_failure_never_un_files_the_medical_leave(node, hcm, fault):
    """The §5.4 rule in one assertion. Cancelling a filed medical leave because
    a mailbox-delegation ticket failed would put the employee's protected
    absence at risk to tidy up a clerical step."""
    state = await node.execute(_state("UC-2.2-MEDICAL-LEAVE", injected_faults={fault: True}))

    assert hcm.cancellations == []
    assert state["saga_ledger"][0].status == SagaStepStatus.SUCCESS
    assert state["saga_state"] == (
        SagaWorkflowState.PARTIALLY_COMPLETED_MANUAL_FOLLOWUP.value
    )


async def test_the_employee_is_told_their_leave_stands_and_needs_nothing_from_them(node):
    state = await node.execute(
        _state("UC-2.2-MEDICAL-LEAVE", injected_faults={"itsm_503": True})
    )

    assert "WW-LV-778899" in state["final_response"]
    assert "stands unaffected" in state["final_response"]
    assert "No further action is required from you" in state["final_response"]


async def test_the_operations_queue_carries_the_preserved_step_for_the_human(node):
    await node.execute(_state("UC-2.2-MEDICAL-LEAVE", injected_faults={"itsm_503": True}))

    task = node.compensation_matrix.ops_queue[0]
    assert task["severity"] == "P2"
    assert task["employeeId"] == "EMP-44210"
    assert task["preservedSteps"][0]["externalReferenceId"] == "WW-LV-778899"


# --- Path 6: UC-2.3 relocation ------------------------------------------------


async def test_the_address_is_updated_and_a_badge_ticket_raised(node, hcm, itsm):
    state = await node.execute(_state("UC-2.3-RELOCATION"))

    assert "London" in hcm.contact_updates[0]["address"]
    assert itsm.created[0]["category"] == "Facilities"
    assert state["saga_state"] == SagaWorkflowState.COMPLETED.value


async def test_the_previous_address_is_captured_before_it_is_overwritten(node):
    """Without the prior value stored at write time there is nothing to restore
    to, and the rollback would have to invent an address."""
    state = await node.execute(_state("UC-2.3-RELOCATION"))

    payload = node.ledger.get_saga(state["saga_id"])["steps"][0]["compensationPayload"]
    assert payload["previousAddress"] == "1 Raffles Place, Singapore 048616"
    assert payload["previousPhone"] == "+65 6555 0100"


@pytest.mark.parametrize("fault", ["step_2_fail", "facilities_ticket_fail"])
async def test_a_badge_failure_restores_the_previous_address(node, hcm, fault):
    """Both prior steps are REVERSIBLE_SAFE, so the whole saga is put back."""
    state = await node.execute(_state("UC-2.3-RELOCATION", injected_faults={fault: True}))

    assert hcm.contact_updates[-1]["address"] == "1 Raffles Place, Singapore 048616"
    assert hcm.contact_updates[-1]["phone"] == "+65 6555 0100"
    assert state["saga_state"] == SagaWorkflowState.COMPENSATED_ROLLED_BACK.value
    assert state["saga_ledger"][0].status == SagaStepStatus.ROLLED_BACK
    assert "safely restored" in state["final_response"]


# --- the rollback handlers in isolation ---------------------------------------


async def test_the_contact_rollback_restores_whatever_was_captured(node, hcm):
    step = SagaStepRecord(
        step_index=1,
        target_system="WorkWeek",
        action="UPDATE_CONTACT",
        compensation_class=SagaCompensationClass.REVERSIBLE_SAFE,
        status=SagaStepStatus.SUCCESS,
        compensation_payload={"previousAddress": "9 Old Road", "previousPhone": "+65 1"},
    )

    await node._rollback_update_contact(step, {"employee_id": "EMP-7"})

    assert hcm.contact_updates == [
        {"employee_id": "EMP-7", "address": "9 Old Road", "phone": "+65 1"}
    ]


async def test_a_contact_rollback_with_no_captured_payload_restores_nothing(node, hcm):
    """`None` for both fields is a no-op update in WorkWeek, which is the right
    outcome: better to leave the new value than to blank the record."""
    step = SagaStepRecord(
        step_index=1,
        target_system="WorkWeek",
        action="UPDATE_CONTACT",
        compensation_class=SagaCompensationClass.REVERSIBLE_SAFE,
        status=SagaStepStatus.SUCCESS,
    )

    await node._rollback_update_contact(step, {})

    assert hcm.contact_updates == [
        {"employee_id": "EMP-44210", "address": None, "phone": None}
    ]


async def test_the_leave_rollback_cancels_the_filing_it_was_given(node, hcm):
    """Only ever reached if a leave step were classified REVERSIBLE_SAFE, which
    UC-2.2 does not do - but the handler is registered, so it is tested."""
    step = SagaStepRecord(
        step_index=1,
        target_system="WorkWeek",
        action="SUBMIT_LEAVE",
        compensation_class=SagaCompensationClass.REVERSIBLE_SAFE,
        status=SagaStepStatus.SUCCESS,
        external_ref_id="WW-LV-000123",
    )

    await node._rollback_submit_leave(step, {"employee_id": "EMP-7"})

    assert hcm.cancellations == [("EMP-7", "WW-LV-000123")]


async def test_a_leave_rollback_without_a_reference_cancels_nothing(node, hcm):
    """No external reference means the filing never reached WorkWeek."""
    step = SagaStepRecord(
        step_index=1,
        target_system="WorkWeek",
        action="SUBMIT_LEAVE",
        compensation_class=SagaCompensationClass.REVERSIBLE_SAFE,
        status=SagaStepStatus.SUCCESS,
    )

    await node._rollback_submit_leave(step, {"employee_id": "EMP-7"})

    assert hcm.cancellations == []


# --- the compensation matrix directly -----------------------------------------


@pytest.fixture
def ledger() -> SagaLedgerManager:
    return SagaLedgerManager(in_memory=True)


@pytest.fixture
def matrix(ledger) -> SagaCompensationDecisionMatrix:
    return SagaCompensationDecisionMatrix(ledger=ledger)


def _record(ledger, saga_id, index, action, klass, status, ref=None):
    ledger.record_step(
        saga_id,
        SagaStepRecord(
            step_index=index,
            target_system="WorkWeek",
            action=action,
            compensation_class=klass,
            status=status,
            external_ref_id=ref,
        ),
    )


async def test_a_step_index_absent_from_the_ledger_is_an_error(matrix, ledger):
    """Compensating a step nobody recorded would mean guessing its class, and
    the class is precisely what decides whether an undo is permitted."""
    saga_id = ledger.init_saga("s", "EMP-1", "UC-2.3-RELOCATION")

    with pytest.raises(ValueError, match="Step 7 not found"):
        await matrix.handle_step_failure(saga_id, 7, "boom", {})


async def test_a_handler_can_be_registered_after_construction(matrix, ledger):
    seen = []

    async def _restore(step, state):
        seen.append(step)

    matrix.register_rollback_handler("UPDATE_CONTACT", _restore)

    saga_id = ledger.init_saga("s", "EMP-1", "UC-2.3-RELOCATION")
    _record(
        ledger, saga_id, 1, "UPDATE_CONTACT",
        SagaCompensationClass.REVERSIBLE_SAFE, SagaStepStatus.SUCCESS,
    )
    _record(
        ledger, saga_id, 2, "CREATE_FACILITIES_TICKET",
        SagaCompensationClass.REVERSIBLE_SAFE, SagaStepStatus.PENDING,
    )

    await matrix.handle_step_failure(saga_id, 2, "Facilities 500", {})

    assert [s.step_index for s in seen] == [1]


async def test_a_reversible_step_with_no_registered_handler_is_still_marked_back(
    matrix, ledger
):
    """The ledger is the record of intent. A missing handler is an integration
    gap, not a licence to leave the step reading as SUCCESS."""
    saga_id = ledger.init_saga("s", "EMP-1", "UC-2.3-RELOCATION")
    _record(
        ledger, saga_id, 1, "UPDATE_CONTACT",
        SagaCompensationClass.REVERSIBLE_SAFE, SagaStepStatus.SUCCESS,
    )
    _record(
        ledger, saga_id, 2, "CREATE_FACILITIES_TICKET",
        SagaCompensationClass.REVERSIBLE_SAFE, SagaStepStatus.PENDING,
    )

    resulting_state, _ = await matrix.handle_step_failure(saga_id, 2, "Facilities 500", {})

    steps = ledger.get_saga(saga_id)["steps"]
    assert steps[0]["status"] == SagaStepStatus.ROLLED_BACK.value
    assert resulting_state == SagaWorkflowState.COMPENSATED_ROLLED_BACK


async def test_a_failure_with_no_prior_steps_at_all_escalates(matrix, ledger):
    """Step 1 failing has nothing behind it, so there is no reversible history
    and the all-reversible branch must not claim it rolled anything back."""
    saga_id = ledger.init_saga("s", "EMP-1", "UC-2.3-RELOCATION")
    _record(
        ledger, saga_id, 1, "UPDATE_CONTACT",
        SagaCompensationClass.REVERSIBLE_SAFE, SagaStepStatus.PENDING,
    )

    resulting_state, message = await matrix.handle_step_failure(saga_id, 1, "WorkWeek 500", {})

    assert resulting_state == SagaWorkflowState.PARTIALLY_COMPLETED_MANUAL_FOLLOWUP
    assert "partially completed" in message


async def test_a_mixed_history_preserves_the_consequential_and_undoes_the_rest(ledger):
    """The §5.4 core case: one filing that must stand, one edit that need not."""
    rolled_back: list[str] = []

    async def _undo(step, state):
        rolled_back.append(step.action)

    matrix = SagaCompensationDecisionMatrix(
        ledger=ledger,
        rollback_handlers={"UPDATE_CONTACT": _undo, "SUBMIT_LEAVE": _undo},
    )
    saga_id = ledger.init_saga("s", "EMP-1", "UC-2.2-MEDICAL-LEAVE")
    _record(
        ledger, saga_id, 1, "SUBMIT_LEAVE",
        SagaCompensationClass.HUMAN_CONSEQUENTIAL, SagaStepStatus.SUCCESS, ref="WW-LV-1",
    )
    _record(
        ledger, saga_id, 2, "UPDATE_CONTACT",
        SagaCompensationClass.REVERSIBLE_SAFE, SagaStepStatus.SUCCESS,
    )
    _record(
        ledger, saga_id, 3, "CREATE_BADGE_TICKET",
        SagaCompensationClass.REVERSIBLE_SAFE, SagaStepStatus.PENDING,
    )

    resulting_state, message = await matrix.handle_step_failure(saga_id, 3, "500", {})

    assert rolled_back == ["UPDATE_CONTACT"]
    steps = ledger.get_saga(saga_id)["steps"]
    assert steps[0]["status"] == SagaStepStatus.SUCCESS.value
    assert steps[1]["status"] == SagaStepStatus.ROLLED_BACK.value
    assert resulting_state == SagaWorkflowState.PARTIALLY_COMPLETED_MANUAL_FOLLOWUP
    assert "Consequential records have been preserved" in message


async def test_an_ancillary_failure_quotes_the_first_prior_reference_it_finds(
    matrix, ledger
):
    """The employee is told which record stands. A step that produced no
    external reference is skipped rather than quoted as an empty one."""
    saga_id = ledger.init_saga("s", "EMP-1", "UC-2.2-MEDICAL-LEAVE")
    _record(
        ledger, saga_id, 1, "QUERY_POLICY",
        SagaCompensationClass.READ_ONLY, SagaStepStatus.SUCCESS,
    )
    _record(
        ledger, saga_id, 2, "SUBMIT_LEAVE",
        SagaCompensationClass.HUMAN_CONSEQUENTIAL, SagaStepStatus.SUCCESS, ref="WW-LV-42",
    )
    _record(
        ledger, saga_id, 3, "CREATE_ROUTING_TICKET",
        SagaCompensationClass.ANCILLARY, SagaStepStatus.PENDING,
    )

    _, message = await matrix.handle_step_failure(saga_id, 3, "ITSM 503", {})

    assert "Your primary request WW-LV-42 has been filed successfully" in message


async def test_an_ancillary_failure_with_no_references_omits_the_reference(matrix, ledger):
    saga_id = ledger.init_saga("s", "EMP-1", "UC-2.2-MEDICAL-LEAVE")
    _record(
        ledger, saga_id, 1, "QUERY_POLICY",
        SagaCompensationClass.READ_ONLY, SagaStepStatus.SUCCESS,
    )
    _record(
        ledger, saga_id, 2, "CREATE_ROUTING_TICKET",
        SagaCompensationClass.ANCILLARY, SagaStepStatus.PENDING,
    )

    _, message = await matrix.handle_step_failure(saga_id, 2, "ITSM 503", {})

    assert "Your primary request has been filed successfully" in message


async def test_only_successful_prior_steps_are_considered_for_rollback(matrix, ledger):
    """A step that failed changed nothing, so undoing it would be an edit."""
    saga_id = ledger.init_saga("s", "EMP-1", "UC-2.3-RELOCATION")
    _record(
        ledger, saga_id, 1, "UPDATE_CONTACT",
        SagaCompensationClass.REVERSIBLE_SAFE, SagaStepStatus.FAILED,
    )
    _record(
        ledger, saga_id, 2, "CREATE_FACILITIES_TICKET",
        SagaCompensationClass.REVERSIBLE_SAFE, SagaStepStatus.PENDING,
    )

    resulting_state, _ = await matrix.handle_step_failure(saga_id, 2, "500", {})

    assert ledger.get_saga(saga_id)["steps"][0]["status"] == SagaStepStatus.FAILED.value
    assert resulting_state == SagaWorkflowState.PARTIALLY_COMPLETED_MANUAL_FOLLOWUP
