"""The ServiceImmediately client adapter: the four FR-4.2 operations end to end.

This adapter carries the ITSM half of FR-4.2 - `si.get_incident`,
`si.create_incident`, `si.post_comment`, `si.update_status` - and applies the
FR-4.3 guardrails (transition legality, duplicate scan, priority verification)
before any of the writes. Only `create_incident` had coverage, through the agent
tests; the other three were exercised nowhere, and all three were broken:

* `add_comment` called `_service.add_comment`, which does not exist, and built a
  `TicketComment` from field names the model does not have. Both paths raised.
* `update_incident_status` called `_guardrails.validate_status_transition`,
  also not a real name, and returned the bool from `update_status` where its
  signature promises a ticket.
* the guardrail's transition table used a vocabulary ("Work in Progress") that
  no ticket in the system is ever in, so every transition off the seeded
  "In Progress" ticket was refused as illegal.

The live/mock split follows the same `_should_use_live_mcp` convention as the
WorkWeek adapter: under pytest, EMP-509 goes live and everyone else goes to the
mock service.
"""

from __future__ import annotations

import datetime
import sys

import pytest

from src.guardrails.operation_guardrails import OperationGuardrailEngine
from src.integrations.service_immediately.client import ServiceImmediatelyClient
from src.integrations.service_immediately.mock_service import ServiceImmediatelyMockService
from src.integrations.service_immediately.models import IncidentTicket

LIVE = "EMP-509"
MOCK = "EMP-1001"

NOW = datetime.datetime(2026, 8, 27, 10, 0, 0, tzinfo=datetime.timezone.utc)


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

    def list_tickets(self, employee_id):
        return self._answer("list_tickets", employee_id=employee_id)

    def create_ticket(self, **kwargs):
        return self._answer("create_ticket", **kwargs)

    def add_ticket_comment(self, **kwargs):
        return self._answer("add_ticket_comment", **kwargs)

    def update_ticket_status(self, **kwargs):
        return self._answer("update_ticket_status", **kwargs)

    def named(self, name: str) -> list[dict]:
        return [kwargs for called, kwargs in self.calls if called == name]


class SpyLogger:
    def __init__(self):
        self.events: list[dict] = []

    def log_event(self, **kwargs):
        self.events.append(kwargs)

    def statuses(self, action_type: str) -> list[str]:
        return [e["status"] for e in self.events if e["action_type"] == action_type]


@pytest.fixture
def service() -> ServiceImmediatelyMockService:
    return ServiceImmediatelyMockService()


def make_client(mcp=None, service=None, spy=None) -> ServiceImmediatelyClient:
    return ServiceImmediatelyClient(
        service=service if service is not None else ServiceImmediatelyMockService(),
        mcp_client=mcp or FakeMCP(),
        guardrails=OperationGuardrailEngine(),
        logger=spy or SpyLogger(),
    )


def _seed(
    service: ServiceImmediatelyMockService,
    requester: str = MOCK,
    status: str | None = None,
    **overrides
) -> IncidentTicket:
    """Add one ticket on top of the two the mock service seeds itself.

    `create_incident` always opens a ticket as "New" - the ITSM decides that,
    not the caller - so a later lifecycle state is set on the record afterwards.
    """
    fields = {
        "requester_id": requester,
        "category": "IT_NETWORK",
        "priority": "3 - Moderate",
        "short_description": "VPN drops",
    }
    fields.update(overrides)
    ticket = service.create_incident(**fields)
    if status:
        ticket.status = status
    return ticket


# --- the live / mock branch --------------------------------------------------


def test_a_non_live_employee_never_reaches_the_mcp_client(service):
    mcp = FakeMCP()
    _seed(service)

    assert make_client(mcp=mcp, service=service).list_tickets_for_user(MOCK)
    assert mcp.calls == []


def test_outside_a_test_run_every_employee_goes_live(monkeypatch):
    """The branch the server and the CLI take; see the WorkWeek adapter tests."""
    monkeypatch.delitem(sys.modules, "pytest")

    assert make_client()._should_use_live_mcp(MOCK) is True


def test_live_mcp_is_bypassed_entirely_when_disabled(service):
    """`USE_LIVE_MCP=false` must reach the mock even for EMP-509."""
    mcp = FakeMCP(list_tickets=[{"ticket_id": "INC-LIVE"}])
    client = make_client(mcp=mcp, service=service)
    client._use_live_mcp = False

    assert [t.ticket_id for t in client.list_tickets_for_user(LIVE)] == ["INC123401"]
    assert mcp.calls == []


def test_a_client_with_no_mcp_client_uses_the_service(service):
    client = ServiceImmediatelyClient(service=service, mcp_client=None, logger=SpyLogger())
    client._mcp_client = None

    assert [t.ticket_id for t in client.list_tickets_for_user(LIVE)] == ["INC123401"]


# --- listing tickets ---------------------------------------------------------


def test_live_tickets_are_mapped_field_by_field():
    mcp = FakeMCP(
        list_tickets=[
            {
                "ticket_id": "INC0003359",
                "requested_by": LIVE,
                "category": "Network",
                "priority": "2 - High",
                "status": "In Progress",
                "short_description": "VPN drops",
                "created_at": "2026-08-27T09:00:00+00:00",
            }
        ]
    )

    (ticket,) = make_client(mcp=mcp).list_tickets_for_user(LIVE)

    assert ticket.ticket_id == "INC0003359"
    assert ticket.status == "In Progress"
    assert ticket.priority == "2 - High"
    assert ticket.created_at == "2026-08-27T09:00:00+00:00"


def test_missing_live_ticket_fields_fall_back_to_documented_defaults():
    mcp = FakeMCP(list_tickets=[{}])

    (ticket,) = make_client(mcp=mcp).list_tickets_for_user(LIVE)

    assert ticket.ticket_id == "INC0001000"
    assert ticket.requester_id == LIVE
    assert ticket.status == "New"
    assert ticket.created_at


def test_a_failed_live_listing_falls_back_to_the_mock_service(service):
    """Unlike a profile read, an empty ticket list is not a claim about anyone,
    so degrading here is safe."""
    _seed(service, requester=LIVE)
    mcp = FakeMCP(list_tickets=ConnectionError("tenant down"))

    assert len(make_client(mcp=mcp, service=service).list_tickets_for_user(LIVE)) == 2


# --- reading one ticket (si.get_incident) ------------------------------------


def test_a_ticket_read_is_audited_as_success(service):
    ticket = _seed(service)
    spy = SpyLogger()

    found = make_client(service=service, spy=spy).get_ticket_details(MOCK, ticket.ticket_id)

    assert found.ticket_id == ticket.ticket_id
    assert spy.statuses("SERVICE_IMMEDIATELY_GET_TICKET") == ["SUCCESS"]


def test_an_unknown_ticket_is_audited_as_not_found(service):
    spy = SpyLogger()

    assert make_client(service=service, spy=spy).get_ticket_details(MOCK, "INC-NOPE") is None
    assert spy.statuses("SERVICE_IMMEDIATELY_GET_TICKET") == ["NOT_FOUND"]


# --- creating an incident (si.create_incident, FR-4.3) -----------------------


def test_a_second_ticket_in_the_same_category_is_suppressed(service):
    """FR-4.3: same requester, same category, inside the 10-minute window."""
    _seed(service)
    spy = SpyLogger()

    with pytest.raises(ValueError, match="Duplicate ticket detected"):
        make_client(service=service, spy=spy).create_incident_ticket(
            MOCK, "IT_NETWORK", "3 - Moderate", "VPN drops again"
        )

    assert spy.statuses("SERVICE_IMMEDIATELY_CREATE_INCIDENT") == ["REFUSED"]


def test_the_same_category_outside_the_window_is_allowed(service):
    ticket = _seed(service)
    ticket.created_at = (NOW - datetime.timedelta(minutes=11)).isoformat()

    created = make_client(service=service).create_incident_ticket(
        MOCK, "IT_NETWORK", "3 - Moderate", "VPN drops again", now=NOW
    )

    assert created.ticket_id != ticket.ticket_id


def test_a_different_category_is_not_a_duplicate(service):
    _seed(service)

    created = make_client(service=service).create_incident_ticket(
        MOCK, "IT_HARDWARE", "3 - Moderate", "Laptop will not boot"
    )

    assert created.category == "IT_HARDWARE"


@pytest.mark.parametrize(
    ("description", "requested", "expected"),
    [
        ("Site-wide outage", "3 - Moderate", "1 - Critical"),
        ("I am blocked and cannot work", "4 - Low", "2 - High"),
        ("Printer is slow", "1 - Critical", "3 - Moderate"),
        ("Printer is slow", "4 - Low", "4 - Low"),
        ("Printer is slow", "P1", "3 - Moderate"),
    ],
)
def test_the_priority_written_is_the_verified_one_not_the_requested_one(
    service, description, requested, expected
):
    """FR-4.3: the caller asks, the guardrail decides."""
    created = make_client(service=service).create_incident_ticket(
        MOCK, "IT_GENERAL", requested, description
    )

    assert created.priority == expected


def test_a_created_ticket_is_audited_with_its_reference(service):
    spy = SpyLogger()

    created = make_client(service=service, spy=spy).create_incident_ticket(
        MOCK, "IT_NETWORK", "3 - Moderate", "VPN drops"
    )

    (event,) = [e for e in spy.events if e["action_type"] == "SERVICE_IMMEDIATELY_CREATE_INCIDENT"]
    assert event["status"] == "SUCCESS"
    assert event["details"]["ticket_id"] == created.ticket_id


# --- creating an incident over the live path ---------------------------------


def test_a_live_ticket_id_comes_from_structured_content():
    mcp = FakeMCP(create_ticket={"structuredContent": {"result": "INC0003360"}})

    created = make_client(mcp=mcp).create_incident_ticket(
        LIVE, "IT_NETWORK", "3 - Moderate", "VPN drops"
    )

    assert created.ticket_id == "INC0003360"
    assert created.status == "New"
    (sent,) = mcp.named("create_ticket")
    assert sent["requested_by"] == LIVE
    assert sent["priority"] == "3 - Moderate"


def test_a_live_ticket_id_is_decoded_from_a_json_content_block():
    mcp = FakeMCP(create_ticket={"content": [{"text": '{"ticket_id": "INC0003361"}'}]})

    created = make_client(mcp=mcp).create_incident_ticket(
        LIVE, "IT_NETWORK", "3 - Moderate", "VPN drops"
    )

    assert created.ticket_id == "INC0003361"


def test_a_live_ticket_id_is_lifted_out_of_prose():
    mcp = FakeMCP(create_ticket={"content": [{"text": 'Created ticket "INC0003362", assigned.'}]})

    created = make_client(mcp=mcp).create_incident_ticket(
        LIVE, "IT_NETWORK", "3 - Moderate", "VPN drops"
    )

    assert created.ticket_id == "INC0003362"


def test_json_that_is_not_a_ticket_record_leaves_the_default_in_place():
    mcp = FakeMCP(create_ticket={"content": [{"text": '{"status": "queued"}'}]})

    created = make_client(mcp=mcp).create_incident_ticket(
        LIVE, "IT_NETWORK", "3 - Moderate", "VPN drops"
    )

    assert created.ticket_id == "INC0009999"


def test_prose_with_no_reference_at_all_leaves_the_default_in_place():
    mcp = FakeMCP(create_ticket={"content": [{"text": "Your request has been received."}]})

    created = make_client(mcp=mcp).create_incident_ticket(
        LIVE, "IT_NETWORK", "3 - Moderate", "VPN drops"
    )

    assert created.ticket_id == "INC0009999"


def test_an_empty_content_list_leaves_the_default_in_place():
    mcp = FakeMCP(create_ticket={"content": []})

    created = make_client(mcp=mcp).create_incident_ticket(
        LIVE, "IT_NETWORK", "3 - Moderate", "VPN drops"
    )

    assert created.ticket_id == "INC0009999"


def test_a_non_dict_live_response_leaves_the_default_in_place():
    mcp = FakeMCP(create_ticket="INC0003363")

    created = make_client(mcp=mcp).create_incident_ticket(
        LIVE, "IT_NETWORK", "3 - Moderate", "VPN drops"
    )

    assert created.ticket_id == "INC0009999"


def test_a_structured_result_that_is_itself_json_is_unwrapped():
    """Some tenants answer `structuredContent.result` with a serialised record."""
    mcp = FakeMCP(create_ticket={"structuredContent": {"result": '{"ticket_id": "INC0003364"}'}})

    created = make_client(mcp=mcp).create_incident_ticket(
        LIVE, "IT_NETWORK", "3 - Moderate", "VPN drops"
    )

    assert created.ticket_id == "INC0003364"


def test_an_unparseable_structured_result_is_kept_verbatim():
    mcp = FakeMCP(create_ticket={"structuredContent": {"result": "{not json"}})

    created = make_client(mcp=mcp).create_incident_ticket(
        LIVE, "IT_NETWORK", "3 - Moderate", "VPN drops"
    )

    assert created.ticket_id == "{not json"


def test_a_failed_live_creation_falls_back_to_the_mock_service(service):
    """A ticket the employee was promised must exist somewhere."""
    mcp = FakeMCP(create_ticket=ConnectionError("tenant down"))
    spy = SpyLogger()

    created = make_client(mcp=mcp, service=service, spy=spy).create_incident_ticket(
        LIVE, "IT_NETWORK", "3 - Moderate", "VPN drops"
    )

    assert created.ticket_id.startswith("INC")
    assert spy.statuses("SERVICE_IMMEDIATELY_CREATE_INCIDENT") == ["SUCCESS"]


# --- comments (si.post_comment) ----------------------------------------------


def test_a_comment_is_appended_to_the_ticket_timeline(service):
    ticket = _seed(service)
    spy = SpyLogger()

    comment = make_client(service=service, spy=spy).add_comment(MOCK, ticket.ticket_id, "any update?")

    assert comment.author_id == MOCK
    assert comment.comment_text == "any update?"
    assert service.get_ticket(ticket.ticket_id).comments == [comment]
    assert spy.statuses("SERVICE_IMMEDIATELY_ADD_COMMENT") == ["SUCCESS"]


def test_a_comment_carries_the_orchestrator_origin(service):
    ticket = _seed(service)
    client = ServiceImmediatelyClient(
        service=service, mcp_client=FakeMCP(), logger=SpyLogger(), origin="HR_AGENT_TEST"
    )

    assert client.add_comment(MOCK, ticket.ticket_id, "note").origin == "HR_AGENT_TEST"


def test_a_comment_on_a_ticket_that_does_not_exist_is_audited_as_not_found(service):
    spy = SpyLogger()

    assert make_client(service=service, spy=spy).add_comment(MOCK, "INC-NOPE", "hello") is None
    assert spy.statuses("SERVICE_IMMEDIATELY_ADD_COMMENT") == ["NOT_FOUND"]


def test_a_live_comment_is_sent_with_its_author():
    mcp = FakeMCP(add_ticket_comment={"comment_id": "CMT-ABC123"})

    comment = make_client(mcp=mcp).add_comment(LIVE, "INC0003359", "any update?")

    assert comment.comment_id == "CMT-ABC123"
    (sent,) = mcp.named("add_ticket_comment")
    assert sent == {"ticket_id": "INC0003359", "author": LIVE, "comment": "any update?"}


@pytest.mark.parametrize("key", ["comment_id", "sys_id", "id"])
def test_any_reference_the_itsm_returns_is_the_one_kept(key):
    comment = make_client(mcp=FakeMCP(add_ticket_comment={key: "REF-1"})).add_comment(
        LIVE, "INC-1", "note"
    )

    assert comment.comment_id == "REF-1"


def test_a_live_comment_with_no_reference_still_gets_a_handle():
    """Prose responses are the common case; the audit line needs an id anyway."""
    comment = make_client(mcp=FakeMCP(add_ticket_comment={"content": [{"text": "Added"}]})).add_comment(
        LIVE, "INC-1", "note"
    )

    assert comment.comment_id.startswith("CMT-")


def test_a_non_dict_comment_response_still_gets_a_handle():
    comment = make_client(mcp=FakeMCP(add_ticket_comment="Added")).add_comment(LIVE, "INC-1", "note")

    assert comment.comment_id.startswith("CMT-")


def test_a_failed_live_comment_falls_back_to_the_mock_service(service):
    ticket = _seed(service, requester=LIVE)
    mcp = FakeMCP(add_ticket_comment=ConnectionError("tenant down"))

    comment = make_client(mcp=mcp, service=service).add_comment(LIVE, ticket.ticket_id, "note")

    assert comment.comment_text == "note"


# --- status transitions (si.update_status, FR-4.3) ---------------------------


def test_a_legal_transition_is_applied_and_the_ticket_comes_back(service):
    ticket = _seed(service)
    spy = SpyLogger()

    updated = make_client(service=service, spy=spy).update_incident_status(
        MOCK, ticket.ticket_id, "In Progress"
    )

    assert isinstance(updated, IncidentTicket)
    assert updated.status == "In Progress"
    assert spy.statuses("SERVICE_IMMEDIATELY_UPDATE_STATUS") == ["SUCCESS"]


def test_the_seeded_in_progress_ticket_can_be_resolved(service):
    """The regression that motivated the vocabulary fix: "In Progress" was not
    a key in the transition table, so this was refused as an illegal move."""
    ticket = _seed(service, status="In Progress")

    updated = make_client(service=service).update_incident_status(
        MOCK, ticket.ticket_id, "Resolved", resolution_notes="Switch replaced"
    )

    assert updated.status == "Resolved"


def test_new_straight_to_closed_is_refused(service):
    """The illegal transition FR-4.3 names explicitly."""
    ticket = _seed(service)
    spy = SpyLogger()

    with pytest.raises(ValueError, match="Invalid ticket status transition"):
        make_client(service=service, spy=spy).update_incident_status(MOCK, ticket.ticket_id, "Closed")

    assert spy.statuses("SERVICE_IMMEDIATELY_UPDATE_STATUS") == ["REFUSED"]
    assert service.get_ticket(ticket.ticket_id).status == "New"


def test_a_closed_ticket_is_terminal(service):
    ticket = _seed(service, status="Closed")

    with pytest.raises(ValueError):
        make_client(service=service).update_incident_status(MOCK, ticket.ticket_id, "In Progress")


def test_resolution_notes_are_recorded_on_the_timeline(service):
    ticket = _seed(service, status="In Progress")

    make_client(service=service).update_incident_status(
        MOCK, ticket.ticket_id, "Resolved", resolution_notes="Switch replaced"
    )

    (note,) = service.get_ticket(ticket.ticket_id).comments
    assert "Switch replaced" in note.comment_text


def test_updating_a_ticket_that_does_not_exist_is_audited_as_failed(service):
    """No current ticket means no transition to check, so this reaches the write."""
    spy = SpyLogger()

    assert make_client(service=service, spy=spy).update_incident_status(
        MOCK, "INC-NOPE", "Resolved"
    ) is None
    assert spy.statuses("SERVICE_IMMEDIATELY_UPDATE_STATUS") == ["FAILED"]


def test_a_live_status_update_is_sent_before_the_local_write():
    mcp = FakeMCP()

    make_client(mcp=mcp).update_incident_status(LIVE, "INC0003359", "Resolved", "Fixed")

    (sent,) = mcp.named("update_ticket_status")
    assert sent == {
        "ticket_id": "INC0003359",
        "status": "Resolved",
        "resolution_notes": "Fixed",
        "updated_by": LIVE,
    }


def test_a_failed_live_status_update_does_not_abort_the_turn(service):
    ticket = _seed(service, requester=LIVE, status="In Progress")
    mcp = FakeMCP(update_ticket_status=ConnectionError("tenant down"))

    updated = make_client(mcp=mcp, service=service).update_incident_status(
        LIVE, ticket.ticket_id, "Resolved"
    )

    assert updated.status == "Resolved"


# --- hardware and facilities (UC-2.1, UC-2.3) --------------------------------


def test_a_hardware_request_records_the_policy_that_authorised_it(service):
    spy = SpyLogger()

    req = make_client(service=service, spy=spy).create_hardware_request(
        MOCK, "27in_Monitor", "1 Marina Bay, Singapore"
    )

    assert req.item == "27in_Monitor"
    assert req.referenced_policy_section == "Sec 08.3"
    assert req.shipping_address == "1 Marina Bay, Singapore"
    assert spy.statuses("SERVICE_IMMEDIATELY_REQUEST_HARDWARE") == ["SUCCESS"]


def test_a_facilities_ticket_carries_the_office_and_start_date(service):
    spy = SpyLogger()

    ticket = make_client(service=service, spy=spy).create_facilities_ticket(
        MOCK, "BADGE_ACCESS", "London_Pancras", "2026-09-26"
    )

    assert ticket.office == "London_Pancras"
    assert ticket.start_date == "2026-09-26"
    assert spy.statuses("SERVICE_IMMEDIATELY_REQUEST_FACILITIES") == ["SUCCESS"]


# --- saga escalation ---------------------------------------------------------


def test_an_escalation_is_attributed_to_the_orchestrator_not_the_employee(service):
    """A rollback ticket is the system asking a human for help, so it must not
    look like the employee filed it - and must not trip their duplicate scan."""
    ticket = make_client(service=service).create_escalated_incident(
        "2 - High", "Manual medical leave setup required"
    )

    assert ticket.requester_id == "SYSTEM_ORCHESTRATOR"
    assert ticket.category == "SAGA_ESCALATION"
    assert ticket.priority == "2 - High"


def test_an_escalation_is_created_even_while_the_backend_is_failing(service):
    """The escalation is the last thing standing when everything else broke."""
    service.set_simulate_error(True)

    assert make_client(service=service).create_escalated_incident("2 - High", "rollback") is not None
