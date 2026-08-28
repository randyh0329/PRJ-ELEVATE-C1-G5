"""The routing schemas, and the argument consolidation both of them perform.

`SupervisorRoutingDecision` is the supervisor's structured output (§3.1): it
classifies the intent *and* extracts tool parameters in the same turn, so the
fast path in `HREnterpriseAgent._handle_workweek_leave` can skip a second LLM
round-trip. `WorkWeekToolSelection` is the specialist's equivalent (§3.2).

Both flatten a set of typed optional fields into one argument dict, and the
same rule governs both: a field the model did not fill must not appear in the
arguments at all. An absent key means "not supplied"; a key holding None would
be forwarded to the tool as an explicit null and overwrite what is on file.
`days=0.0` is the case that separates the two - falsy, but supplied.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.models.routing import SupervisorRoutingDecision, WorkWeekToolSelection


def _decision(**overrides) -> SupervisorRoutingDecision:
    fields = {
        "intent": "UC_1_2_WORKWEEK_LEAVE",
        "target_agent": "WORKWEEK_SPECIALIST",
        "reasoning": "Employee is asking to book leave.",
    }
    fields.update(overrides)
    return SupervisorRoutingDecision(**fields)


def _selection(**overrides) -> WorkWeekToolSelection:
    fields = {"tool_name": "request_time_off", "reasoning": "Leave booking."}
    fields.update(overrides)
    return WorkWeekToolSelection(**fields)


# --- schema defaults and validation ------------------------------------------


def test_a_decision_defaults_to_high_confidence_and_no_tool():
    decision = _decision()

    assert decision.confidence == 0.95
    assert decision.tool_name == "none"
    assert decision.extracted_action is None


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_confidence_outside_zero_to_one_is_rejected(confidence):
    with pytest.raises(ValidationError):
        _decision(confidence=confidence)


def test_an_intent_outside_the_mvp_use_cases_is_rejected():
    """The router's output is a closed set; a new intent is a code change."""
    with pytest.raises(ValidationError):
        _decision(intent="UC_9_9_PAYROLL")


def test_delegating_to_an_unregistered_agent_is_rejected():
    with pytest.raises(ValidationError):
        _decision(target_agent="PAYROLL_SPECIALIST")


def test_an_unregistered_tool_name_is_rejected():
    """FR-1.1: the model may only name a tool from the registry."""
    with pytest.raises(ValidationError):
        _decision(tool_name="delete_employee")


def test_reasoning_is_required_of_the_supervisor():
    """Every routing decision has to be explainable in the audit record."""
    with pytest.raises(ValidationError):
        SupervisorRoutingDecision(intent="OUT_OF_DOMAIN", target_agent="DOMAIN_CONTAINMENT")


def test_a_selection_defaults_to_an_empty_argument_dict():
    selection = _selection(tool_name="none")

    assert selection.arguments == {}
    assert selection.direct_response is None


# --- consolidating the supervisor's extracted parameters ---------------------


def test_fields_the_router_did_not_fill_are_absent_from_the_arguments():
    assert _decision().get_tool_arguments() == {}


def test_every_extracted_leave_parameter_is_carried_through():
    decision = _decision(
        tool_name="request_time_off",
        start_date="2026-09-01",
        end_date="2026-09-03",
        days=3.0,
        leave_type="Vacation",
        reason="Family trip",
    )

    assert decision.get_tool_arguments() == {
        "start_date": "2026-09-01",
        "end_date": "2026-09-03",
        "days": 3.0,
        "leave_type": "Vacation",
        "reason": "Family trip",
    }


def test_a_zero_day_request_is_still_a_supplied_value():
    """Dropping it would turn a guardrail rejection into an unbounded request."""
    assert _decision(days=0.0).get_tool_arguments() == {"days": 0.0}


def test_a_cancellation_carries_only_its_reference():
    decision = _decision(tool_name="cancel_leave_request", request_id="4012")

    assert decision.get_tool_arguments() == {"request_id": "4012"}


def test_a_contact_update_carries_only_the_fields_the_employee_named():
    decision = _decision(tool_name="update_personal_info", phone_number="+65 6555 0100")

    assert decision.get_tool_arguments() == {"phone_number": "+65 6555 0100"}


def test_a_relocation_carries_the_new_address():
    decision = _decision(
        tool_name="update_personal_info", home_address="2 Raffles Place, Singapore"
    )

    assert decision.get_tool_arguments() == {"home_address": "2 Raffles Place, Singapore"}


def test_an_empty_string_is_treated_as_not_supplied():
    """The router emits "" for a field it could not find; forwarding that would
    blank the value held in WorkWeek."""
    decision = _decision(home_address="", phone_number="", leave_type="", reason="", request_id="")

    assert decision.get_tool_arguments() == {}


# --- consolidating the specialist's selection --------------------------------


def test_generic_arguments_are_the_base_of_the_effective_set():
    selection = _selection(arguments={"employee_id": "EMP-1001"})

    assert selection.get_effective_arguments() == {"employee_id": "EMP-1001"}


def test_typed_fields_override_the_generic_argument_dict():
    """The typed field went through validation; the loose dict did not."""
    selection = _selection(
        arguments={"start_date": "yesterday", "employee_id": "EMP-1001"},
        start_date="2026-09-01",
    )

    assert selection.get_effective_arguments() == {
        "start_date": "2026-09-01",
        "employee_id": "EMP-1001",
    }


def test_consolidating_does_not_mutate_the_arguments_the_model_returned():
    selection = _selection(arguments={"employee_id": "EMP-1001"}, days=3.0)

    selection.get_effective_arguments()

    assert selection.arguments == {"employee_id": "EMP-1001"}


def test_every_specialist_field_is_carried_through():
    selection = _selection(
        start_date="2026-09-01",
        end_date="2026-09-03",
        days=3.0,
        leave_type="Sick",
        reason="Medical",
        request_id="4012",
        home_address="2 Raffles Place, Singapore",
        phone_number="+65 6555 0100",
    )

    assert selection.get_effective_arguments() == {
        "start_date": "2026-09-01",
        "end_date": "2026-09-03",
        "days": 3.0,
        "leave_type": "Sick",
        "reason": "Medical",
        "request_id": "4012",
        "home_address": "2 Raffles Place, Singapore",
        "phone_number": "+65 6555 0100",
    }


def test_a_zero_day_specialist_request_is_also_supplied():
    assert _selection(days=0.0).get_effective_arguments() == {"days": 0.0}


def test_a_none_argument_dict_consolidates_to_an_empty_one():
    selection = _selection()
    selection.arguments = None

    assert selection.get_effective_arguments() == {}


# --- what the turn did not do -------------------------------------------------
#
# One turn is classified as one intent and dispatched to one specialist, so the
# second request in `my laptop is broken, open a ticket, and I need sick leave
# 10/01-10/03` is not served. That is a documented limit. What made it a defect
# is that it was not *said*: the employee received a confident ticket
# confirmation, nothing about the leave, and no reason to suspect that half
# their sentence had been read and dropped.


def test_the_ordinary_single_request_turn_says_nothing_extra():
    """This runs on every turn. Silence has to be the default, not a special case."""
    assert _decision().unaddressed_note() == ""


def test_a_dropped_request_is_named_in_the_reply():
    note = _decision(
        unaddressed_requests=["a sick-leave request for 2026-10-01 to 2026-10-03"]
    ).unaddressed_note()

    assert "a sick-leave request for 2026-10-01 to 2026-10-03" in note
    assert "Still outstanding" in note


def test_more_than_one_dropped_request_is_listed_rather_than_summarised():
    note = _decision(
        unaddressed_requests=["a sick-leave request for 2026-10-01", "a badge replacement"]
    ).unaddressed_note()

    assert "a sick-leave request for 2026-10-01; a badge replacement" in note


def test_the_note_tells_the_employee_what_to_do_next():
    """A disclosure that leaves them wondering whether to wait is half a fix."""
    note = _decision(unaddressed_requests=["a leave request"]).unaddressed_note()

    assert "Send it to me on its own" in note


def test_the_note_is_appended_not_substituted():
    """The half that ran really did run; its receipt is still owed."""
    note = _decision(unaddressed_requests=["a leave request"]).unaddressed_note()

    assert note.startswith("\n\n")


@pytest.mark.parametrize("requests", [[], ["", "   "], [""]])
def test_an_empty_or_blank_list_produces_no_note(requests):
    """A model that fills the field with an empty string has told us nothing, and
    `Still outstanding: .` is worse than saying nothing at all."""
    assert _decision(unaddressed_requests=requests).unaddressed_note() == ""
