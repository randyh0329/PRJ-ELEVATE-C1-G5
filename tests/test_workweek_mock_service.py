"""The in-memory WorkWeek backend that stands in for the HCM tenant.

`WorkWeekClient` is what the agent talks to; this is what the client talks to
when the live FastMCP session is not in play, which is every test run and every
demo. It is a mock, but it is the *system of record* for those runs, so the
behaviours the saga layer depends on have to hold here or a rollback silently
does nothing.

Two of those matter more than the rest:

* A submission deducts from the balance, and a cancellation puts it back
  exactly. Compensation is only meaningful if the second undoes the first.
* Cancelling twice is refused. Otherwise a retried compensation would credit
  the balance again and hand the employee days they never had.
"""

from __future__ import annotations

import pytest

from src.integrations.workweek.mock_service import WorkWeekMockService


@pytest.fixture
def service() -> WorkWeekMockService:
    return WorkWeekMockService()


# --- reads --------------------------------------------------------------------


def test_a_seeded_profile_reads_back(service):
    profile = service.get_profile("EMP-1001")

    assert profile.full_name == "Jane Doe"
    assert profile.work_location_status == "REMOTE_FULL_TIME"


def test_an_unknown_profile_is_absent_rather_than_a_blank_record(service):
    """A placeholder profile would let a caller act on invented attributes -
    UC-2.1 gates a hardware entitlement on `work_location_status` alone."""
    assert service.get_profile("EMP-9999") is None


def test_seeded_balances_read_back(service):
    balances = service.get_balances("EMP-1001")

    assert balances.vacation_remaining == 14.0
    assert balances.sick_remaining == 12.0


def test_balances_for_an_unknown_employee_are_absent(service):
    assert service.get_balances("EMP-9999") is None


# --- contact updates ----------------------------------------------------------


def test_updating_an_unknown_employee_fails_without_creating_one(service):
    result = service.update_contact("EMP-9999", home_address="1 Somewhere Street")

    assert result.success is False
    assert "EMP-9999 not found" in result.message
    assert result.updated_fields == {}
    assert service.get_profile("EMP-9999") is None


def test_each_supplied_field_is_written_and_reported(service):
    result = service.update_contact(
        "EMP-1001",
        home_address="100 Bishopsgate, London EC2N 4AG",
        phone_number="+44 20 7946 0000",
        current_office="London EC2",
        country="UK",
    )

    assert result.success is True
    assert result.updated_fields == {
        "home_address": "100 Bishopsgate, London EC2N 4AG",
        "phone_number": "+44 20 7946 0000",
        "current_office": "London EC2",
        "country": "UK",
    }
    profile = service.get_profile("EMP-1001")
    assert profile.home_address == "100 Bishopsgate, London EC2N 4AG"
    assert profile.country == "UK"


def test_an_omitted_field_is_left_alone(service):
    """A partial update must not blank the fields it did not mention - the saga
    rollback passes only the values it captured."""
    before = service.get_profile("EMP-1001").phone_number

    result = service.update_contact("EMP-1001", home_address="9 Old Road, Austin, TX")

    assert result.updated_fields == {"home_address": "9 Old Road, Austin, TX"}
    assert service.get_profile("EMP-1001").phone_number == before


def test_an_update_that_names_nothing_succeeds_and_changes_nothing(service):
    result = service.update_contact("EMP-1001")

    assert result.success is True
    assert result.updated_fields == {}


# --- leave submission ---------------------------------------------------------


def test_a_vacation_submission_deducts_from_the_vacation_balance(service):
    result = service.submit_leave("EMP-1001", "Vacation", "2026-09-01", "2026-09-03", 3.0)

    assert result.success is True
    assert result.remaining_balance == 11.0
    balances = service.get_balances("EMP-1001")
    assert balances.vacation_used == 7.0
    assert balances.sick_remaining == 12.0


def test_any_other_leave_type_is_drawn_from_the_sick_balance(service):
    result = service.submit_leave("EMP-1001", "Sick_LOA", "2026-09-01", "2026-09-02", 2.0)

    assert result.remaining_balance == 10.0
    assert service.get_balances("EMP-1001").vacation_remaining == 14.0


def test_a_submission_for_an_employee_with_no_leave_record_is_refused(service):
    result = service.submit_leave("EMP-9999", "Vacation", "2026-09-01", "2026-09-02", 1.0)

    assert result.success is False
    assert "No leave record found" in result.message
    assert result.request_id is None


def test_a_vacation_request_beyond_the_balance_is_refused_and_deducts_nothing(service):
    result = service.submit_leave("EMP-1001", "Vacation", "2026-09-01", "2026-10-01", 20.0)

    assert result.success is False
    assert "Insufficient vacation balance" in result.message
    assert service.get_balances("EMP-1001").vacation_remaining == 14.0


def test_a_sick_request_beyond_the_balance_is_refused_and_deducts_nothing(service):
    result = service.submit_leave("EMP-1001", "Sick_LOA", "2026-09-01", "2026-10-01", 20.0)

    assert result.success is False
    assert "Insufficient sick leave balance" in result.message
    assert service.get_balances("EMP-1001").sick_remaining == 12.0


def test_a_submission_records_who_filed_it(service):
    """§7.1 attribution: an agent-filed request must be distinguishable from one
    an employee typed into WorkWeek themselves."""
    request_id = service.submit_leave(
        "EMP-1001", "Vacation", "2026-09-01", "2026-09-02", 2.0
    ).request_id

    record = service.get_leave_request(request_id)
    assert record.origin == "HR_AGENT_ORCHESTRATOR_V1"
    assert record.status == "SUBMITTED"
    assert record.submitted_at.startswith("20")


def test_a_caller_supplied_origin_is_preserved(service):
    request_id = service.submit_leave(
        "EMP-1001", "Vacation", "2026-09-01", "2026-09-02", 2.0, origin="EMPLOYEE_SELF_SERVICE"
    ).request_id

    assert service.get_leave_request(request_id).origin == "EMPLOYEE_SELF_SERVICE"


def test_an_unknown_request_id_reads_back_as_absent(service):
    assert service.get_leave_request("WW-LV-NOPE") is None


# --- cancellation, the compensation primitive ---------------------------------


def test_cancelling_restores_the_vacation_balance_exactly(service):
    request_id = service.submit_leave(
        "EMP-1001", "Vacation", "2026-09-01", "2026-09-03", 3.0
    ).request_id

    assert service.cancel_leave(request_id) is True

    balances = service.get_balances("EMP-1001")
    assert balances.vacation_remaining == 14.0
    assert balances.vacation_used == 4.0
    assert service.get_leave_request(request_id).status == "CANCELLED"


def test_cancelling_restores_the_sick_balance_exactly(service):
    request_id = service.submit_leave(
        "EMP-1001", "Sick_LOA", "2026-09-01", "2026-09-02", 2.0
    ).request_id

    service.cancel_leave(request_id)

    balances = service.get_balances("EMP-1001")
    assert balances.sick_remaining == 12.0
    assert balances.sick_used == 2.0


def test_cancelling_twice_is_refused_so_the_balance_is_not_credited_again(service):
    """A retried saga compensation must be idempotent, or the employee is handed
    days they never accrued."""
    request_id = service.submit_leave(
        "EMP-1001", "Vacation", "2026-09-01", "2026-09-03", 3.0
    ).request_id
    service.cancel_leave(request_id)

    assert service.cancel_leave(request_id) is False
    assert service.get_balances("EMP-1001").vacation_remaining == 14.0


def test_cancelling_an_unknown_request_is_refused(service):
    assert service.cancel_leave("WW-LV-NOPE") is False


def test_cancelling_survives_a_missing_balance_record(service):
    """Defensive: the request is still marked cancelled even when there is no
    balance to credit, so the ledger and the backend do not disagree."""
    request_id = service.submit_leave(
        "EMP-1001", "Vacation", "2026-09-01", "2026-09-02", 2.0
    ).request_id
    del service._balances["EMP-1001"]

    assert service.cancel_leave(request_id) is True
    assert service.get_leave_request(request_id).status == "CANCELLED"


# --- reset --------------------------------------------------------------------


def test_reinitialising_discards_submissions_and_restores_the_baseline(service):
    request_id = service.submit_leave(
        "EMP-1001", "Vacation", "2026-09-01", "2026-09-03", 3.0
    ).request_id
    service.update_contact("EMP-1001", home_address="100 Bishopsgate, London EC2N 4AG")

    service.init_mock_data()

    assert service.get_leave_request(request_id) is None
    assert service.get_balances("EMP-1001").vacation_remaining == 14.0
    assert service.get_profile("EMP-1001").home_address == "123 Tech Park Way, Austin, TX"
