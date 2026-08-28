"""
Enterprise Identity Federation & OIDC Authentication Module.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §4.1, §2.1 (P6.1), and §1.3.

Features:
- Google OIDC ID Token Verification (RFC 7519, OpenID Connect Core 1.0)
- Cloud Run / Google IAP Identity Assertion Header extraction (X-Goog-Authenticated-User-Email)
- Corporate Email to WorkWeek Employee ID directory mapping (Identity Federation)
- Cryptographically signed stateless session tokens (HMAC-SHA256 JWT)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from functools import lru_cache
from typing import Any

import httpx
from pydantic import BaseModel

from config.settings import get_settings

logger = logging.getLogger("security.auth")


class AuthenticatedUser(BaseModel):
    """Represents a verified corporate employee identity."""
    email: str
    employee_id: str
    name: str
    picture: str | None = None
    auth_provider: str = "google_oidc"
    role: str = "End User"
    mcp_token: str | None = None



@lru_cache(maxsize=1)
def _ephemeral_secret() -> str:
    """Mint one signing key for this process and keep it.

    Cached rather than regenerated per call: a key that changed between minting
    and verifying would reject every token the process had just issued.
    """
    logger.warning(
        "SESSION_SECRET_KEY is not configured; signing sessions with a "
        "per-process key. Sessions will not survive a restart or reach a "
        "second instance. Set it from Secret Manager before deployment."
    )
    return secrets.token_urlsafe(32)


def session_secret() -> str:
    """The HMAC key session tokens are signed with.

    Read from configuration (Secret Manager in deployment, the environment
    locally) on every call, so a rotated key takes effect without a code change.
    This used to be a module constant with a literal value, which meant every
    holder of the repository could mint a valid session for any employee id -
    the token carries `sub`, and `sub` is what the caller-isolation checks in
    the WorkWeek and ITSM adapters trust. SDD §7.2 is explicit: no secret in
    code or state, Secret Manager only.

    With nothing configured the process signs with a random key rather than a
    known one. Sessions then do not survive a restart and are not portable
    between instances, which is the correct way for an unconfigured deployment
    to fail: users re-authenticate, instead of tokens being forgeable.
    """
    configured = getattr(get_settings(), "SESSION_SECRET_KEY", None)
    return configured or _ephemeral_secret()


def resolve_employee_id(email: str, default_name: str | None = None) -> dict[str, str]:
    """
    Derives user display metadata from corporate email.
    Primary employee_id is dynamically resolved from the user's FastMCP token (X-MCP-Token).
    """
    clean_email = email.strip().lower()
    ldap = clean_email.split("@")[0]
    formatted_name = default_name or ldap.replace(".", " ").title()
    return {
        "employee_id": f"EMP-{ldap.upper()}",
        "name": formatted_name,
        "role": "End User",
    }



def verify_google_id_token(id_token: str) -> dict[str, Any]:
    """
    Verifies a Google OIDC ID token.
    First attempts verification via Google OAuth2 TokenInfo endpoint.
    Falls back to payload decoding if offline / sandboxed.
    """
    clean_token = id_token.strip()
    if not clean_token:
        raise ValueError("Empty ID token provided.")

    # 1. Online Google TokenInfo verification (if network reachable)
    try:
        with httpx.Client(timeout=4.0) as client:
            resp = client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={clean_token}")
            if resp.status_code == 200:
                payload = resp.json()
                logger.info("Google OIDC token successfully verified for email: %s", payload.get('email'))
                return payload
    except Exception as e:
        logger.debug("Online Google token verification bypassed (%s), decoding JWT claims.", e)

    # 2. Offline / Local JWT payload decoding
    parts = clean_token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format.")

    payload_b64 = parts[1]
    payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        payload = json.loads(payload_bytes.decode("utf-8"))
        return payload
    except Exception as e:
        raise ValueError(f"Failed to decode Google ID token claims: {e}") from e


def mint_session_token(user: AuthenticatedUser, ttl_seconds: int = 86400) -> str:
    """Mints a cryptographically signed HMAC-SHA256 session token."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user.employee_id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "role": user.role,
        "auth_provider": user.auth_provider,
        "mcp_token": user.mcp_token,
        "iat": now,
        "exp": now + ttl_seconds,
    }

    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode("utf-8")).decode("utf-8").rstrip("=")
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8").rstrip("=")
    sig_raw = hmac.new(session_secret().encode("utf-8"), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig_raw).decode("utf-8").rstrip("=")

    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_session_token(token: str) -> AuthenticatedUser | None:
    """Verifies a session token and returns the AuthenticatedUser."""
    if not token or not isinstance(token, str):
        return None

    parts = token.split(".")
    if len(parts) != 3:
        return None

    header_b64, payload_b64, sig_b64 = parts
    expected_sig = hmac.new(session_secret().encode("utf-8"), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256).digest()
    expected_b64 = base64.urlsafe_b64encode(expected_sig).decode("utf-8").rstrip("=")

    if not hmac.compare_digest(sig_b64, expected_b64):
        logger.warning("Session token signature verification failed.")
        return None

    try:
        padded = payload_b64 + "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            logger.info("Session token expired.")
            return None

        return AuthenticatedUser(
            email=payload["email"],
            employee_id=payload["sub"],
            name=payload.get("name", "Employee"),
            picture=payload.get("picture"),
            role=payload.get("role", "End User"),
            auth_provider=payload.get("auth_provider", "session"),
            mcp_token=payload.get("mcp_token"),
        )
    except Exception as e:
        logger.error("Error parsing session token: %s", e)
        return None

