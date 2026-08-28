"""Unit tests for operational guardrails."""
import datetime

from src.guardrails.operation_guardrails import OperationGuardrailEngine


def test_leave_guardrail_insufficient_balance():
    """Verify leave request exceeding balance is rejected."""
    engine = OperationGuardrailEngine()
    today = datetime.date(2026, 8, 27)
    res = engine.validate_leave_request(
        days_requested=15.0,
        remaining_balance=14.0,
        start_date=today,
        end_date=today + datetime.timedelta(days=15),
        reference_date=today
    )
    assert not res.is_valid
    assert "Insufficient leave balance" in res.error_message


def test_leave_guardrail_past_date():
    """Verify leave request for past dates is rejected."""
    engine = OperationGuardrailEngine()
    today = datetime.date(2026, 8, 27)
    past_date = datetime.date(2026, 8, 20)
    res = engine.validate_leave_request(
        days_requested=2.0,
        remaining_balance=14.0,
        start_date=past_date,
        end_date=past_date + datetime.timedelta(days=1),
        reference_date=today
    )
    assert not res.is_valid
    assert "in the past" in res.error_message


def test_ticket_deduplication_guardrail():
    """Verify duplicate ticket creation within the FR-4.3 window is rejected."""
    engine = OperationGuardrailEngine()
    now = datetime.datetime(2026, 8, 27, 10, 0, 0, tzinfo=datetime.timezone.utc)
    recent_ticket_time = (now - datetime.timedelta(minutes=4)).isoformat()

    existing_tickets = [{
        "ticket_id": "INC123450",
        "requester_id": "EMP-1001",
        "category": "IT_NETWORK",
        "created_at": recent_ticket_time
    }]

    res = engine.validate_ticket_deduplication(
        requester_id="EMP-1001",
        category="IT_NETWORK",
        existing_tickets=existing_tickets,
        window_minutes=10,
        now=now
    )
    assert not res.is_valid
    assert "Duplicate ticket detected" in res.error_message


def test_ticket_status_state_machine():
    """Verify valid and invalid ticket status transitions."""
    engine = OperationGuardrailEngine()

    # Valid transition
    res_valid = engine.validate_ticket_transition("New", "In Progress")
    assert res_valid.is_valid

    # Invalid transition (New directly to Closed)
    res_invalid = engine.validate_ticket_transition("New", "Closed")
    assert not res_invalid.is_valid


def test_leave_guardrail_zero_days():
    """Verify a zero-day request is rejected before any balance arithmetic."""
    engine = OperationGuardrailEngine()
    today = datetime.date(2026, 8, 27)
    res = engine.validate_leave_request(
        days_requested=0.0,
        remaining_balance=14.0,
        start_date=today,
        end_date=today,
        reference_date=today
    )
    assert not res.is_valid
    assert res.rule_name == "LEAVE_POSITIVE_DAYS_CONSTRAINT"


def test_leave_guardrail_end_before_start():
    """Verify an inverted date range is rejected."""
    engine = OperationGuardrailEngine()
    today = datetime.date(2026, 8, 27)
    res = engine.validate_leave_request(
        days_requested=2.0,
        remaining_balance=14.0,
        start_date=today + datetime.timedelta(days=5),
        end_date=today + datetime.timedelta(days=1),
        reference_date=today
    )
    assert not res.is_valid
    assert res.rule_name == "LEAVE_TEMPORAL_ORDER_CONSTRAINT"


def test_leave_guardrail_accepts_a_well_formed_future_request():
    """The pass case: in balance, correctly ordered, and not in the past."""
    engine = OperationGuardrailEngine()
    today = datetime.date(2026, 8, 27)
    res = engine.validate_leave_request(
        days_requested=3.0,
        remaining_balance=14.0,
        start_date=today + datetime.timedelta(days=7),
        end_date=today + datetime.timedelta(days=9),
        reference_date=today
    )
    assert res.is_valid
    assert res.error_message is None


def test_leave_guardrail_defaults_to_the_business_clock():
    """Omitting `reference_date` must fall back to `business_today()`, not fail open."""
    engine = OperationGuardrailEngine()
    res = engine.validate_leave_request(
        days_requested=1.0,
        remaining_balance=5.0,
        start_date=datetime.date(2020, 1, 1),
        end_date=datetime.date(2020, 1, 2)
    )
    assert not res.is_valid
    assert res.rule_name == "LEAVE_PAST_DATE_CONSTRAINT"


def test_contact_guardrail_rejects_a_malformed_phone_number():
    """A number with letters in it is not a number the HCM backend will accept."""
    engine = OperationGuardrailEngine()
    res = engine.validate_contact_update(phone_number="call-me", home_address=None)
    assert not res.is_valid
    assert res.rule_name == "CONTACT_PHONE_SYNTAX_CONSTRAINT"


def test_contact_guardrail_rejects_a_too_short_phone_number():
    """Fewer than seven digits cannot be a dialable number anywhere."""
    engine = OperationGuardrailEngine()
    res = engine.validate_contact_update(phone_number="+65 123", home_address=None)
    assert not res.is_valid
    assert res.rule_name == "CONTACT_PHONE_SYNTAX_CONSTRAINT"


def test_contact_guardrail_rejects_a_truncated_address():
    """A stub address would be written over a good one, so it is refused."""
    engine = OperationGuardrailEngine()
    res = engine.validate_contact_update(phone_number=None, home_address="  12 Rd  ")
    assert not res.is_valid
    assert res.rule_name == "CONTACT_ADDRESS_LENGTH_CONSTRAINT"


def test_contact_guardrail_accepts_a_dial_code_and_a_full_address():
    engine = OperationGuardrailEngine()
    res = engine.validate_contact_update(
        phone_number="+65 6555 0100",
        home_address="1 Raffles Place, Singapore 048616"
    )
    assert res.is_valid
    assert res.rule_name == "CONTACT_VALIDATION_PASSED"


def test_contact_guardrail_passes_when_nothing_is_being_changed():
    """Both fields optional: an empty update is vacuously valid."""
    assert OperationGuardrailEngine().validate_contact_update(None, None).is_valid


def test_deduplication_ignores_a_ticket_with_no_creation_timestamp():
    """Without a timestamp there is no window to compare against, so it cannot match."""
    engine = OperationGuardrailEngine()
    res = engine.validate_ticket_deduplication(
        requester_id="EMP-1001",
        category="IT_NETWORK",
        existing_tickets=[{"ticket_id": "INC1", "requester_id": "EMP-1001", "category": "IT_NETWORK"}],
        now=datetime.datetime(2026, 8, 27, 10, 0, tzinfo=datetime.timezone.utc)
    )
    assert res.is_valid


def test_deduplication_reads_a_naive_timestamp_as_utc():
    """WorkWeek returns some timestamps without an offset; comparing them to an
    aware `now` would raise, so they are pinned to UTC rather than skipped."""
    engine = OperationGuardrailEngine()
    now = datetime.datetime(2026, 8, 27, 10, 0, tzinfo=datetime.timezone.utc)
    res = engine.validate_ticket_deduplication(
        requester_id="EMP-1001",
        category="IT_NETWORK",
        existing_tickets=[{
            "ticket_id": "INC1",
            "requester_id": "EMP-1001",
            "category": "IT_NETWORK",
            "created_at": "2026-08-27T09:58:00",
        }],
        now=now
    )
    assert not res.is_valid
    assert "INC1" in res.error_message


def test_deduplication_ignores_an_unparseable_timestamp():
    """A corrupt `created_at` must not take down ticket creation for the caller."""
    engine = OperationGuardrailEngine()
    res = engine.validate_ticket_deduplication(
        requester_id="EMP-1001",
        category="IT_NETWORK",
        existing_tickets=[{
            "ticket_id": "INC1",
            "requester_id": "EMP-1001",
            "category": "IT_NETWORK",
            "created_at": "last tuesday",
        }],
        now=datetime.datetime(2026, 8, 27, 10, 0, tzinfo=datetime.timezone.utc)
    )
    assert res.is_valid


def test_deduplication_allows_a_repeat_outside_the_window():
    """FR-4.3 bounds the suppression at ten minutes; past that it is a new issue."""
    engine = OperationGuardrailEngine()
    now = datetime.datetime(2026, 8, 27, 10, 0, tzinfo=datetime.timezone.utc)
    res = engine.validate_ticket_deduplication(
        requester_id="EMP-1001",
        category="IT_NETWORK",
        existing_tickets=[{
            "ticket_id": "INC1",
            "requester_id": "EMP-1001",
            "category": "IT_NETWORK",
            "created_at": (now - datetime.timedelta(minutes=45)).isoformat(),
        }],
        now=now
    )
    assert res.is_valid


def test_deduplication_only_suppresses_the_same_requester_and_category():
    """Two employees hitting the same outage must both get a ticket."""
    engine = OperationGuardrailEngine()
    now = datetime.datetime(2026, 8, 27, 10, 0, tzinfo=datetime.timezone.utc)
    recent = (now - datetime.timedelta(minutes=1)).isoformat()
    existing = [
        {"ticket_id": "INC1", "requester_id": "EMP-1002", "category": "IT_NETWORK", "created_at": recent},
        {"ticket_id": "INC2", "requester_id": "EMP-1001", "category": "FACILITIES", "created_at": recent},
    ]

    res = engine.validate_ticket_deduplication(
        requester_id="EMP-1001", category="IT_NETWORK", existing_tickets=existing, now=now
    )
    assert res.is_valid


def test_deduplication_uses_wall_clock_now_when_none_is_supplied():
    """Production passes no `now`; the freshly stamped ticket must still match."""
    engine = OperationGuardrailEngine()
    created = datetime.datetime.now(datetime.timezone.utc).isoformat()

    res = engine.validate_ticket_deduplication(
        requester_id="EMP-1001",
        category="IT_NETWORK",
        existing_tickets=[{
            "ticket_id": "INC1",
            "requester_id": "EMP-1001",
            "category": "IT_NETWORK",
            "created_at": created,
        }],
    )
    assert not res.is_valid


def test_a_closed_ticket_cannot_be_reopened():
    """`Closed` is terminal in the §5.9 lifecycle - reopening means a new ticket."""
    engine = OperationGuardrailEngine()
    res = engine.validate_ticket_transition("Closed", "In Progress")
    assert not res.is_valid
    assert res.rule_name == "TICKET_STATE_MACHINE_CONSTRAINT"


def test_a_status_outside_the_lifecycle_allows_no_transition_at_all():
    """The vocabulary is the enum's. An unknown current state is not a licence."""
    assert not OperationGuardrailEngine().validate_ticket_transition(
        "Work in Progress", "Resolved"
    ).is_valid


def test_an_in_progress_ticket_can_be_resolved():
    """The regression this pins: "In Progress" once matched no key, so every
    transition off the enum's own value was refused as illegal."""
    assert OperationGuardrailEngine().validate_ticket_transition("In Progress", "Resolved").is_valid


def test_an_outage_is_critical_whatever_priority_was_asked_for():
    engine = OperationGuardrailEngine()
    assert engine.verify_priority_assignment(
        "Network", "Site-wide outage in the Singapore office", "4 - Low"
    ) == "1 - Critical"


def test_a_blocked_employee_is_high_priority():
    engine = OperationGuardrailEngine()
    assert engine.verify_priority_assignment(
        "Hardware", "I am blocked and cannot work", "4 - Low"
    ) == "2 - High"


def test_self_declared_critical_without_an_outage_is_downgraded():
    """Otherwise every requester is P1 and the queue stops meaning anything."""
    engine = OperationGuardrailEngine()
    assert engine.verify_priority_assignment(
        "Hardware", "My mouse is faulty", "1 - Critical"
    ) == "3 - Moderate"


def test_a_reasonable_requested_priority_is_honoured():
    engine = OperationGuardrailEngine()
    assert engine.verify_priority_assignment("Hardware", "Spare charger", "4 - Low") == "4 - Low"


def test_a_priority_outside_the_vocabulary_falls_back_to_moderate():
    engine = OperationGuardrailEngine()
    assert engine.verify_priority_assignment("Hardware", "Spare charger", "P0!!!") == "3 - Moderate"
