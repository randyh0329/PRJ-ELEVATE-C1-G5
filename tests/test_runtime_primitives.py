"""The small runtime pieces every path leans on: session, audit, surrogates.

None of these are interesting on their own, which is exactly why they are worth
pinning: a policy answer, a leave submission and a saga rollback all pass
through them, so a defect here is a defect everywhere at once and shows up as a
symptom somewhere far away.

The three properties under test:

* `SessionMemory` never invents a session. Writing to an unknown id is a no-op
  rather than an implicit create, so a turn cannot graft itself onto a
  conversation that was never opened.
* `AuditLogger` keeps every record it is handed and filters on read. Under
  §7.1 the archive is the evidence that an automated write happened.
* `CloudDLPInterceptor._mint` hands out a distinct surrogate per entity, so two people
  in one sentence do not collapse into one token.
"""

from __future__ import annotations

import datetime
import logging
from types import SimpleNamespace

import pytest

from src.core.saga import SagaCoordinator
from src.core.session import SessionMemory
from src.grounding.okf_store import OKFPolicyStore, PolicyDocument
from src.security.dlp import CloudDLPInterceptor
from src.telemetry.audit_logger import AuditLogger

# --- session memory -----------------------------------------------------------


def test_a_session_is_created_once_and_returned_thereafter():
    memory = SessionMemory()

    first = memory.get_or_create_session("sess-1", "EMP-1001")
    second = memory.get_or_create_session("sess-1", "EMP-1001")

    assert first is second
    assert first.employee_id == "EMP-1001"


def test_reopening_a_session_refreshes_its_last_active_stamp():
    memory = SessionMemory()
    session = memory.get_or_create_session("sess-1", "EMP-1001")
    session.last_active_at = "2020-01-01T00:00:00+00:00"

    memory.get_or_create_session("sess-1", "EMP-1001")

    assert session.last_active_at > "2020-01-01T00:00:00+00:00"


def test_messages_accumulate_in_the_order_they_were_added():
    memory = SessionMemory()
    memory.get_or_create_session("sess-1", "EMP-1001")

    memory.add_message("sess-1", "user", "What is the leave policy?")
    memory.add_message("sess-1", "assistant", "14 days.", citations=["handbook.md#leave"])

    history = memory.get_history("sess-1")
    assert [m.role for m in history] == ["user", "assistant"]
    assert history[1].citations == ["handbook.md#leave"]


def test_writing_to_an_unopened_session_is_dropped_rather_than_creating_one():
    """An implicit create would let a turn attach itself to a conversation that
    was never opened, and the employee binding would come from nowhere."""
    memory = SessionMemory()

    memory.add_message("sess-unknown", "user", "hello")

    assert memory.get_history("sess-unknown") == []


def test_the_history_of_an_unknown_session_is_empty_not_an_error():
    assert SessionMemory().get_history("sess-nope") == []


def test_clearing_drops_every_session():
    memory = SessionMemory()
    memory.get_or_create_session("sess-1", "EMP-1001")
    memory.get_or_create_session("sess-2", "EMP-1002")

    memory.clear()

    assert memory.get_history("sess-1") == []
    assert memory.get_or_create_session("sess-1", "EMP-1001").messages == []


def test_a_message_stamps_the_session_as_active():
    memory = SessionMemory()
    session = memory.get_or_create_session("sess-1", "EMP-1001")
    session.last_active_at = "2020-01-01T00:00:00+00:00"

    memory.add_message("sess-1", "user", "still here")

    assert session.last_active_at > "2020-01-01T00:00:00+00:00"


# --- the audit archive --------------------------------------------------------


@pytest.fixture
def audit() -> AuditLogger:
    return AuditLogger()


def test_an_event_is_kept_and_returned_as_it_was_recorded(audit):
    record = audit.log_event(
        caller_employee_id="EMP-1001",
        action_type="SUBMIT_LEAVE",
        status="SUCCESS",
        details={"days": 3},
    )

    assert record.origin == "HR_AGENT_ORCHESTRATOR_V1"
    assert audit.get_records() == [record]


def test_an_event_carries_the_origin_and_metadata_it_was_given(audit):
    record = audit.log_event(
        caller_employee_id="EMP-1001",
        action_type="SUBMIT_LEAVE",
        status="SUCCESS",
        origin="SAGA_COORDINATOR",
        metadata={"sagaId": "SAGA-1"},
    )

    assert record.origin == "SAGA_COORDINATOR"
    assert record.metadata == {"sagaId": "SAGA-1"}
    assert record.details == {}


def test_records_can_be_narrowed_to_one_caller(audit):
    audit.log_event(caller_employee_id="EMP-1001", action_type="GET_BALANCES", status="SUCCESS")
    audit.log_event(caller_employee_id="EMP-1002", action_type="GET_BALANCES", status="SUCCESS")

    assert [r.caller_employee_id for r in audit.get_records(caller_employee_id="EMP-1001")] == [
        "EMP-1001"
    ]


def test_records_can_be_narrowed_to_one_action(audit):
    audit.log_event(caller_employee_id="EMP-1001", action_type="GET_BALANCES", status="SUCCESS")
    audit.log_event(caller_employee_id="EMP-1001", action_type="SUBMIT_LEAVE", status="SUCCESS")

    assert [r.action_type for r in audit.get_records(action_type="SUBMIT_LEAVE")] == [
        "SUBMIT_LEAVE"
    ]


def test_both_filters_apply_together(audit):
    audit.log_event(caller_employee_id="EMP-1001", action_type="SUBMIT_LEAVE", status="SUCCESS")
    audit.log_event(caller_employee_id="EMP-1002", action_type="SUBMIT_LEAVE", status="SUCCESS")
    audit.log_event(caller_employee_id="EMP-1001", action_type="CANCEL_LEAVE", status="SUCCESS")

    matched = audit.get_records(caller_employee_id="EMP-1001", action_type="SUBMIT_LEAVE")

    assert len(matched) == 1


def test_clearing_empties_the_archive(audit):
    audit.log_event(caller_employee_id="EMP-1001", action_type="SUBMIT_LEAVE", status="SUCCESS")

    audit.clear()

    assert audit.get_records() == []


def test_the_audit_stream_handler_is_installed_only_once():
    """Every `AuditLogger` shares one named logger. Adding a handler per instance
    would duplicate each line once per object ever constructed."""
    named = logging.getLogger("hr_agent_audit")
    AuditLogger()
    before = len(named.handlers)

    AuditLogger()

    assert len(named.handlers) == before == 1


# --- the OKF policy store -----------------------------------------------------


def test_a_policy_is_retrievable_by_its_exact_section_id():
    store = OKFPolicyStore()

    doc = store.get_policy_by_section("14.1")

    assert doc is not None
    assert "relocation" in doc.tags


def test_an_unknown_section_id_reads_back_as_absent():
    """A miss must be `None`, not a placeholder: FR-5.2 forbids answering from
    a document the store could not actually produce."""
    assert OKFPolicyStore().get_policy_by_section("99.9") is None


def test_adding_a_policy_makes_it_retrievable_under_its_own_section():
    store = OKFPolicyStore()
    doc = PolicyDocument(
        section_id="22.7",
        title="Sabbatical Leave",
        category="LEAVE",
        summary="Eligible after seven continuous years.",
        details="Up to twelve weeks unpaid, subject to manager approval.",
        citation_title="View Policy Section 22.7",
        citation_url="https://hr.corp.internal/policies/22.7-sabbatical",
        tags=["sabbatical"],
    )

    store.add_policy(doc)

    assert store.get_policy_by_section("22.7") is doc


def test_adding_a_policy_under_an_existing_section_replaces_it():
    """Sections are keys, not a history: the store holds the current text only."""
    store = OKFPolicyStore()
    replacement = PolicyDocument(
        section_id="14.1",
        title="International Relocation (2027 revision)",
        category="MOBILITY",
        summary="Superseded terms.",
        details="The 2026 allowance table no longer applies.",
        citation_title="View Policy Section 14.1",
        citation_url="https://hr.corp.internal/policies/14.1-international-relocation",
        tags=["relocation"],
    )

    store.add_policy(replacement)

    assert store.get_policy_by_section("14.1").title.endswith("(2027 revision)")


# --- surrogate minting --------------------------------------------------------


def test_the_first_surrogate_for_a_label_is_numbered_one():
    assert CloudDLPInterceptor._mint("PERSON", {}) == "[PERSON_1]"


def test_a_surrogate_never_collides_with_one_already_issued():
    """Two colleagues named in one sentence must not become the same token, or
    the re-identification pass puts the wrong name back."""
    issued = {"[PERSON_1]": "Jane Doe", "[PERSON_2]": "John Smith"}

    assert CloudDLPInterceptor._mint("PERSON", issued) == "[PERSON_3]"


def test_numbering_is_kept_per_label():
    issued = {"[PERSON_1]": "Jane Doe"}

    assert CloudDLPInterceptor._mint("EMAIL_ADDRESS", issued) == "[EMAIL_ADDRESS_1]"


# --- the REST-path saga coordinator -------------------------------------------


def _leave(success=True, request_id="WW-LV-A1B2C3", message="ok", remaining=11.0):
    return SimpleNamespace(
        success=success, request_id=request_id, message=message, remaining_balance=remaining
    )


class FakeWorkWeek:
    """Records submissions and cancellations so compensation can be asserted."""

    def __init__(self, leave_result=None, error: Exception | None = None):
        self._leave_result = leave_result or _leave()
        self._error = error
        self.submitted: list[dict] = []
        self.cancelled: list[tuple[str, str]] = []

    def submit_leave_request(self, **kwargs):
        self.submitted.append(kwargs)
        if self._error:
            raise self._error
        return self._leave_result

    def cancel_leave_request(self, caller_employee_id, request_id):
        self.cancelled.append((caller_employee_id, request_id))
        return True


class FakeServiceImmediately:
    def __init__(self, error: Exception | None = None):
        self._error = error
        self.created: list[dict] = []
        self.escalated: list[dict] = []

    def create_incident_ticket(self, **kwargs):
        self.created.append(kwargs)
        if self._error:
            raise self._error
        return SimpleNamespace(ticket_id="INC0009001")

    def create_escalated_incident(self, **kwargs):
        self.escalated.append(kwargs)
        return SimpleNamespace(ticket_id="INC0009999")


class SpyAudit:
    def __init__(self):
        self.events: list[dict] = []

    def log_event(self, **kwargs):
        self.events.append(kwargs)


def _coordinator(ww=None, sn=None, logger=None):
    return SagaCoordinator(
        ww_client=ww or FakeWorkWeek(),
        sn_client=sn or FakeServiceImmediately(),
        logger=logger or SpyAudit(),
    )


def _run(coordinator):
    return coordinator.execute_medical_leave_orchestration(
        caller_employee_id="EMP-1001",
        start_date=datetime.date(2026, 9, 1),
        end_date=datetime.date(2026, 9, 15),
        days=10.0,
    )


def test_both_systems_succeeding_reports_the_leave_and_the_ticket():
    ww, sn = FakeWorkWeek(), FakeServiceImmediately()

    result = _run(_coordinator(ww, sn))

    assert result.success is True
    assert "WW-LV-A1B2C3" in result.message
    assert "INC0009001" in result.message
    assert [s.status for s in result.steps_executed] == ["COMPLETED", "COMPLETED"]
    assert result.compensated is False


def test_the_leave_is_filed_as_sick_loa_for_the_caller_themselves():
    """UC-2.2 is a self-service medical filing; the target must not be delegable."""
    ww = FakeWorkWeek()

    _run(_coordinator(ww))

    assert ww.submitted[0]["leave_type"] == "Sick_LOA"
    assert ww.submitted[0]["target_employee_id"] == "EMP-1001"


def test_a_refused_leave_stops_before_the_ticket_is_raised():
    """Nothing to compensate: step 1 never took effect, so step 2 must not run."""
    ww = FakeWorkWeek(leave_result=_leave(success=False, message="Insufficient sick balance."))
    sn = FakeServiceImmediately()

    result = _run(_coordinator(ww, sn))

    assert result.success is False
    assert result.compensated is False
    assert "Insufficient sick balance." in result.message
    assert sn.created == []
    assert result.steps_executed[0].status == "FAILED"


def test_a_workweek_outage_is_reported_without_a_rollback():
    """An exception on step 1 leaves no external record, so there is nothing to undo."""
    ww = FakeWorkWeek(error=RuntimeError("WorkWeek 503"))
    sn = FakeServiceImmediately()

    result = _run(_coordinator(ww, sn))

    assert result.success is False
    assert result.compensated is False
    assert "WorkWeek 503" in result.message
    assert result.steps_executed[0].error == "WorkWeek 503"
    assert ww.cancelled == []
    assert sn.created == []


def test_an_itsm_failure_rolls_the_leave_back_and_escalates():
    ww = FakeWorkWeek()
    sn = FakeServiceImmediately(error=RuntimeError("ITSM 503"))

    result = _run(_coordinator(ww, sn))

    assert result.compensated is True
    assert ww.cancelled == [("EMP-1001", "WW-LV-A1B2C3")]
    assert result.steps_executed[0].status == "COMPENSATED"
    assert result.steps_executed[1].status == "FAILED"
    assert result.escalation_ticket_id == "INC0009999"
    assert "INC0009999" in result.message


def test_the_compensation_is_announced_to_the_audit_archive_before_it_runs():
    """§7.1: the rollback is itself an automated write and has to be evidenced."""
    spy = SpyAudit()

    _run(_coordinator(sn=FakeServiceImmediately(error=RuntimeError("ITSM 503")), logger=spy))

    assert spy.events[0]["action_type"] == "SAGA_BACKWARD_COMPENSATION"
    assert spy.events[0]["status"] == "TRIGGERED"
    assert "ITSM 503" in spy.events[0]["details"]["reason"]


def test_the_escalation_ticket_names_the_leave_that_was_cancelled():
    """A PeopleOps operator picking this up needs the reference, not just a note."""
    sn = FakeServiceImmediately(error=RuntimeError("ITSM 503"))

    _run(_coordinator(sn=sn))

    assert sn.escalated[0]["priority"] == "2 - High"
    assert "WW-LV-A1B2C3" in sn.escalated[0]["description"]


def test_nothing_is_cancelled_when_workweek_returned_no_reference():
    """Success without a request id means there is no handle to cancel. Calling
    `cancel_leave_request(None)` would either raise or cancel something else."""
    ww = FakeWorkWeek(leave_result=_leave(request_id=None))
    sn = FakeServiceImmediately(error=RuntimeError("ITSM 503"))

    result = _run(_coordinator(ww, sn))

    assert ww.cancelled == []
    assert result.compensated is True
    assert result.steps_executed[0].status == "COMPLETED"


def test_the_coordinator_defaults_to_the_shared_clients():
    from src.integrations.service_immediately.client import service_immediately_client
    from src.integrations.workweek.client import workweek_client
    from src.telemetry.audit_logger import audit_logger

    coordinator = SagaCoordinator()

    assert coordinator._ww_client is workweek_client
    assert coordinator._sn_client is service_immediately_client
    assert coordinator._logger is audit_logger
