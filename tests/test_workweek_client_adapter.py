"""The WorkWeek client adapter: caller isolation, the live/mock split, audit trail.

`tests/test_workweek_flow.py` drives this through the mock service, which is the
path taken for every employee except EMP-509. The live FastMCP branch - the one
production actually runs - was reachable only from the integration test that
skips without a working token, so the response mapping, the merge-before-update
read and the error wrapping were all untested.

The adapter's real job is not transport, it is the three things layered on top:
FR-1.5 caller isolation on every method, a guardrail check before any write, and
an audit record for every outcome including the refusals. Those are what these
tests pin.

`_should_use_live_mcp` decides the branch by sniffing `sys.modules` for pytest
and then keying on EMP-509. That is a test-environment check living in
production code, which is not a design I would choose - but it is load-bearing
for the existing suite, so these tests work with it rather than around it:
EMP-509 exercises the live path, any other id exercises the mock.
"""

from __future__ import annotations

import datetime
import sys

import pytest

from src.guardrails.operation_guardrails import (
    GuardrailValidationResult,
    OperationGuardrailEngine,
)
from src.integrations.workweek.client import WorkWeekClient
from src.integrations.workweek.models import (
    ContactUpdateResponse,
    EmployeeProfile,
    LeaveBalances,
    LeaveSubmissionResponse,
)

LIVE = "EMP-509"
MOCK = "EMP-1001"

TODAY = datetime.date(2026, 8, 27)
SOON = datetime.date(2026, 9, 1)
SOON_END = datetime.date(2026, 9, 3)


class FakeMCP:
    """Records calls and replays programmed answers, raising if told to."""

    def __init__(self, **answers):
        self.answers = answers
        self.calls: list[tuple[str, dict]] = []

    def _answer(self, name: str, **kwargs):
        self.calls.append((name, kwargs))
        value = self.answers.get(name, {})
        if isinstance(value, Exception):
            raise value
        return value

    def get_employee_profile(self, employee_id):
        return self._answer("get_employee_profile", employee_id=employee_id)

    def get_personal_info(self, employee_id):
        return self._answer("get_personal_info", employee_id=employee_id)

    def get_employee_balances(self, employee_id):
        return self._answer("get_employee_balances", employee_id=employee_id)

    def update_personal_info(self, **kwargs):
        return self._answer("update_personal_info", **kwargs)

    def request_time_off(self, **kwargs):
        return self._answer("request_time_off", **kwargs)

    def get_leave_requests(self, employee_id):
        return self._answer("get_leave_requests", employee_id=employee_id)

    def cancel_leave_request(self, employee_id, request_id):
        return self._answer(
            "cancel_leave_request", employee_id=employee_id, request_id=request_id
        )

    def named(self, name: str) -> list[dict]:
        return [kwargs for called, kwargs in self.calls if called == name]


class FakeService:
    """The mock-service half of the split."""

    def __init__(self, **answers):
        self.answers = answers
        self.calls: list[tuple[str, dict]] = []

    def get_profile(self, employee_id):
        self.calls.append(("get_profile", {"employee_id": employee_id}))
        return self.answers.get("get_profile")

    def get_balances(self, employee_id):
        self.calls.append(("get_balances", {"employee_id": employee_id}))
        return self.answers.get("get_balances")

    def update_contact(self, **kwargs):
        self.calls.append(("update_contact", kwargs))
        return self.answers.get(
            "update_contact",
            ContactUpdateResponse(
                success=True, employee_id=kwargs["employee_id"], message="ok", updated_fields={}
            ),
        )

    def submit_leave(self, **kwargs):
        self.calls.append(("submit_leave", kwargs))
        return self.answers.get(
            "submit_leave",
            LeaveSubmissionResponse(success=True, request_id="WW-LV-MOCK", message="ok"),
        )

    def cancel_leave(self, request_id):
        self.calls.append(("cancel_leave", {"request_id": request_id}))
        return self.answers.get("cancel_leave", True)


class SpyLogger:
    def __init__(self):
        self.events: list[dict] = []

    def log_event(self, **kwargs):
        self.events.append(kwargs)

    def statuses(self, action_type: str) -> list[str]:
        return [e["status"] for e in self.events if e["action_type"] == action_type]


def _balances(vacation: float = 14.0, sick: float = 10.0) -> LeaveBalances:
    return LeaveBalances(
        employee_id=MOCK,
        vacation_accrued=18.0,
        vacation_used=18.0 - vacation,
        vacation_remaining=vacation,
        sick_accrued=10.0,
        sick_used=10.0 - sick,
        sick_remaining=sick,
    )


def _profile(employee_id: str = MOCK, **overrides) -> EmployeeProfile:
    fields = {
        "employee_id": employee_id,
        "full_name": "Jane Doe",
        "email": "jane@corp",
        "phone_number": "+1-512-555-0199",
        "home_address": "123 Tech Park Way",
        "work_location_status": "REMOTE_FULL_TIME",
        "current_office": "Austin",
        "country": "USA",
        "job_title": "Engineer",
        "manager_id": "MGR-1",
    }
    fields.update(overrides)
    return EmployeeProfile(**fields)


def make_client(mcp=None, service=None, guardrails=None, spy=None) -> WorkWeekClient:
    return WorkWeekClient(
        service=service or FakeService(),
        mcp_client=mcp or FakeMCP(),
        guardrails=guardrails or OperationGuardrailEngine(),
        logger=spy or SpyLogger(),
    )


# --- FR-1.5 caller isolation -------------------------------------------------


def test_reading_another_employees_profile_is_refused_and_audited():
    spy = SpyLogger()
    client = make_client(spy=spy)

    with pytest.raises(PermissionError, match="cannot access profile"):
        client.get_employee_profile("EMP-1001", "EMP-1002")

    assert spy.statuses("WORKWEEK_GET_PROFILE") == ["REFUSED"]
    assert "FR-1.5" in spy.events[0]["details"]["reason"]


def test_reading_another_employees_balances_is_refused_and_audited():
    spy = SpyLogger()
    client = make_client(spy=spy)

    with pytest.raises(PermissionError, match="cannot access balances"):
        client.get_leave_balances("EMP-1001", "EMP-1002")

    assert spy.statuses("WORKWEEK_GET_BALANCES") == ["REFUSED"]


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("update_contact_info", {"home_address": "somewhere"}),
        ("get_leave_requests", {}),
    ],
)
def test_cross_employee_writes_and_reads_are_prohibited(method, args):
    client = make_client()

    with pytest.raises(PermissionError):
        getattr(client, method)("EMP-1001", "EMP-1002", **args)


def test_submitting_leave_for_someone_else_is_prohibited():
    client = make_client()

    with pytest.raises(PermissionError, match="on behalf of another employee"):
        client.submit_leave_request("EMP-1001", "EMP-1002", "Vacation", SOON, SOON_END, 3.0)


# --- the live / mock branch --------------------------------------------------


def test_the_mock_service_answers_for_a_non_live_employee():
    service = FakeService(get_profile=_profile())
    mcp = FakeMCP()
    client = make_client(mcp=mcp, service=service)

    assert client.get_employee_profile(MOCK, MOCK).full_name == "Jane Doe"
    assert mcp.calls == []


def test_live_mcp_is_bypassed_entirely_when_disabled():
    """`USE_LIVE_MCP=false` must reach the mock even for EMP-509."""
    service = FakeService(get_profile=_profile(LIVE))
    mcp = FakeMCP()
    client = make_client(mcp=mcp, service=service)
    client._use_live_mcp = False

    assert client.get_employee_profile(LIVE, LIVE).employee_id == LIVE
    assert mcp.calls == []


def test_outside_a_test_run_every_employee_goes_live(monkeypatch):
    """The branch the server and the CLI actually take.

    `_should_use_live_mcp` looks for pytest in `sys.modules` and, finding it,
    reserves the live path for EMP-509 so the fixture-backed tests keep their
    mock data. Removing the marker is the only way to reach the production
    behaviour, and it is what pins the two halves of that decision together.
    """
    monkeypatch.delitem(sys.modules, "pytest")

    assert make_client()._should_use_live_mcp(MOCK) is True


def test_a_client_with_no_mcp_client_falls_back_to_the_service():
    service = FakeService(get_profile=_profile(LIVE))
    client = WorkWeekClient(service=service, mcp_client=None, logger=SpyLogger())
    client._mcp_client = None

    assert client.get_employee_profile(LIVE, LIVE) is not None


# --- profile mapping over the live path --------------------------------------


def test_a_live_profile_is_mapped_field_by_field():
    mcp = FakeMCP(
        get_employee_profile={
            "first_name": "Aish",
            "last_name": "Prabhat",
            "email": "aish@altostrat.com",
            "home_address": "1 Marina Bay",
            "phone_number": "+65 6555 0100",
            "role": "HYBRID",
            "department": "Singapore HQ",
            "country": "SG",
            "job_title": "Staff Engineer",
            "manager_id": "MGR-9",
        }
    )

    profile = make_client(mcp=mcp).get_employee_profile(LIVE, LIVE)

    assert profile.full_name == "Aish Prabhat"
    assert profile.email == "aish@altostrat.com"
    assert profile.job_title == "Staff Engineer"
    assert profile.current_office == "Singapore HQ"


def test_missing_live_profile_fields_become_n_a_rather_than_empty():
    """An empty string renders as a blank in the answer; "N/A" reads as unknown."""
    mcp = FakeMCP(get_employee_profile={"job_title": "Engineer"})

    profile = make_client(mcp=mcp).get_employee_profile(LIVE, LIVE)

    assert profile.home_address == "N/A"
    assert profile.manager_id == "N/A"
    assert profile.full_name == f"Employee {LIVE}"
    assert profile.email == f"{LIVE.lower()}@google.com"


def test_a_profile_with_neither_name_nor_title_falls_back_to_personal_info():
    """The resource is absent on some tenants; the contact tool always answers."""
    mcp = FakeMCP(
        get_employee_profile={"unrelated": "payload"},
        get_personal_info={"address": "1 Marina Bay", "phone": "+65 6555 0100"},
    )

    profile = make_client(mcp=mcp).get_employee_profile(LIVE, LIVE)

    assert profile.home_address == "1 Marina Bay"
    assert profile.phone_number == "+65 6555 0100"
    assert profile.job_title == "N/A"


def test_an_empty_live_profile_still_falls_back():
    mcp = FakeMCP(get_employee_profile={}, get_personal_info={})

    profile = make_client(mcp=mcp).get_employee_profile(LIVE, LIVE)

    assert profile.home_address == "N/A"


def test_a_live_profile_failure_is_reported_not_silently_mocked():
    """Answering from mock data after a live failure would state fiction as fact."""
    mcp = FakeMCP(get_employee_profile=ConnectionError("tenant down"))

    with pytest.raises(RuntimeError, match="FastMCP communication error"):
        make_client(mcp=mcp).get_employee_profile(LIVE, LIVE)


def test_a_successful_profile_read_is_audited():
    spy = SpyLogger()
    make_client(service=FakeService(get_profile=_profile()), spy=spy).get_employee_profile(
        MOCK, MOCK
    )

    assert spy.statuses("WORKWEEK_GET_PROFILE") == ["SUCCESS"]


def test_an_absent_profile_is_audited_as_not_found():
    spy = SpyLogger()
    client = make_client(service=FakeService(get_profile=None), spy=spy)

    assert client.get_employee_profile(MOCK, MOCK) is None
    assert spy.statuses("WORKWEEK_GET_PROFILE") == ["NOT_FOUND"]


# --- balances ----------------------------------------------------------------


def test_live_balances_are_reconstructed_from_the_remaining_days():
    """The tool reports remaining only, so used is derived from the accrual."""
    mcp = FakeMCP(
        get_employee_balances={"vacation_days_remaining": 12.0, "sick_days_remaining": 7.0}
    )

    balances = make_client(mcp=mcp).get_leave_balances(LIVE, LIVE)

    assert balances.vacation_remaining == 12.0
    assert balances.vacation_used == 8.0
    assert balances.sick_remaining == 7.0
    assert balances.sick_used == 3.0


def test_absent_live_balances_use_the_documented_defaults():
    balances = make_client(mcp=FakeMCP(get_employee_balances={})).get_leave_balances(LIVE, LIVE)

    assert balances.vacation_remaining == 15.0
    assert balances.sick_remaining == 10.0


def test_a_live_balance_failure_is_reported():
    mcp = FakeMCP(get_employee_balances=TimeoutError("no answer"))

    with pytest.raises(RuntimeError, match="FastMCP communication error"):
        make_client(mcp=mcp).get_leave_balances(LIVE, LIVE)


def test_an_absent_balance_record_is_audited_as_not_found():
    spy = SpyLogger()
    client = make_client(service=FakeService(get_balances=None), spy=spy)

    assert client.get_leave_balances(MOCK, MOCK) is None
    assert spy.statuses("WORKWEEK_GET_BALANCES") == ["NOT_FOUND"]


# --- contact updates ---------------------------------------------------------


def test_an_update_with_no_fields_is_rejected_before_anything_is_called():
    mcp, service = FakeMCP(), FakeService()

    res = make_client(mcp=mcp, service=service).update_contact_info(LIVE, LIVE)

    assert not res.success
    assert "No contact or office update parameters" in res.message
    assert mcp.calls == [] and service.calls == []


def test_a_guardrail_rejection_stops_the_write_and_is_audited():
    class Rejecting:
        def validate_contact_update(self, phone, address):
            return GuardrailValidationResult(
                is_valid=False, error_message="Phone number is malformed.", rule_name="PHONE_FORMAT"
            )

    spy, mcp = SpyLogger(), FakeMCP()
    client = make_client(mcp=mcp, guardrails=Rejecting(), spy=spy)

    res = client.update_contact_info(LIVE, LIVE, phone_number="nonsense")

    assert not res.success
    assert res.message == "Phone number is malformed."
    assert mcp.named("update_personal_info") == []
    assert spy.statuses("WORKWEEK_UPDATE_CONTACT") == ["FAILED"]
    assert spy.events[0]["details"]["rule"] == "PHONE_FORMAT"


def test_a_guardrail_rejection_with_no_message_still_reads_as_a_failure():
    class Terse:
        def validate_contact_update(self, phone, address):
            return GuardrailValidationResult(is_valid=False, rule_name="UNKNOWN")

    res = make_client(guardrails=Terse()).update_contact_info(LIVE, LIVE, phone_number="x")

    assert not res.success
    assert res.message == "Validation failed"


def test_a_partial_update_reads_the_current_profile_before_writing():
    """WorkWeek's update tool replaces both fields, so a one-field update
    submitted alone would blank the other."""
    mcp = FakeMCP(
        get_employee_profile={"first_name": "A", "home_address": "1 Marina Bay",
                              "phone_number": "+65 6555 0100"},
        update_personal_info={"content": [{"text": "Updated"}]},
    )

    res = make_client(mcp=mcp).update_contact_info(LIVE, LIVE, phone_number="+65 6555 0999")

    assert res.success
    (sent,) = mcp.named("update_personal_info")
    assert sent["phone"] == "+65 6555 0999"
    assert sent["address"] == "1 Marina Bay"


def test_a_full_update_skips_the_read():
    mcp = FakeMCP(update_personal_info={"content": [{"text": "Updated"}]})

    make_client(mcp=mcp).update_contact_info(
        LIVE, LIVE, home_address="2 Raffles", phone_number="+65 1"
    )

    assert mcp.named("get_employee_profile") == []


def test_an_unreadable_current_profile_does_not_block_the_update():
    """Degrades to the placeholder rather than refusing to write at all."""
    mcp = FakeMCP(
        get_employee_profile=ConnectionError("down"),
        update_personal_info={"content": [{"text": "Updated"}]},
    )

    res = make_client(mcp=mcp).update_contact_info(LIVE, LIVE, phone_number="+65 6555 0999")

    assert res.success
    (sent,) = mcp.named("update_personal_info")
    assert sent["address"] == "Corporate Office"


def test_a_missing_profile_leaves_the_placeholders_in_place():
    mcp = FakeMCP(
        get_employee_profile={},
        get_personal_info={},
        update_personal_info={"content": [{"text": "Updated"}]},
    )

    make_client(mcp=mcp).update_contact_info(LIVE, LIVE, phone_number="+65 6555 0999")

    (sent,) = mcp.named("update_personal_info")
    assert sent["address"] == "N/A"


def test_an_address_only_update_keeps_the_phone_number_on_file():
    """The mirror of the partial update above: the field held back is the phone."""
    mcp = FakeMCP(
        get_employee_profile={"first_name": "A", "home_address": "1 Marina Bay",
                              "phone_number": "+65 6555 0100"},
        update_personal_info={"content": [{"text": "Updated"}]},
    )

    res = make_client(mcp=mcp).update_contact_info(
        LIVE, LIVE, home_address="2 Raffles Place, Singapore"
    )

    assert res.success
    (sent,) = mcp.named("update_personal_info")
    assert sent["address"] == "2 Raffles Place, Singapore"
    assert sent["phone"] == "+65 6555 0100"


def test_a_profile_read_returning_nothing_leaves_the_placeholder(monkeypatch):
    """Defensive: on the live path the read always yields a profile, so the
    `if cur_prof` guard is unreachable from outside. It still has to hold, since
    dereferencing None here would abort a write the guardrails already cleared."""
    mcp = FakeMCP(update_personal_info={"content": [{"text": "Updated"}]})
    client = make_client(mcp=mcp)
    monkeypatch.setattr(client, "get_employee_profile", lambda caller, target: None)

    assert client.update_contact_info(LIVE, LIVE, phone_number="+65 6555 0999").success
    (sent,) = mcp.named("update_personal_info")
    assert sent["address"] == "Corporate Office"


def test_an_error_in_the_tool_response_text_is_surfaced_as_a_failure():
    """The transport succeeded; the operation did not. A 200 is not a success."""
    mcp = FakeMCP(update_personal_info={"content": [{"text": "Error: invalid phone format"}]})
    spy = SpyLogger()

    res = make_client(mcp=mcp, spy=spy).update_contact_info(
        LIVE, LIVE, home_address="1 Marina Bay, Singapore", phone_number="+65 6555 0100"
    )

    assert not res.success
    assert "Error: invalid phone format" in res.message
    assert spy.statuses("WORKWEEK_UPDATE_CONTACT") == ["FAILED"]


def test_a_response_with_no_content_block_is_treated_as_success():
    mcp = FakeMCP(update_personal_info={"structuredContent": {"ok": True}})

    res = make_client(mcp=mcp).update_contact_info(LIVE, LIVE, home_address="1 Marina Bay, Singapore", phone_number="+65 6555 0100")

    assert res.success


def test_a_live_update_failure_is_reported():
    mcp = FakeMCP(update_personal_info=ConnectionError("down"))

    with pytest.raises(RuntimeError, match="FastMCP communication error"):
        make_client(mcp=mcp).update_contact_info(LIVE, LIVE, home_address="1 Marina Bay, Singapore", phone_number="+65 6555 0100")


def test_an_office_only_update_goes_to_the_mock_service():
    """FastMCP exposes no office field, so office moves are service-side."""
    service, mcp = FakeService(), FakeMCP()

    make_client(mcp=mcp, service=service).update_contact_info(
        LIVE, LIVE, current_office="Singapore HQ", country="SG"
    )

    assert mcp.named("update_personal_info") == []
    assert service.calls[0][1]["current_office"] == "Singapore HQ"


# --- leave submission --------------------------------------------------------


def test_leave_cannot_be_submitted_without_a_balance_record():
    client = make_client(service=FakeService(get_balances=None))

    res = client.submit_leave_request(MOCK, MOCK, "Vacation", SOON, SOON_END, 3.0)

    assert not res.success
    assert "balance record not found" in res.message


def test_a_guardrail_rejection_blocks_submission_and_is_audited():
    spy = SpyLogger()
    client = make_client(service=FakeService(get_balances=_balances(vacation=1.0)), spy=spy)

    res = client.submit_leave_request(MOCK, MOCK, "Vacation", SOON, SOON_END, 5.0, TODAY)

    assert not res.success
    assert spy.statuses("WORKWEEK_SUBMIT_LEAVE") == ["FAILED"]


def test_the_balance_checked_is_the_one_matching_the_leave_type():
    """Sick leave must not be validated against the vacation balance."""
    service = FakeService(get_balances=_balances(vacation=20.0, sick=1.0))
    client = make_client(service=service)

    res = client.submit_leave_request(MOCK, MOCK, "Sick", SOON, SOON_END, 5.0, TODAY)

    assert not res.success


def test_a_valid_request_reaches_the_mock_service():
    service = FakeService(get_balances=_balances())
    spy = SpyLogger()

    res = make_client(service=service, spy=spy).submit_leave_request(
        MOCK, MOCK, "Vacation", SOON, SOON_END, 3.0, TODAY
    )

    assert res.success
    assert spy.statuses("WORKWEEK_SUBMIT_LEAVE") == ["SUCCESS"]
    assert service.calls[-1][1]["start_date"] == "2026-09-01"


def test_a_live_submission_normalises_the_leave_type_and_dates():
    """FastMCP only accepts the two canonical types."""
    mcp = FakeMCP(
        get_employee_balances={"vacation_days_remaining": 20.0, "sick_days_remaining": 10.0},
        request_time_off={"content": [{"text": "Leave submitted"}]},
    )

    make_client(mcp=mcp).submit_leave_request(
        LIVE, LIVE, "Annual Vacation Leave", SOON, SOON_END, 3.0, TODAY
    )

    (sent,) = mcp.named("request_time_off")
    assert sent["leave_type"] == "Vacation"
    assert (sent["start_date"], sent["end_date"]) == ("2026-09-01", "2026-09-03")


def test_a_non_vacation_type_is_submitted_as_sick():
    mcp = FakeMCP(
        get_employee_balances={"sick_days_remaining": 10.0},
        request_time_off={"content": [{"text": "ok"}]},
    )

    make_client(mcp=mcp).submit_leave_request(
        LIVE, LIVE, "Medical Leave", SOON, SOON_END, 2.0, TODAY
    )

    assert mcp.named("request_time_off")[0]["leave_type"] == "Sick"


def test_the_request_id_is_lifted_out_of_the_response_prose():
    mcp = FakeMCP(
        get_employee_balances={"vacation_days_remaining": 20.0},
        request_time_off={"content": [{"text": "Created with ID: 4012 for EMP-509"}]},
    )

    res = make_client(mcp=mcp).submit_leave_request(
        LIVE, LIVE, "Vacation", SOON, SOON_END, 3.0, TODAY
    )

    assert res.request_id == "WW-LV-4012"
    assert res.remaining_balance == 17.0


def test_a_response_with_no_id_still_yields_a_usable_reference():
    mcp = FakeMCP(
        get_employee_balances={"vacation_days_remaining": 20.0},
        request_time_off={"content": [{"text": "Submitted"}]},
    )

    res = make_client(mcp=mcp).submit_leave_request(
        LIVE, LIVE, "Vacation", SOON, SOON_END, 1.0, TODAY
    )

    assert res.request_id == "WW-LV-MCP"


def test_an_empty_submission_response_gets_a_default_message():
    mcp = FakeMCP(
        get_employee_balances={"vacation_days_remaining": 20.0},
        request_time_off={},
    )

    res = make_client(mcp=mcp).submit_leave_request(
        LIVE, LIVE, "Vacation", SOON, SOON_END, 1.0, TODAY
    )

    assert res.message == "Submitted to WorkWeek FastMCP"


def test_a_live_submission_failure_is_reported():
    mcp = FakeMCP(
        get_employee_balances={"vacation_days_remaining": 20.0},
        request_time_off=ConnectionError("down"),
    )

    with pytest.raises(RuntimeError, match="FastMCP communication error"):
        make_client(mcp=mcp).submit_leave_request(
            LIVE, LIVE, "Vacation", SOON, SOON_END, 1.0, TODAY
        )


# --- leave history -----------------------------------------------------------


def test_leave_history_comes_from_the_live_tool():
    mcp = FakeMCP(get_leave_requests=[{"request_id": 1}, {"request_id": 2}])
    spy = SpyLogger()

    assert len(make_client(mcp=mcp, spy=spy).get_leave_requests(LIVE, LIVE)) == 2
    assert spy.events[0]["details"]["count"] == 2


def test_a_history_lookup_failure_degrades_to_empty_rather_than_raising():
    """Unlike a balance read, an empty history is a truthful answer."""
    mcp = FakeMCP(get_leave_requests=ConnectionError("down"))
    spy = SpyLogger()

    assert make_client(mcp=mcp, spy=spy).get_leave_requests(LIVE, LIVE) == []
    assert spy.statuses("WORKWEEK_GET_LEAVE_REQUESTS") == ["SUCCESS"]


def test_history_for_a_mock_employee_is_empty_without_calling_anything():
    mcp = FakeMCP()

    assert make_client(mcp=mcp).get_leave_requests(MOCK, MOCK) == []
    assert mcp.calls == []


# --- cancellation, the compensating action -----------------------------------


def test_a_numeric_request_id_is_cancelled_over_the_live_tool():
    mcp = FakeMCP(cancel_leave_request={"ok": True})
    spy = SpyLogger()

    assert make_client(mcp=mcp, spy=spy).cancel_leave_request(LIVE, "4012")
    assert mcp.named("cancel_leave_request")[0]["request_id"] == 4012
    assert spy.statuses("WORKWEEK_CANCEL_LEAVE") == ["COMPENSATED"]


def test_a_non_numeric_request_id_is_cancelled_against_the_mock_service():
    """Mock ids look like WW-LV-1; the live tool only accepts integers."""
    mcp, service = FakeMCP(), FakeService()

    assert make_client(mcp=mcp, service=service).cancel_leave_request(MOCK, "WW-LV-9001")
    assert mcp.calls == []
    assert service.calls == [("cancel_leave", {"request_id": "WW-LV-9001"})]


def test_a_failed_live_cancellation_falls_back_to_the_service():
    """Compensation must not be abandoned because one backend is unreachable."""
    mcp = FakeMCP(cancel_leave_request=ConnectionError("down"))
    service = FakeService(cancel_leave=True)

    assert make_client(mcp=mcp, service=service).cancel_leave_request(LIVE, "4012")
    assert service.calls == [("cancel_leave", {"request_id": "4012"})]


def test_a_cancellation_nothing_can_satisfy_is_audited_as_failed():
    mcp = FakeMCP(cancel_leave_request=ConnectionError("down"))
    service = FakeService(cancel_leave=False)
    spy = SpyLogger()

    assert not make_client(mcp=mcp, service=service, spy=spy).cancel_leave_request(LIVE, "4012")
    assert spy.statuses("WORKWEEK_CANCEL_LEAVE") == ["FAILED"]


def test_cancellation_skips_the_live_tool_when_it_is_disabled():
    mcp, service = FakeMCP(), FakeService()
    client = make_client(mcp=mcp, service=service)
    client._use_live_mcp = False

    assert client.cancel_leave_request(LIVE, "4012")
    assert mcp.calls == []
