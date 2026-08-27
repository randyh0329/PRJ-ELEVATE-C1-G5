"""Tests for Google OIDC, Identity Federation, and Session Authentication Module."""
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.security.auth import (
    AuthenticatedUser,
    resolve_employee_id,
    mint_session_token,
    verify_session_token,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_resolve_employee_id_directory():
    """Verify known corporate emails resolve to correct WorkWeek Employee IDs."""
    romij_info = resolve_employee_id("romij@google.com")
    assert romij_info["employee_id"] == "EMP-509"
    assert "Romij" in romij_info["name"]

    sarah_info = resolve_employee_id("sarah.chen@elevate-corp.internal")
    assert sarah_info["employee_id"] == "EMP-44210"

    google_corp_info = resolve_employee_id("developer@google.com")
    assert google_corp_info["employee_id"] == "EMP-509"


def test_session_token_minting_and_verification():
    """Verify cryptographically signed session tokens mint and verify correctly."""
    user = AuthenticatedUser(
        email="romij@google.com",
        employee_id="EMP-509",
        name="Romij Employee",
        role="Solutions Acceleration Architect",
        auth_provider="google_oidc"
    )

    token = mint_session_token(user, ttl_seconds=3600)
    assert token is not None
    assert len(token.split(".")) == 3

    verified = verify_session_token(token)
    assert verified is not None
    assert verified.email == "romij@google.com"
    assert verified.employee_id == "EMP-509"
    assert verified.name == "Romij Employee"

    # Test tampering
    tampered = token[:-4] + "fake"
    assert verify_session_token(tampered) is None


def test_quick_login_and_auth_me_endpoint(client):
    """Verify /auth/quick-login returns a valid session token and /auth/me verifies it."""
    login_resp = client.post("/auth/quick-login", json={"email": "romij@google.com", "name": "Romij Employee"})
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert data["success"] is True
    assert "token" in data
    token = data["token"]
    assert data["user"]["employee_id"] == "EMP-509"

    # Verify /auth/me with Bearer token
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["email"] == "romij@google.com"
    assert me_data["user"]["employee_id"] == "EMP-509"


def test_chat_with_authenticated_session_token(client):
    """Verify /chat binds caller subject from session token without relying on client payload."""
    login_resp = client.post("/auth/quick-login", json={"email": "romij@google.com"})
    token = login_resp.json()["token"]

    # In payload, client specifies fake employee_id="EMP-9999", but session token is for romij (EMP-509)
    chat_resp = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"employee_id": "EMP-9999", "message": "내 연차 얼마나 남았어?"}
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert chat_data["intent"] == "UC_1_2_WORKWEEK_LEAVE"
    # Bound to EMP-509's real balance
    assert "Vacation:" in chat_data["response"]


def test_chat_with_cloud_run_iap_header(client):
    """Verify /chat automatically recognizes Google Cloud IAP header."""
    chat_resp = client.post(
        "/chat",
        headers={"X-Goog-Authenticated-User-Email": "accounts.google.com:romij@google.com"},
        json={"employee_id": "EMP-9999", "message": "내 연차 얼마나 남았어?"}
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert chat_data["intent"] == "UC_1_2_WORKWEEK_LEAVE"


def test_quick_login_with_custom_mcp_token(client):
    """Verify /auth/quick-login accepts and preserves custom MCP token."""
    from config.settings import get_settings
    valid_token = get_settings().SAAS_MCP_CREDENTIAL

    login_resp = client.post(
        "/auth/quick-login",
        json={"email": "teammate@google.com", "mcp_token": valid_token}
    )
    assert login_resp.status_code == 200
    data = login_resp.json()
    assert data["success"] is True
    assert data["user"]["mcp_token"] == valid_token

    token = data["token"]
    me_resp = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["mcp_token"] == valid_token


def test_quick_login_with_invalid_token_rejects(client):
    """Verify /auth/quick-login rejects invalid token with 401."""
    login_resp = client.post(
        "/auth/quick-login",
        json={"email": "teammate@google.com", "mcp_token": "invalid_fake_token"}
    )
    assert login_resp.status_code == 401
    assert "WorkWeek Authentication Failed" in login_resp.json()["detail"]


