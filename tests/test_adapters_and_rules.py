import pytest
import time
from fastapi import HTTPException
from src.adapters.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerOpenException
from src.adapters.rules_engine import rules_engine
from src.storage.firestore import firestore_store
from src.models.common import PriorityEnum, TicketStateEnum


def test_circuit_breaker_state_machine():
    cb = CircuitBreaker("test_cb", failure_threshold=3, rolling_window_seconds=10.0, cooldown_seconds=0.2)
    assert cb.state == CircuitState.CLOSED
    assert cb.can_execute() is True

    # Record 2 failures -> still closed
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.CLOSED

    # 3rd failure -> trips to OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert cb.can_execute() is False

    # Wait for cooldown
    time.sleep(0.25)
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Probe succeeds -> resets to CLOSED
    cb.record_success()
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_probe_failure():
    cb = CircuitBreaker("test_cb_probe", failure_threshold=2, cooldown_seconds=0.1)
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitState.OPEN

    time.sleep(0.15)
    assert cb.can_execute() is True
    assert cb.state == CircuitState.HALF_OPEN

    # Probe fails -> trips immediately back to OPEN
    cb.record_failure()
    assert cb.state == CircuitState.OPEN


def test_rules_engine_leave_validations():
    # Valid
    rules_engine.validate_leave_request("2027-01-10", "2027-01-12", "Vacation", 2.0, 40.0)

    # Past date
    with pytest.raises(HTTPException) as exc1:
        rules_engine.validate_leave_request("2020-01-01", "2020-01-02", "Vacation", 1.0, 40.0)
    assert exc1.value.status_code == 422
    assert exc1.value.detail["code"] == "TEMPORAL_VIOLATION"

    # Start after End
    with pytest.raises(HTTPException) as exc2:
        rules_engine.validate_leave_request("2027-01-05", "2027-01-02", "Vacation", 1.0, 40.0)
    assert exc2.value.status_code == 422
    assert exc2.value.detail["code"] == "TEMPORAL_VIOLATION"

    # Insufficient Balance
    with pytest.raises(HTTPException) as exc3:
        rules_engine.validate_leave_request("2027-01-10", "2027-01-12", "Vacation", 10.0, 16.0) # 80h > 16h
    assert exc3.value.status_code == 422
    assert exc3.value.detail["code"] == "INSUFFICIENT_BALANCE"


def test_rules_engine_contact_validations():
    # Valid
    rules_engine.validate_contact_update("123 Main St, Suite 400", "+15551234567")

    # Address too short
    with pytest.raises(HTTPException):
        rules_engine.validate_contact_update("abc", "+15551234567")

    # Invalid phone format
    with pytest.raises(HTTPException):
        rules_engine.validate_contact_update("123 Main St", "invalid-phone")


def test_rules_engine_incident_validations():
    # Critical without keywords fails
    with pytest.raises(HTTPException):
        rules_engine.validate_incident_creation("Software", "Change font size", PriorityEnum.CRITICAL)

    # Critical with outage passes
    rules_engine.validate_incident_creation("Network", "Critical VPN outage affecting floor 3", PriorityEnum.CRITICAL)

    # Illegal lifecycle transition: New -> Closed
    with pytest.raises(HTTPException):
        rules_engine.validate_status_transition("New", "Closed")

    # Legal transition
    rules_engine.validate_status_transition("New", "In Progress")
    rules_engine.validate_status_transition("In Progress", "Resolved")


def test_firestore_idempotency_locking():
    emp_id = "EMP-TEST-LOCK"
    action = "submit_leave"
    params = {"days": 3}

    # 1. First acquisition succeeds
    acq1, key1, cached1 = firestore_store.acquire_lock(emp_id, action, params)
    assert acq1 is True
    assert cached1 is None

    # 2. Second immediate acquisition fails
    acq2, key2, cached2 = firestore_store.acquire_lock(emp_id, action, params)
    assert acq2 is False
    assert cached2 is None

    # 3. Complete lock
    firestore_store.release_or_complete_lock(key1, {"leaveId": "LV-1234"})

    # 4. Third acquisition returns completed cached result
    acq3, key3, cached3 = firestore_store.acquire_lock(emp_id, action, params)
    assert acq3 is False
    assert cached3 == {"leaveId": "LV-1234"}
