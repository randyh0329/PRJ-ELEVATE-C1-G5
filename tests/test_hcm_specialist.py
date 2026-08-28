"""The WorkWeek HCM specialist: tool execution and response formatting (§3.2).

Two classes live in `src.core.agents.hcm`. `WorkWeekAutonomousSpecialist` is the
one on the REST path - it turns a tool name plus a loose argument dict into an
adapter call and then into prose. `HCMSpecialistNode` is the graph-path node,
which answers from its own seeded records.

The specialist is where server-side subject binding is enforced (SDD §4.1):
`caller_id` is passed as *both* the caller and the target on every adapter call,
so an `employee_id` the model invented cannot reach WorkWeek. The tests below
assert that on each of the six tools, because a single call that forwarded an
argument instead would be an FR-1.5 breach that nothing downstream would catch.

Date handling gets the same attention. `request_time_off` derives a start and an
end from whatever the model produced, and each fallback (missing, unparseable,
inverted, in the past) changes what a real employee gets booked.
"""

from __future__ import annotations

import datetime

import pytest

from src.core.agents.hcm import (
    WORKWEEK_TOOL_SCHEMAS,
    HCMSpecialistNode,
    WorkWeekAutonomousSpecialist,
    workweek_autonomous_specialist,
)
from src.integrations.workweek.models import (
    ContactUpdateResponse,
    EmployeeProfile,
    LeaveBalances,
    LeaveSubmissionResponse,
)
from src.models.routing import WorkWeekToolSelection

REF = datetime.date(2026, 3, 2)
CALLER = "EMP-1001"


def _profile(**overrides) -> EmployeeProfile:
    fields = {
        "employee_id": CALLER,
        "full_name": "Jane Doe",
        "email": "jane.doe@altostrat.com",
        "phone_number": "+65 6555 0100",
        "home_address": "1 Marina Bay, Singapore",
        "work_location_status": "HYBRID",
        "current_office": "Singapore HQ",
        "country": "SG",
        "job_title": "Staff Engineer",
        "manager_id": "EMP-2002",
    }
    fields.update(overrides)
    return EmployeeProfile(**fields)


def _balances(**overrides) -> LeaveBalances:
    fields = {
        "employee_id": CALLER,
        "vacation_accrued": 20.0,
        "vacation_used": 6.0,
        "vacation_remaining": 14.0,
        "sick_accrued": 14.0,
        "sick_used": 2.0,
        "sick_remaining": 12.0,
    }
    fields.update(overrides)
    return LeaveBalances(**fields)


class FakeClient:
    """Records every adapter call so the caller/target pair can be asserted."""

    def __init__(self, **behaviour):
        self.calls: list[tuple[str, dict]] = []
        self._behaviour = behaviour

    def _record(self, name, **kwargs):
        self.calls.append((name, kwargs))
        outcome = self._behaviour.get(name, "__unset__")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def get_employee_profile(self, caller_employee_id, target_employee_id):
        result = self._record(
            "get_employee_profile",
            caller_employee_id=caller_employee_id,
            target_employee_id=target_employee_id,
        )
        return _profile() if result == "__unset__" else result

    def get_leave_balances(self, caller_employee_id, target_employee_id):
        result = self._record(
            "get_leave_balances",
            caller_employee_id=caller_employee_id,
            target_employee_id=target_employee_id,
        )
        return _balances() if result == "__unset__" else result

    def get_leave_requests(self, caller_employee_id, target_employee_id):
        result = self._record(
            "get_leave_requests",
            caller_employee_id=caller_employee_id,
            target_employee_id=target_employee_id,
        )
        return [] if result == "__unset__" else result

    def submit_leave_request(self, **kwargs):
        result = self._record("submit_leave_request", **kwargs)
        if result == "__unset__":
            return LeaveSubmissionResponse(
                success=True, request_id="4012", message="Submitted.", remaining_balance=11.0
            )
        return result

    def cancel_leave_request(self, caller_employee_id, request_id):
        result = self._record(
            "cancel_leave_request",
            caller_employee_id=caller_employee_id,
            request_id=request_id,
        )
        return True if result == "__unset__" else result

    def update_contact_info(self, **kwargs):
        result = self._record("update_contact_info", **kwargs)
        if result == "__unset__":
            return ContactUpdateResponse(
                success=True,
                employee_id=CALLER,
                message="Updated.",
                updated_fields={"phone_number": "+65 6555 0101"},
            )
        return result

    def last(self, name: str) -> dict:
        return next(kwargs for called, kwargs in reversed(self.calls) if called == name)


class FakeLLM:
    """Stands in for Gemini's function-calling round-trip."""

    def __init__(self, selection: WorkWeekToolSelection):
        self.selection = selection
        self.prompts: list[str] = []

    def select_workweek_tool(self, prompt, reference_date=None):
        self.prompts.append(prompt)
        self.reference_date = reference_date
        return self.selection


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


def make_specialist(client, llm=None) -> WorkWeekAutonomousSpecialist:
    return WorkWeekAutonomousSpecialist(client=client, llm_client=llm or object())


# --- the tool registry --------------------------------------------------------


def test_every_declared_schema_is_a_tool_the_specialist_can_execute(client):
    """A schema the executor has no branch for would fail only at runtime."""
    specialist = make_specialist(client)

    for schema in WORKWEEK_TOOL_SCHEMAS:
        result = specialist.execute_tool(schema["name"], {}, CALLER, REF)

        assert result.get("message") != f"Unknown tool '{schema['name']}'."


def test_no_schema_accepts_an_employee_id_argument():
    """§4.1 subject binding: the model must have no way to name a subject."""
    for schema in WORKWEEK_TOOL_SCHEMAS:
        assert "employee_id" not in schema["parameters"].get("properties", {})


def test_the_module_singleton_is_wired_to_the_shared_adapter():
    from src.integrations.workweek.client import workweek_client

    assert workweek_autonomous_specialist.client is workweek_client


def test_an_unspecified_llm_defaults_to_the_vertex_client(client):
    from src.integrations.vertex.client import vertex_gemini_client

    assert WorkWeekAutonomousSpecialist(client=client)._llm is vertex_gemini_client


def test_an_unspecified_client_defaults_to_the_shared_adapter():
    from src.integrations.workweek.client import workweek_client

    assert WorkWeekAutonomousSpecialist(llm_client=object()).client is workweek_client


# --- get_employee_balances ----------------------------------------------------


def test_balances_are_read_for_the_caller_and_only_the_caller(client):
    result = make_specialist(client).execute_tool("get_employee_balances", {}, CALLER, REF)

    assert client.last("get_leave_balances") == {
        "caller_employee_id": CALLER,
        "target_employee_id": CALLER,
    }
    assert result["vacation_remaining"] == 14.0
    assert result["sick_used"] == 2.0


def test_an_adapter_that_returns_no_balances_is_an_error_not_a_zero():
    """Reporting "0 days remaining" for a failed read would be a wrong answer."""
    specialist = make_specialist(FakeClient(get_leave_balances=None))

    result = specialist.execute_tool("get_employee_balances", {}, CALLER, REF)

    assert result["status"] == "ERROR"
    assert "balances" in result["message"]


# --- get_leave_requests -------------------------------------------------------


def test_leave_requests_are_returned_with_their_count(client):
    client._behaviour["get_leave_requests"] = [{"request_id": "4012"}, {"request_id": "4013"}]

    result = make_specialist(client).execute_tool("get_leave_requests", {}, CALLER, REF)

    assert result["count"] == 2
    assert client.last("get_leave_requests")["target_employee_id"] == CALLER


def test_no_leave_requests_is_a_successful_empty_answer(client):
    result = make_specialist(client).execute_tool("get_leave_requests", {}, CALLER, REF)

    assert result == {"status": "SUCCESS", "requests": [], "count": 0}


# --- request_time_off ---------------------------------------------------------


def test_the_dates_the_employee_gave_are_the_dates_submitted(client):
    result = make_specialist(client).execute_tool(
        "request_time_off",
        {"start_date": "2026-04-01", "end_date": "2026-04-03", "days": 3},
        CALLER,
        REF,
    )

    call = client.last("submit_leave_request")
    assert call["start_date"] == datetime.date(2026, 4, 1)
    assert call["end_date"] == datetime.date(2026, 4, 3)
    assert call["days"] == 3.0
    assert result["request_id"] == "4012"


@pytest.mark.parametrize("leave_type", ["sick", "Sick leave", "medical", "병가"])
def test_sick_leave_is_recognised_however_it_is_worded(client, leave_type):
    make_specialist(client).execute_tool(
        "request_time_off", {"leave_type": leave_type, "days": 1}, CALLER, REF
    )

    assert client.last("submit_leave_request")["leave_type"] == "Sick"


def test_anything_that_is_not_sick_leave_is_booked_as_vacation(client):
    make_specialist(client).execute_tool(
        "request_time_off", {"leave_type": "Annual", "days": 1}, CALLER, REF
    )

    assert client.last("submit_leave_request")["leave_type"] == "Vacation"


def test_a_missing_start_date_defaults_to_tomorrow(client):
    make_specialist(client).execute_tool("request_time_off", {"days": 1}, CALLER, REF)

    assert client.last("submit_leave_request")["start_date"] == datetime.date(2026, 3, 3)


def test_an_unparseable_start_date_falls_back_rather_than_raising(client):
    """The model writes these; "next Monday" is an expected input, not a fault."""
    make_specialist(client).execute_tool(
        "request_time_off", {"start_date": "next Monday", "days": 1}, CALLER, REF
    )

    assert client.last("submit_leave_request")["start_date"] == datetime.date(2026, 3, 3)


def test_a_missing_end_date_is_derived_from_the_day_count(client):
    make_specialist(client).execute_tool(
        "request_time_off", {"start_date": "2026-04-01", "days": 3}, CALLER, REF
    )

    call = client.last("submit_leave_request")
    assert call["end_date"] == datetime.date(2026, 4, 3)


def test_an_unusable_end_date_does_not_discard_a_good_start_date(client):
    """The bug this guards: one `except` around both parses moved the start too."""
    make_specialist(client).execute_tool(
        "request_time_off",
        {"start_date": "2026-04-01", "end_date": "the Friday after", "days": 2},
        CALLER,
        REF,
    )

    call = client.last("submit_leave_request")
    assert call["start_date"] == datetime.date(2026, 4, 1)
    assert call["end_date"] == datetime.date(2026, 4, 2)


def test_an_end_date_before_the_start_is_recomputed_from_the_day_count(client):
    make_specialist(client).execute_tool(
        "request_time_off",
        {"start_date": "2026-04-10", "end_date": "2026-04-02", "days": 2},
        CALLER,
        REF,
    )

    call = client.last("submit_leave_request")
    assert call["start_date"] == datetime.date(2026, 4, 10)
    assert call["end_date"] == datetime.date(2026, 4, 11)


def test_a_start_date_in_the_past_is_pulled_forward_to_today(client):
    """Backdating leave is not something the employee can ask the agent to do."""
    make_specialist(client).execute_tool(
        "request_time_off",
        {"start_date": "2026-01-05", "end_date": "2026-01-07", "days": 3},
        CALLER,
        REF,
    )

    call = client.last("submit_leave_request")
    assert call["start_date"] == REF
    assert call["end_date"] == datetime.date(2026, 3, 4)


def test_the_business_reference_date_is_passed_through_to_the_adapter(client):
    """The adapter re-checks the past-date rule against the same day (§2.2)."""
    make_specialist(client).execute_tool("request_time_off", {"days": 1}, CALLER, REF)

    assert client.last("submit_leave_request")["reference_date"] == REF


def test_a_rejected_submission_is_reported_as_failed_not_errored(client):
    """A guardrail rejection is a business answer; the employee needs the reason."""
    client._behaviour["submit_leave_request"] = LeaveSubmissionResponse(
        success=False, message="Insufficient balance.", remaining_balance=1.0
    )

    result = make_specialist(client).execute_tool(
        "request_time_off", {"days": 5}, CALLER, REF
    )

    assert result["status"] == "FAILED"
    assert result["message"] == "Insufficient balance."


# --- cancel_leave_request -----------------------------------------------------


def test_a_cancellation_names_the_request_and_the_caller(client):
    result = make_specialist(client).execute_tool(
        "cancel_leave_request", {"request_id": 4012}, CALLER, REF
    )

    assert client.last("cancel_leave_request") == {
        "caller_employee_id": CALLER,
        "request_id": "4012",
    }
    assert result["status"] == "SUCCESS"


@pytest.mark.parametrize("arguments", [{}, {"request_id": ""}, {"request_id": "   "}])
def test_a_cancellation_without_a_reference_never_reaches_the_adapter(client, arguments):
    result = make_specialist(client).execute_tool("cancel_leave_request", arguments, CALLER, REF)

    assert result["status"] == "ERROR"
    assert client.calls == []


def test_a_refused_cancellation_says_so(client):
    client._behaviour["cancel_leave_request"] = False

    result = make_specialist(client).execute_tool(
        "cancel_leave_request", {"request_id": "4012"}, CALLER, REF
    )

    assert result["status"] == "FAILED"
    assert "Failed to cancel" in result["message"]


# --- update_personal_info -----------------------------------------------------


def test_a_contact_update_forwards_only_the_fields_supplied(client):
    result = make_specialist(client).execute_tool(
        "update_personal_info", {"phone_number": "+65 6555 0101"}, CALLER, REF
    )

    call = client.last("update_contact_info")
    assert call["phone_number"] == "+65 6555 0101"
    assert call["home_address"] is None
    assert call["caller_employee_id"] == call["target_employee_id"] == CALLER
    assert result["status"] == "SUCCESS"


def test_a_rejected_contact_update_is_reported_as_failed(client):
    client._behaviour["update_contact_info"] = ContactUpdateResponse(
        success=False, employee_id=CALLER, message="Address failed validation.", updated_fields={}
    )

    result = make_specialist(client).execute_tool(
        "update_personal_info", {"home_address": "x"}, CALLER, REF
    )

    assert result["status"] == "FAILED"
    assert result["message"] == "Address failed validation."


# --- get_employee_profile -----------------------------------------------------


def test_the_profile_is_flattened_into_the_tool_result(client):
    result = make_specialist(client).execute_tool("get_employee_profile", {}, CALLER, REF)

    assert result["department"] == "Singapore HQ"
    assert result["manager_id"] == "EMP-2002"
    assert result["home_address"] == "1 Marina Bay, Singapore"


def test_a_missing_profile_is_an_error(client):
    client._behaviour["get_employee_profile"] = None

    result = make_specialist(client).execute_tool("get_employee_profile", {}, CALLER, REF)

    assert result == {"status": "ERROR", "message": "Profile not found."}


# --- unknown tools and adapter failures ---------------------------------------


def test_a_tool_the_specialist_does_not_implement_is_refused(client):
    result = make_specialist(client).execute_tool("delete_employee", {}, CALLER, REF)

    assert result["status"] == "ERROR"
    assert "Unknown tool" in result["message"]


def test_an_adapter_that_raises_becomes_an_error_result_not_a_crash(client):
    """A FastMCP timeout must surface as a message, not a 500 from the API."""
    client._behaviour["get_leave_balances"] = RuntimeError("FastMCP token expired")

    result = make_specialist(client).execute_tool("get_employee_balances", {}, CALLER, REF)

    assert result == {"status": "ERROR", "message": "FastMCP token expired"}


def test_the_reference_date_defaults_to_the_business_day(client, monkeypatch):
    """§2.2: "today" is Singapore's today, not the serving region's."""
    monkeypatch.setattr("src.core.agents.hcm.business_today", lambda: datetime.date(2026, 6, 1))

    make_specialist(client).execute_tool("request_time_off", {"days": 1}, CALLER)

    assert client.last("submit_leave_request")["reference_date"] == datetime.date(2026, 6, 1)


# --- date parsing -------------------------------------------------------------


@pytest.mark.parametrize("value", [None, "", 0])
def test_an_absent_date_parses_to_nothing(value):
    assert WorkWeekAutonomousSpecialist._parse_date(value) is None


@pytest.mark.parametrize("value", ["tomorrow", "2026-13-01", "01/04/2026", object()])
def test_an_unusable_date_parses_to_nothing(value):
    assert WorkWeekAutonomousSpecialist._parse_date(value) is None


def test_an_iso_date_parses_to_that_date():
    assert WorkWeekAutonomousSpecialist._parse_date("2026-04-01") == datetime.date(2026, 4, 1)


# --- plan_and_execute ---------------------------------------------------------


def test_the_selected_tool_is_executed_with_the_extracted_arguments(client):
    llm = FakeLLM(
        WorkWeekToolSelection(
            tool_name="cancel_leave_request", reasoning="Cancellation.", request_id="4012"
        )
    )

    result = make_specialist(client, llm).plan_and_execute("cancel 4012", CALLER, REF)

    assert client.last("cancel_leave_request")["request_id"] == "4012"
    assert result["action_performed"] == "CANCEL_LEAVE"
    assert llm.reference_date == REF


def test_a_conversational_turn_calls_no_tool_at_all(client):
    llm = FakeLLM(
        WorkWeekToolSelection(
            tool_name="none", reasoning="Greeting.", direct_response="Hello - how can I help?"
        )
    )

    result = make_specialist(client, llm).plan_and_execute("hi", CALLER, REF)

    assert result["response_text"] == "Hello - how can I help?"
    assert result["action_performed"] == "CONVERSATION"
    assert client.calls == []


def test_a_conversational_turn_with_nothing_to_say_still_answers(client):
    llm = FakeLLM(WorkWeekToolSelection(tool_name="none", reasoning="Unclear."))

    result = make_specialist(client, llm).plan_and_execute("...", CALLER, REF)

    assert "WorkWeek self-service" in result["response_text"]


def test_planning_defaults_its_reference_date_to_the_business_day(client, monkeypatch):
    monkeypatch.setattr("src.core.agents.hcm.business_today", lambda: datetime.date(2026, 6, 1))
    llm = FakeLLM(WorkWeekToolSelection(tool_name="none", reasoning="Greeting."))

    make_specialist(client, llm).plan_and_execute("hi", CALLER)

    assert llm.reference_date == datetime.date(2026, 6, 1)


# --- the fast path and its formatting -----------------------------------------


def test_an_adapter_error_short_circuits_before_formatting(client):
    client._behaviour["get_leave_balances"] = RuntimeError("connection refused")

    result = make_specialist(client).execute_fast_path("get_employee_balances", {}, CALLER, REF)

    assert result["action_performed"] == "ERROR"
    assert "connection refused" in result["response_text"]
    assert result["transaction_reference"] is None


def test_the_fast_path_defaults_its_reference_date_too(client, monkeypatch):
    monkeypatch.setattr("src.core.agents.hcm.business_today", lambda: datetime.date(2026, 6, 1))

    make_specialist(client).execute_fast_path("request_time_off", {"days": 1}, CALLER)

    assert client.last("submit_leave_request")["reference_date"] == datetime.date(2026, 6, 1)


def test_a_successful_cancellation_confirms_the_refund(client):
    result = make_specialist(client).execute_fast_path(
        "cancel_leave_request", {"request_id": "4012"}, CALLER, REF
    )

    assert "#4012" in result["response_text"]
    assert "refunded" in result["response_text"]
    assert result["transaction_reference"] == "CANCEL-4012"


def test_a_failed_cancellation_surfaces_the_reason(client):
    client._behaviour["cancel_leave_request"] = False

    result = make_specialist(client).execute_fast_path(
        "cancel_leave_request", {"request_id": "4012"}, CALLER, REF
    )

    assert "Failed to cancel leave request #4012" in result["response_text"]
    assert result["action_performed"] == "CANCEL_LEAVE"


def test_a_cancellation_with_no_reference_anywhere_has_no_transaction_id(client):
    formatted = make_specialist(client)._format_tool_response(
        "cancel_leave_request", {}, {"status": "SUCCESS"}
    )

    assert formatted["transaction_reference"] is None


def test_an_empty_leave_history_reads_as_a_sentence_not_a_blank_list(client):
    result = make_specialist(client).execute_fast_path("get_leave_requests", {}, CALLER, REF)

    assert result["response_text"] == "You currently have no leave requests registered in WorkWeek."
    assert result["action_performed"] == "LIST_LEAVE_REQUESTS"


def test_each_leave_request_is_listed_with_its_dates_and_type(client):
    client._behaviour["get_leave_requests"] = [
        {
            "request_id": "4012",
            "start_date": "2026-04-01",
            "end_date": "2026-04-03",
            "days": 3,
            "leave_type": "Vacation",
        }
    ]

    text = make_specialist(client).execute_fast_path(
        "get_leave_requests", {}, CALLER, REF
    )["response_text"]

    assert "(1 total)" in text
    assert "- Request #4012: 2026-04-01 to 2026-04-03 (3 days, Vacation)" in text


def test_a_contact_update_names_the_fields_that_changed(client):
    result = make_specialist(client).execute_fast_path(
        "update_personal_info",
        {"home_address": "2 Raffles Place, Singapore", "phone_number": "+65 6555 0101"},
        CALLER,
        REF,
    )

    assert "address: '2 Raffles Place, Singapore'" in result["response_text"]
    assert "phone: '+65 6555 0101'" in result["response_text"]
    assert result["action_performed"] == "UPDATE_CONTACT"


def test_a_contact_update_with_no_named_field_still_confirms(client):
    """Reachable when the adapter succeeded on values the router did not echo."""
    formatted = make_specialist(client)._format_tool_response(
        "update_personal_info", {}, {"status": "SUCCESS"}
    )

    assert "contact details" in formatted["response_text"]


def test_a_failed_contact_update_reports_the_adapter_message(client):
    client._behaviour["update_contact_info"] = ContactUpdateResponse(
        success=False, employee_id=CALLER, message="Phone number rejected.", updated_fields={}
    )

    result = make_specialist(client).execute_fast_path(
        "update_personal_info", {"phone_number": "12"}, CALLER, REF
    )

    assert "Phone number rejected." in result["response_text"]


@pytest.mark.parametrize(
    ("field", "action", "expected"),
    [
        ("manager", "CHECK_MANAGER", "EMP-2002"),
        ("department", "CHECK_DEPARTMENT", "Singapore HQ"),
        ("phone", "CHECK_PHONE", "+65 6555 0100"),
        ("address", "CHECK_ADDRESS", "1 Marina Bay, Singapore"),
    ],
)
def test_a_single_profile_field_is_answered_on_its_own(client, field, action, expected):
    """Answering a "who is my manager?" with the whole profile is over-disclosure."""
    result = make_specialist(client).execute_fast_path(
        "get_employee_profile", {"field": field}, CALLER, REF
    )

    assert expected in result["response_text"]
    assert result["action_performed"] == action


def test_the_whole_profile_is_rendered_when_no_field_is_named(client):
    result = make_specialist(client).execute_fast_path("get_employee_profile", {}, CALLER, REF)

    assert result["action_performed"] == "CHECK_PROFILE"
    for expected in ("Jane Doe", "Staff Engineer", "HYBRID", "EMP-2002"):
        assert expected in result["response_text"]


def test_balances_are_rendered_with_accrued_and_used_alongside_remaining(client):
    result = make_specialist(client).execute_fast_path("get_employee_balances", {}, CALLER, REF)

    assert "14.0 days remaining (20.0 accrued, 6.0 used)" in result["response_text"]
    assert "12.0 days remaining (14.0 accrued, 2.0 used)" in result["response_text"]
    assert result["action_performed"] == "CHECK_BALANCE"


def test_a_submitted_request_reports_its_reference_and_new_balance(client):
    result = make_specialist(client).execute_fast_path(
        "request_time_off",
        {"start_date": "2026-04-01", "end_date": "2026-04-03", "days": 3},
        CALLER,
        REF,
    )

    assert "[4012]" in result["response_text"]
    assert "Remaining balance: 11.0 days" in result["response_text"]
    assert result["transaction_reference"] == "4012"


def test_a_rejected_request_reports_why_and_carries_no_reference(client):
    client._behaviour["submit_leave_request"] = LeaveSubmissionResponse(
        success=False, message="Insufficient balance."
    )

    result = make_specialist(client).execute_fast_path("request_time_off", {"days": 99}, CALLER, REF)

    assert result["response_text"] == "Leave submission failed: Insufficient balance."
    assert result["transaction_reference"] is None


def test_a_tool_with_no_formatter_still_returns_a_usable_envelope(client):
    """Defensive: every caller reads `response_text`, so it can never be absent."""
    formatted = make_specialist(client)._format_tool_response(
        "some_future_tool", {}, {"status": "SUCCESS"}
    )

    assert formatted["action_performed"] == "UNKNOWN"
    assert formatted["response_text"]


# --- the graph-path node ------------------------------------------------------


def test_the_node_returns_a_seeded_profile_by_employee_id():
    assert HCMSpecialistNode().get_profile("EMP-44210")["name"] == "Sarah Chen"


def test_an_unknown_employee_gets_a_placeholder_profile_rather_than_an_error():
    profile = HCMSpecialistNode().get_profile("EMP-9999")

    assert profile["employeeId"] == "EMP-9999"
    assert profile["email"] == "emp-9999@elevate-corp.internal"


def test_seeded_and_unseeded_balances_both_resolve():
    node = HCMSpecialistNode()

    assert node.get_balances("EMP-10022")["vacation"]["remainingHours"] == 40.0
    assert node.get_balances("EMP-9999")["sick"]["remainingHours"] == 80.0


def test_a_contact_update_records_the_previous_values_for_compensation():
    """§5.4 REVERSIBLE_SAFE: the saga can only undo what it captured first."""
    node = HCMSpecialistNode()

    result = node.update_contact("EMP-44210", new_address="1 Marina Bay, Singapore")

    assert result["previousAddress"] == "742 Evergreen Terrace, Springfield, OR"
    assert result["currentAddress"] == "1 Marina Bay, Singapore"
    assert result["updated"] == ["homeAddress"]


def test_updating_only_the_phone_leaves_the_address_untouched():
    node = HCMSpecialistNode()

    result = node.update_contact("EMP-44210", new_phone="+65 6555 0100")

    assert result["updated"] == ["phoneNumber"]
    assert result["currentAddress"] == "742 Evergreen Terrace, Springfield, OR"


def test_an_update_naming_nothing_changes_nothing():
    result = HCMSpecialistNode().update_contact("EMP-44210")

    assert result["updated"] == []
    assert result["currentPhone"] == result["previousPhone"]


def test_a_submitted_leave_starts_pending_approval():
    """HUMAN_CONSEQUENTIAL: nothing is booked without an approver (§5.4)."""
    result = HCMSpecialistNode().submit_leave("EMP-44210", "Vacation", "2026-04-01", "2026-04-03", 3)

    assert result["leaveStatus"] == "PENDING_APPROVAL"
    assert result["leaveId"].startswith("LV-")


def test_a_submitted_leave_can_be_cancelled_by_its_id():
    node = HCMSpecialistNode()
    leave_id = node.submit_leave("EMP-44210", "Vacation", "2026-04-01", "2026-04-03", 3)["leaveId"]

    assert node.cancel_leave("EMP-44210", leave_id) == {
        "status": "SUCCESS",
        "cancelledLeaveId": leave_id,
    }
    assert node._leaves[leave_id]["status"] == "CANCELLED"


def test_cancelling_a_leave_that_was_never_submitted_is_not_found():
    assert HCMSpecialistNode().cancel_leave("EMP-44210", "LV-0000") == {"status": "NOT_FOUND"}


@pytest.mark.parametrize("query", ["What is my PTO balance?", "how much pto do i have"])
async def test_a_balance_question_is_answered_from_the_balance_record(query):
    state = {"employee_id": "EMP-44210", "user_input": query}

    result = await HCMSpecialistNode().execute(state)

    assert "120.0 hours" in result["final_response"]
    assert "80.0 hours" in result["final_response"]
    assert result["next_node"] == "guardrails_out"


async def test_any_other_question_is_answered_from_the_profile():
    state = {"employee_id": "EMP-10022", "user_input": "Where do I work?"}

    result = await HCMSpecialistNode().execute(state)

    assert "David Miller" in result["final_response"]
    assert "ON_SITE" in result["final_response"]


async def test_the_masked_input_is_what_the_node_reads():
    """§4.4: the node must never see the raw text the DLP gate rewrote."""
    state = {
        "employee_id": "EMP-44210",
        "user_input": "my balance, call +6512345678",
        "masked_input": "profile please",
    }

    result = await HCMSpecialistNode().execute(state)

    assert "WorkWeek Profile" in result["final_response"]


async def test_a_request_without_a_subject_falls_back_to_the_demo_employee():
    result = await HCMSpecialistNode().execute({"user_input": "balance"})

    assert "120.0 hours" in result["final_response"]
