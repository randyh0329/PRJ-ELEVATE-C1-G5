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
    """Verify duplicate ticket creation within 30 minutes is rejected."""
    engine = OperationGuardrailEngine()
    now = datetime.datetime(2026, 8, 27, 10, 0, 0, tzinfo=datetime.timezone.utc)
    recent_ticket_time = (now - datetime.timedelta(minutes=10)).isoformat()

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
        window_minutes=30,
        now=now
    )
    assert not res.is_valid
    assert "Duplicate ticket detected" in res.error_message


def test_ticket_status_state_machine():
    """Verify valid and invalid ticket status transitions."""
    engine = OperationGuardrailEngine()

    # Valid transition
    res_valid = engine.validate_ticket_transition("New", "Work in Progress")
    assert res_valid.is_valid

    # Invalid transition (New directly to Closed)
    res_invalid = engine.validate_ticket_transition("New", "Closed")
    assert not res_invalid.is_valid
