"""The API surface around identity: login, session, and caller binding (§4.1).

`tests/test_api_server.py` covers the happy path of `/chat` end to end. This
module covers the part that decides *whose* records that request will reach.

Three sources can supply a caller id, and `/chat` consults them in a fixed
order: a verified session token, then the Cloud Run IAP header, then the
client-supplied header or body. The order is the whole security property. If a
body field could displace a verified token, any authenticated employee could
read another's leave balance, and every FR-1.5 check downstream would pass
because it would be comparing the forged id against itself. The tests here
assert the precedence directly rather than through a full agent turn.

The agent itself is stubbed throughout: what is under test is the routing of
identity into it, not what it answers.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src import main
from src.core.agent import AgentResponse
from src.main import app
from src.security.auth import AuthenticatedUser, mint_session_token


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def offline_mcp(monkeypatch):
    """No test here may probe the live FastMCP endpoint."""
    probe = SimpleNamespace(
        get_current_employee_id=lambda token=None: (_ for _ in ()).throw(
            RuntimeError("network disabled in tests")
        )
    )
    monkeypatch.setattr(main, "saas_fast_mcp_client", probe)
    return probe


class SpyAgent:
    """Captures the caller id the endpoint resolved, and answers trivially."""

    def __init__(self):
        self.calls: list[dict] = []

    def process_message(self, user_prompt, caller_employee_id, session_id=None):
        self.calls.append(
            {
                "user_prompt": user_prompt,
                "caller_employee_id": caller_employee_id,
                "session_id": session_id,
            }
        )
        return AgentResponse(
            response_text="ok",
            intent="UC_1_1_POLICY_QA",
            citations=["handbook.md#leave"],
            action_performed="ANSWER",
            transaction_reference="TX-1",
            processing_metadata={"latency_ms": 1},
        )


@pytest.fixture
def agent(monkeypatch) -> SpyAgent:
    spy = SpyAgent()
    monkeypatch.setattr(main, "hr_enterprise_agent", spy)
    return spy


@pytest.fixture
def signing_key(monkeypatch):
    monkeypatch.setattr(main.settings, "SESSION_SECRET_KEY", "api-test-key", raising=False)


def _bearer(employee_id="EMP-509", **overrides) -> dict[str, str]:
    fields = {
        "email": "jane.doe@altostrat.com",
        "employee_id": employee_id,
        "name": "Jane Doe",
    }
    fields.update(overrides)
    return {"Authorization": f"Bearer {mint_session_token(AuthenticatedUser(**fields))}"}


# --- the served UI ------------------------------------------------------------


def test_the_root_path_serves_the_chat_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<!DOCTYPE html>" in response.text


# --- /auth/google -------------------------------------------------------------


def test_a_verified_google_token_mints_a_session(client, monkeypatch, signing_key):
    monkeypatch.setattr(
        main,
        "verify_google_id_token",
        lambda credential: {
            "email": "jane.doe@altostrat.com",
            "name": "Jane Doe",
            "picture": "https://cdn/x.png",
        },
    )

    body = client.post("/auth/google", json={"credential": "google-id-token"}).json()

    assert body["success"] is True
    assert body["user"]["employee_id"] == "EMP-JANE.DOE"
    assert body["user"]["picture"] == "https://cdn/x.png"
    assert main.verify_session_token(body["token"]).email == "jane.doe@altostrat.com"


def test_a_google_token_without_a_name_falls_back_to_the_ldap_part(
    client, monkeypatch, signing_key
):
    monkeypatch.setattr(
        main, "verify_google_id_token", lambda credential: {"email": "jdoe@altostrat.com"}
    )

    body = client.post("/auth/google", json={"credential": "x"}).json()

    assert body["user"]["name"] == "Jdoe"


def test_a_google_token_carrying_no_email_is_rejected(client, monkeypatch):
    """Without an email there is no subject to bind, so no session may be issued."""
    monkeypatch.setattr(main, "verify_google_id_token", lambda credential: {"sub": "1234"})

    response = client.post("/auth/google", json={"credential": "x"})

    assert response.status_code == 401


def test_a_google_token_that_fails_verification_is_rejected(client, monkeypatch):
    def _reject(credential):
        raise ValueError("Invalid JWT format.")

    monkeypatch.setattr(main, "verify_google_id_token", _reject)

    response = client.post("/auth/google", json={"credential": "not-a-jwt"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Google authentication failed."


# --- /auth/quick-login --------------------------------------------------------


def test_the_employee_id_is_discovered_from_the_supplied_mcp_token(
    client, monkeypatch, offline_mcp, signing_key
):
    """The id comes from the token's own account, never from the posted email."""
    monkeypatch.setattr(offline_mcp, "get_current_employee_id", lambda token=None: "EMP-509")

    body = client.post(
        "/auth/quick-login",
        json={"email": "someone.else@altostrat.com", "mcp_token": "mcp-live-token"},
    ).json()

    assert body["user"]["employee_id"] == "EMP-509"
    assert body["user"]["mcp_token"] == "mcp-live-token"
    assert body["user"]["auth_provider"] == "corporate_federation"


def test_a_test_run_without_a_token_borrows_the_configured_demo_credential(
    client, monkeypatch, offline_mcp, signing_key
):
    seen = {}

    def _probe(token=None):
        seen["token"] = token
        return "EMP-509"

    monkeypatch.setattr(offline_mcp, "get_current_employee_id", _probe)

    body = client.post("/auth/quick-login", json={"email": "jane@altostrat.com"}).json()

    assert seen["token"] == main.settings.SAAS_MCP_CREDENTIAL
    assert body["user"]["employee_id"] == "EMP-509"


def test_outside_a_test_run_a_login_without_a_token_is_refused(client, monkeypatch):
    """In deployment there is no fallback credential to borrow."""
    monkeypatch.delitem(sys.modules, "pytest")

    response = client.post("/auth/quick-login", json={"email": "jane@altostrat.com"})

    assert response.status_code == 400
    assert "FastMCP Token" in response.json()["detail"]


def test_an_unreachable_probe_under_test_still_yields_the_demo_subject(
    client, signing_key
):
    """The suite runs without egress; the autouse fixture makes the probe raise."""
    body = client.post(
        "/auth/quick-login", json={"email": "jane@altostrat.com", "mcp_token": "test_token"}
    ).json()

    assert body["user"]["employee_id"] == "EMP-509"


def test_a_token_the_saas_rejects_produces_a_readable_error(client, monkeypatch, offline_mcp):
    def _unauthorised(token=None):
        raise RuntimeError("HTTP 401 Unauthorized")

    monkeypatch.setattr(offline_mcp, "get_current_employee_id", _unauthorised)

    response = client.post(
        "/auth/quick-login", json={"email": "jane@altostrat.com", "mcp_token": "mcp-revoked"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "WorkWeek Authentication Failed: Invalid, expired, or revoked FastMCP token."
    )


def test_a_probe_failure_that_is_not_an_auth_error_is_reported_verbatim(
    client, monkeypatch, offline_mcp
):
    def _down(token=None):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(offline_mcp, "get_current_employee_id", _down)

    response = client.post(
        "/auth/quick-login", json={"email": "jane@altostrat.com", "mcp_token": "mcp-live"}
    )

    assert response.status_code == 401
    assert "connection refused" in response.json()["detail"]


def test_a_display_name_is_derived_from_the_email_when_none_is_posted(
    client, monkeypatch, offline_mcp, signing_key
):
    monkeypatch.setattr(offline_mcp, "get_current_employee_id", lambda token=None: "EMP-509")

    body = client.post(
        "/auth/quick-login", json={"email": "jane.doe@altostrat.com", "mcp_token": "t"}
    ).json()

    assert body["user"]["name"] == "Jane Doe"


# --- /auth/me -----------------------------------------------------------------


def test_a_valid_session_token_identifies_the_user(client, signing_key):
    body = client.get("/auth/me", headers=_bearer()).json()

    assert body["authenticated"] is True
    assert body["user"]["employee_id"] == "EMP-509"


def test_an_iap_header_identifies_the_user_when_no_session_is_presented(client):
    """Cloud Run puts `accounts.google.com:` in front of the address."""
    body = client.get(
        "/auth/me",
        headers={"X-Goog-Authenticated-User-Email": "accounts.google.com:jane.doe@altostrat.com"},
    ).json()

    assert body["user"]["employee_id"] == "EMP-JANE.DOE"
    assert body["user"]["auth_provider"] == "cloud_run_iap"


def test_a_tampered_session_falls_through_to_the_iap_header(client, signing_key):
    body = client.get(
        "/auth/me",
        headers={
            "Authorization": "Bearer forged.token.value",
            "X-Goog-Authenticated-User-Email": "jane.doe@altostrat.com",
        },
    ).json()

    assert body["user"]["auth_provider"] == "cloud_run_iap"


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Basic abc"}, {"Authorization": "Bearer forged.a.b"}]
)
def test_anything_short_of_a_verified_identity_is_anonymous(client, headers):
    body = client.get("/auth/me", headers=headers).json()

    assert body == {"authenticated": False, "user": None}


# --- caller binding on /chat --------------------------------------------------


def test_a_session_token_outranks_the_employee_id_in_the_body(client, agent, signing_key):
    """The escalation this prevents: posting someone else's id alongside a token."""
    client.post(
        "/chat",
        json={"employee_id": "EMP-1001", "message": "my balance"},
        headers=_bearer("EMP-509"),
    )

    assert agent.calls[0]["caller_employee_id"] == "EMP-509"


def test_a_session_token_outranks_the_iap_header(client, agent, signing_key):
    client.post(
        "/chat",
        json={"message": "my balance"},
        headers={
            **_bearer("EMP-509"),
            "X-Goog-Authenticated-User-Email": "someone.else@altostrat.com",
        },
    )

    assert agent.calls[0]["caller_employee_id"] == "EMP-509"


def test_the_iap_header_outranks_the_caller_header(client, agent):
    client.post(
        "/chat",
        json={"message": "my balance"},
        headers={
            "X-Goog-Authenticated-User-Email": "accounts.google.com:jane.doe@altostrat.com",
            "X-Caller-Employee-Id": "EMP-9999",
        },
    )

    assert agent.calls[0]["caller_employee_id"] == "EMP-JANE.DOE"


def test_the_caller_header_outranks_the_body(client, agent):
    client.post(
        "/chat",
        json={"employee_id": "EMP-1001", "message": "my balance"},
        headers={"X-Caller-Employee-Id": "EMP-509"},
    )

    assert agent.calls[0]["caller_employee_id"] == "EMP-509"


def test_the_body_supplies_the_caller_when_nothing_else_does(client, agent):
    client.post("/chat", json={"employee_id": "EMP-1001", "message": "my balance"})

    assert agent.calls[0]["caller_employee_id"] == "EMP-1001"


def test_an_unverifiable_bearer_token_does_not_bind_a_caller(client, agent, signing_key):
    client.post(
        "/chat",
        json={"employee_id": "EMP-1001", "message": "my balance"},
        headers={"Authorization": "Bearer forged.a.b"},
    )

    assert agent.calls[0]["caller_employee_id"] == "EMP-1001"


def test_the_session_carries_the_mcp_token_into_the_request_context(
    client, agent, signing_key, monkeypatch
):
    """The per-user SaaS credential is what makes the live path caller-specific."""
    seen = []
    monkeypatch.setattr(main, "current_mcp_token", SimpleNamespace(set=seen.append))

    client.post(
        "/chat",
        json={"message": "my balance"},
        headers=_bearer(mcp_token="mcp-session-token"),
    )

    assert seen == ["mcp-session-token"]


def test_a_header_supplied_mcp_token_is_used_when_the_session_carries_none(
    client, agent, monkeypatch
):
    seen = []
    monkeypatch.setattr(main, "current_mcp_token", SimpleNamespace(set=seen.append))

    client.post(
        "/chat", json={"message": "my balance"}, headers={"X-MCP-Token": "mcp-header-token"}
    )

    assert seen == ["mcp-header-token"]


def test_no_token_anywhere_leaves_the_context_untouched(client, agent, monkeypatch):
    seen = []
    monkeypatch.setattr(main, "current_mcp_token", SimpleNamespace(set=seen.append))

    client.post("/chat", json={"message": "my balance"})

    assert seen == []


def test_the_session_id_is_forwarded_so_the_turn_joins_its_conversation(client, agent):
    client.post("/chat", json={"message": "and the sick balance?", "session_id": "sess-1"})

    assert agent.calls[0]["session_id"] == "sess-1"


def test_the_agent_response_is_mapped_field_for_field(client, agent):
    body = client.post("/chat", json={"message": "policy?"}).json()

    assert body == {
        "response": "ok",
        "intent": "UC_1_1_POLICY_QA",
        "citations": ["handbook.md#leave"],
        "action_performed": "ANSWER",
        "transaction_reference": "TX-1",
        "processing_metadata": {"latency_ms": 1},
    }


def test_an_agent_crash_becomes_an_apology_rather_than_a_five_hundred(
    client, monkeypatch, caplog
):
    """A stack trace reaching the browser would leak internals; NFR-3 wants a turn."""
    def _explode(**kwargs):
        raise RuntimeError("vertex quota exhausted")

    monkeypatch.setattr(main.hr_enterprise_agent, "process_message", _explode)

    response = client.post("/chat", json={"message": "my balance"})

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "SYSTEM_ERROR"
    assert body["action_performed"] == "ERROR"
    assert body["processing_metadata"]["error"] == "vertex quota exhausted"
    assert "Something went wrong" in body["response"]


# --- the debugging read-throughs ----------------------------------------------


def test_the_balances_endpoint_returns_a_seeded_employee(client):
    assert client.get("/workweek/balances/EMP-1001").status_code == 200


def test_the_balances_endpoint_is_a_404_for_an_unknown_employee(client):
    response = client.get("/workweek/balances/EMP-NONEXISTENT")

    assert response.status_code == 404
    assert response.json()["detail"] == "Balances not found"


# --- the interactive console --------------------------------------------------


@pytest.fixture
def console(monkeypatch, capsys):
    """Drive `run_interactive_cli` from a scripted list of typed lines."""
    spy = SpyAgent()
    monkeypatch.setattr(main, "hr_enterprise_agent", spy)
    monkeypatch.setattr(
        "src.integrations.mcp.client.saas_fast_mcp_client.get_current_employee_id",
        lambda token=None: "EMP-509",
    )

    def _run(lines, **kwargs):
        typed = iter(lines)
        monkeypatch.setattr("builtins.input", lambda prompt="": next(typed))
        main.run_interactive_cli(**kwargs)
        return capsys.readouterr().out, spy

    return _run


def test_the_console_greets_with_the_live_session_subject(console):
    out, _ = console(["exit"])

    assert "Logged in user: EMP-509" in out
    assert "Goodbye!" in out


def test_an_explicit_employee_id_overrides_the_live_session(console):
    out, _ = console(["quit"], default_employee_id="EMP-1001")

    assert "Logged in user: EMP-1001" in out


def test_a_typed_question_is_answered_with_its_citations(console):
    out, spy = console(["What is the leave policy?", "exit"])

    assert spy.calls[0]["caller_employee_id"] == "EMP-509"
    assert "Intent: UC_1_1_POLICY_QA" in out
    assert "Citations: handbook.md#leave" in out


def test_a_blank_line_is_ignored_rather_than_sent_to_the_agent(console):
    _, spy = console(["", "   ", "exit"])

    assert spy.calls == []


def test_switching_changes_the_subject_of_later_turns(console):
    out, spy = console(["switch emp-1001", "my balance", "exit"])

    assert "Switched active caller to: EMP-1001" in out
    assert spy.calls[0]["caller_employee_id"] == "EMP-1001"


def test_reset_reloads_both_mock_backends(console, monkeypatch):
    reset = []
    monkeypatch.setattr(
        main.workweek_mock_service, "init_mock_data", lambda: reset.append("workweek")
    )
    monkeypatch.setattr(
        main.service_immediately_mock_service, "init_mock_data", lambda: reset.append("itsm")
    )

    out, _ = console(["reset", "exit"])

    assert reset == ["workweek", "itsm"]
    assert "Mock databases reset" in out


def test_a_control_c_ends_the_session_without_a_traceback(monkeypatch, capsys):
    spy = SpyAgent()
    monkeypatch.setattr(main, "hr_enterprise_agent", spy)
    monkeypatch.setattr(
        "src.integrations.mcp.client.saas_fast_mcp_client.get_current_employee_id",
        lambda token=None: "EMP-509",
    )

    def _interrupt(prompt=""):
        raise KeyboardInterrupt

    monkeypatch.setattr("builtins.input", _interrupt)

    main.run_interactive_cli()

    assert "Session ended." in capsys.readouterr().out


def test_a_response_without_citations_prints_no_citation_line(console, monkeypatch):
    monkeypatch.setattr(
        main.hr_enterprise_agent,
        "process_message",
        lambda **kw: AgentResponse(response_text="ok", intent="OUT_OF_DOMAIN"),
    )

    out, _ = console(["who won the game?", "exit"])

    assert "Citations:" not in out
