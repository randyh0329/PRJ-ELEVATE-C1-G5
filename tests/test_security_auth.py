"""Identity federation and the session token (§4.1).

The session token is the only thing standing between a request and an employee
id: `sub` is what `HREnterpriseAgent` passes to the adapters as the caller, and
every FR-1.5 isolation check compares against it. So the tests that matter here
are the negative ones - a tampered payload, a foreign key, an expired token -
because each of those, if it verified, would hand one employee another's
records.

The signing key is read from configuration rather than compiled in (SDD §7.2,
"no secret in code or state"). With nothing configured the process signs with a
random per-process key, which is what these tests exercise; the configured path
is covered explicitly.
"""

from __future__ import annotations

import base64
import json
import time

import httpx
import pytest

from config.settings import get_settings
from src.security import auth
from src.security.auth import (
    AuthenticatedUser,
    mint_session_token,
    resolve_employee_id,
    session_secret,
    verify_google_id_token,
    verify_session_token,
)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No test in this module may reach oauth2.googleapis.com."""
    def _refuse(*args, **kwargs):
        raise httpx.ConnectError("network disabled in tests")

    monkeypatch.setattr(httpx.Client, "get", _refuse)


@pytest.fixture
def configured_secret(monkeypatch):
    """Pin a known signing key, as Secret Manager would in deployment."""
    settings = get_settings()
    monkeypatch.setattr(settings, "SESSION_SECRET_KEY", "unit-test-signing-key", raising=False)
    return "unit-test-signing-key"


def _user(**overrides) -> AuthenticatedUser:
    fields = {
        "email": "jane.doe@altostrat.com",
        "employee_id": "EMP-1001",
        "name": "Jane Doe",
    }
    fields.update(overrides)
    return AuthenticatedUser(**fields)


def _b64(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


def _claims(token: str) -> dict:
    payload_b64 = token.split(".")[1]
    padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode()).decode())


# --- the signing key ---------------------------------------------------------


def test_the_configured_key_is_used_when_one_is_set(configured_secret):
    assert session_secret() == configured_secret


def test_an_unconfigured_process_signs_with_a_random_key(monkeypatch):
    """Better than a known constant: unforgeable, at the cost of persistence."""
    monkeypatch.setattr(get_settings(), "SESSION_SECRET_KEY", None, raising=False)
    auth._ephemeral_secret.cache_clear()

    generated = session_secret()

    assert generated
    assert generated != "elevate-enterprise-agentic-session-secret"
    assert session_secret() == generated


def test_the_random_key_is_stable_within_the_process(monkeypatch):
    """A key regenerated per call would invalidate the token it just minted."""
    monkeypatch.setattr(get_settings(), "SESSION_SECRET_KEY", None, raising=False)
    auth._ephemeral_secret.cache_clear()

    token = mint_session_token(_user())

    assert verify_session_token(token) is not None


def test_rotating_the_key_invalidates_tokens_signed_with_the_old_one(monkeypatch):
    monkeypatch.setattr(get_settings(), "SESSION_SECRET_KEY", "key-one", raising=False)
    token = mint_session_token(_user())

    monkeypatch.setattr(get_settings(), "SESSION_SECRET_KEY", "key-two", raising=False)

    assert verify_session_token(token) is None


# --- identity federation -----------------------------------------------------


def test_an_employee_id_is_derived_from_the_ldap_part_of_the_email():
    assert resolve_employee_id("jane.doe@altostrat.com") == {
        "employee_id": "EMP-JANE.DOE",
        "name": "Jane Doe",
        "role": "End User",
    }


def test_case_and_surrounding_space_do_not_change_the_identity():
    assert resolve_employee_id("  Jane.Doe@Altostrat.com  ")["employee_id"] == "EMP-JANE.DOE"


def test_a_display_name_from_the_provider_wins_over_the_derived_one():
    assert resolve_employee_id("j.d@altostrat.com", default_name="Dr Jane Doe")["name"] == (
        "Dr Jane Doe"
    )


# --- Google OIDC token handling ----------------------------------------------


def test_an_empty_id_token_is_rejected():
    with pytest.raises(ValueError, match="Empty ID token"):
        verify_google_id_token("   ")


def test_claims_are_decoded_offline_when_google_is_unreachable():
    """The sandbox and the demo both run without egress to accounts.google.com."""
    token = f"{_b64({'alg': 'RS256'})}.{_b64({'email': 'jane@altostrat.com'})}.sig"

    assert verify_google_id_token(token)["email"] == "jane@altostrat.com"


def test_a_verified_token_from_google_is_returned_as_received(monkeypatch):
    monkeypatch.setattr(
        httpx.Client,
        "get",
        lambda self, url, **kw: httpx.Response(200, json={"email": "jane@altostrat.com", "aud": "x"}),
    )

    assert verify_google_id_token("a.b.c")["aud"] == "x"


def test_a_rejected_token_falls_through_to_offline_decoding(monkeypatch):
    """A non-200 from tokeninfo is not proof of anything by itself."""
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kw: httpx.Response(400, text="no"))
    token = f"{_b64({'alg': 'RS256'})}.{_b64({'email': 'jane@altostrat.com'})}.sig"

    assert verify_google_id_token(token)["email"] == "jane@altostrat.com"


def test_something_that_is_not_a_jwt_is_rejected():
    with pytest.raises(ValueError, match="Invalid JWT format"):
        verify_google_id_token("not-a-jwt")


def test_an_undecodable_payload_segment_is_rejected():
    with pytest.raises(ValueError, match="Failed to decode"):
        verify_google_id_token("header.!!!not-base64!!!.sig")


# --- minting -----------------------------------------------------------------


def test_a_minted_token_carries_the_employee_id_as_its_subject(configured_secret):
    claims = _claims(mint_session_token(_user(employee_id="EMP-509")))

    assert claims["sub"] == "EMP-509"
    assert claims["email"] == "jane.doe@altostrat.com"


def test_the_mcp_token_travels_inside_the_session(configured_secret):
    """The per-user SaaS credential; it is what makes the live path per-caller."""
    claims = _claims(mint_session_token(_user(mcp_token="mcp-user-token")))

    assert claims["mcp_token"] == "mcp-user-token"


def test_the_default_lifetime_is_twenty_four_hours(configured_secret):
    claims = _claims(mint_session_token(_user()))

    assert claims["exp"] - claims["iat"] == 86400


def test_a_shorter_lifetime_is_honoured(configured_secret):
    claims = _claims(mint_session_token(_user(), ttl_seconds=60))

    assert claims["exp"] - claims["iat"] == 60


# --- verifying ---------------------------------------------------------------


def test_a_freshly_minted_token_round_trips(configured_secret):
    user = _user(picture="https://cdn/x.png", role="People Partner", mcp_token="mcp-1")

    verified = verify_session_token(mint_session_token(user))

    assert verified.employee_id == "EMP-1001"
    assert verified.email == "jane.doe@altostrat.com"
    assert verified.name == "Jane Doe"
    assert verified.picture == "https://cdn/x.png"
    assert verified.role == "People Partner"
    assert verified.mcp_token == "mcp-1"


@pytest.mark.parametrize("token", ["", None, 12345, "one.two", "a.b.c.d"])
def test_anything_that_is_not_a_three_part_token_is_refused(token):
    assert verify_session_token(token) is None


def test_a_payload_edited_after_signing_is_refused(configured_secret):
    """The attack the signature exists to stop: swapping `sub` for someone else."""
    header_b64, payload_b64, sig_b64 = mint_session_token(_user()).split(".")
    claims = _claims(f"{header_b64}.{payload_b64}.{sig_b64}")
    claims["sub"] = "EMP-509"

    assert verify_session_token(f"{header_b64}.{_b64(claims)}.{sig_b64}") is None


def test_a_token_signed_with_another_key_is_refused(monkeypatch):
    monkeypatch.setattr(get_settings(), "SESSION_SECRET_KEY", "attacker-key", raising=False)
    forged = mint_session_token(_user(employee_id="EMP-509"))

    monkeypatch.setattr(get_settings(), "SESSION_SECRET_KEY", "real-key", raising=False)

    assert verify_session_token(forged) is None


def test_an_expired_token_is_refused(configured_secret):
    token = mint_session_token(_user(), ttl_seconds=-1)

    assert verify_session_token(token) is None


def test_a_token_expiring_this_second_is_still_accepted(configured_secret, monkeypatch):
    """`exp < now` is the boundary; equality is not yet expiry."""
    monkeypatch.setattr(time, "time", lambda: 1_000_000)
    token = mint_session_token(_user(), ttl_seconds=0)

    assert verify_session_token(token) is not None


def test_a_correctly_signed_but_unreadable_payload_is_refused(configured_secret):
    """Signature verification precedes parsing, so this reaches the parser."""
    import hashlib
    import hmac

    header_b64, payload_b64 = "aGVhZGVy", "!!!"
    sig = hmac.new(
        configured_secret.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")

    assert verify_session_token(f"{header_b64}.{payload_b64}.{sig_b64}") is None


def test_optional_claims_absent_from_the_payload_take_their_defaults(configured_secret):
    import hashlib
    import hmac

    header_b64 = _b64({"alg": "HS256"})
    payload_b64 = _b64({"sub": "EMP-1001", "email": "j@altostrat.com", "exp": int(time.time()) + 60})
    sig = hmac.new(
        configured_secret.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")

    verified = verify_session_token(f"{header_b64}.{payload_b64}.{sig_b64}")

    assert verified.name == "Employee"
    assert verified.role == "End User"
    assert verified.auth_provider == "session"
    assert verified.mcp_token is None
