import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from src.mocks.app import mock_app
from src.config import settings

from src.mocks.fidelity import fidelity_engine

client = TestClient(mock_app)


@pytest.fixture(autouse=True)
def reset_state_before_each():
    fidelity_engine.set_profile("unit")
    client.post(
        "/api/test/reset-state",
        headers={"X-Test-Authorization": settings.test_auth_secret}
    )



def test_healthz():
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "HEALTHY"


def test_workweek_profile():
    resp = client.get(
        "/api/v1/employees/me/profile",
        headers={"X-Subject-Assertion": "EMP-44210"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["employeeId"] == "EMP-44210"
    assert data["name"] == "Alex Morgan"
    assert data["email"] == "alex.morgan@company.corp"
    assert data["homeAddress"] == "742 Evergreen Terrace, Springfield"


def test_workweek_contact_update():
    resp = client.patch(
        "/api/v1/employees/me/contact",
        json={"homeAddress": "123 New Street, Metropolis", "phoneNumber": "+15559998877"},
        headers={"X-Subject-Assertion": "EMP-44210"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "homeAddress" in data["updated"]
    assert "phoneNumber" in data["updated"]
    assert data["previousAddress"] == "742 Evergreen Terrace, Springfield"

    # Verify updated
    p_resp = client.get(
        "/api/v1/employees/me/profile",
        headers={"X-Subject-Assertion": "EMP-44210"}
    )
    assert p_resp.json()["homeAddress"] == "123 New Street, Metropolis"


def test_workweek_balances():
    resp = client.get(
        "/api/v1/employees/me/balances",
        headers={"X-Subject-Assertion": "EMP-44210"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["vacation"]["remainingHours"] == 56.0
    assert data["sick"]["remainingHours"] == 32.0


def test_workweek_leave_submission_and_cancellation():
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    day_after = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

    # 1. Successful submission
    resp = client.post(
        "/api/v1/employees/me/leaves",
        json={
            "startDate": tomorrow,
            "endDate": day_after,
            "leaveType": "Vacation",
            "workDays": 2.0,
            "reason": "Family vacation"
        },
        headers={"X-Subject-Assertion": "EMP-44210"}
    )
    assert resp.status_code == 201
    leave_id = resp.json()["leaveId"]
    assert leave_id.startswith("LV-")

    # Verify balance reduced (56 - 16 = 40)
    bal_resp = client.get(
        "/api/v1/employees/me/balances",
        headers={"X-Subject-Assertion": "EMP-44210"}
    )
    assert bal_resp.json()["vacation"]["remainingHours"] == 40.0

    # 2. Cancel leave (Saga compensation)
    del_resp = client.delete(
        f"/api/v1/employees/me/leaves/{leave_id}",
        headers={"X-Subject-Assertion": "EMP-44210"}
    )
    assert del_resp.status_code == 200

    # Verify balance restored to 56
    bal_resp2 = client.get(
        "/api/v1/employees/me/balances",
        headers={"X-Subject-Assertion": "EMP-44210"}
    )
    assert bal_resp2.json()["vacation"]["remainingHours"] == 56.0


def test_workweek_leave_guardrails():
    # 1. Past date violation
    resp_past = client.post(
        "/api/v1/employees/me/leaves",
        json={
            "startDate": "2020-01-01",
            "endDate": "2020-01-02",
            "leaveType": "Vacation",
            "workDays": 1.0
        },
        headers={"X-Subject-Assertion": "EMP-44210"}
    )
    assert resp_past.status_code == 422
    assert "TEMPORAL_VIOLATION" in str(resp_past.json())

    # 2. Insufficient balance violation
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    later = (datetime.now() + timedelta(days=20)).strftime("%Y-%m-%d")
    resp_bal = client.post(
        "/api/v1/employees/me/leaves",
        json={
            "startDate": tomorrow,
            "endDate": later,
            "leaveType": "Vacation",
            "workDays": 15.0  # 15 * 8 = 120 hrs > 56 hrs
        },
        headers={"X-Subject-Assertion": "EMP-44210"}
    )
    assert resp_bal.status_code == 422
    assert "INSUFFICIENT_BALANCE" in str(resp_bal.json())


def test_itsm_incident_flow():
    # 1. Query existing ticket
    resp = client.get("/api/v1/incidents/INC123456")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticketId"] == "INC123456"
    assert data["state"] == "In Progress"
    assert len(data["comments"]) >= 1

    # 2. Create new incident
    create_resp = client.post(
        "/api/v1/incidents",
        json={
            "category": "Hardware",
            "shortDescription": "Keyboard spacebar sticky",
            "priority": "4 - Low",
            "description": "Ergonomic keyboard spacebar gets stuck intermittently"
        }
    )
    assert create_resp.status_code == 201
    ticket_id = create_resp.json()["ticketId"]

    # 3. Add comment
    c_resp = client.post(
        f"/api/v1/incidents/{ticket_id}/comments",
        json={"body": "User provided additional details."}
    )
    assert c_resp.status_code == 201

    # 4. Status update
    s_resp = client.patch(
        f"/api/v1/incidents/{ticket_id}/status",
        json={"state": "In Progress", "resolutionNotes": "Assigned to desk"}
    )
    assert s_resp.status_code == 200


def test_itsm_guardrails():
    # 1. Critical priority requires outage/security justification
    resp = client.post(
        "/api/v1/incidents",
        json={
            "category": "Software",
            "shortDescription": "Need dark mode icon changed",
            "priority": "1 - Critical"
        }
    )
    assert resp.status_code == 422
    assert "Priority verification failed" in str(resp.json())

    # 2. Illegal lifecycle: New directly to Closed
    create_resp = client.post(
        "/api/v1/incidents",
        json={
            "category": "Software",
            "shortDescription": "Minor UI glitch in portal",
            "priority": "3 - Moderate"
        }
    )
    t_id = create_resp.json()["ticketId"]
    close_resp = client.patch(
        f"/api/v1/incidents/{t_id}/status",
        json={"state": "Closed"}
    )
    assert close_resp.status_code == 422
    assert "Illegal lifecycle transition" in str(close_resp.json())


def test_idempotency_and_fault_injection():
    # 1. Idempotency test
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    headers = {
        "X-Subject-Assertion": "EMP-44210",
        "X-Idempotency-Key": "test-key-uuid-1234"
    }
    payload = {
        "startDate": tomorrow,
        "endDate": tomorrow,
        "leaveType": "Vacation",
        "workDays": 1.0
    }
    resp1 = client.post("/api/v1/employees/me/leaves", json=payload, headers=headers)
    assert resp1.status_code == 201

    # Replay same key
    resp2 = client.post("/api/v1/employees/me/leaves", json=payload, headers=headers)
    assert resp2.status_code == 409

    # 2. Deterministic Fault Injection: 429
    resp_429 = client.get(
        "/api/v1/employees/me/profile",
        headers={"X-Test-Fault": "429"}
    )
    assert resp_429.status_code == 429
    assert resp_429.headers.get("Retry-After") == "30"


def test_reset_state_endpoint():
    # Mutate state: change address
    client.patch(
        "/api/v1/employees/me/contact",
        json={"homeAddress": "999 Altered Lane"},
        headers={"X-Subject-Assertion": "EMP-44210"}
    )

    # Call reset
    reset_resp = client.post(
        "/api/test/reset-state",
        headers={"X-Test-Authorization": settings.test_auth_secret}
    )
    assert reset_resp.status_code == 200
    data = reset_resp.json()
    assert data["status"] == "RESET_COMPLETE"
    assert data["elapsed_ms"] < 200.0

    # Verify address restored
    prof = client.get(
        "/api/v1/employees/me/profile",
        headers={"X-Subject-Assertion": "EMP-44210"}
    ).json()
    assert prof["homeAddress"] == "742 Evergreen Terrace, Springfield"
