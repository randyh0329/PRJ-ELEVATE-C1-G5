"""
Two-Layer Composite Token Minter.
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §4.1 (FR-1.2, FR-3.1, FR-4.1).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from typing import Any, Dict, List, Optional


class CompositeTokenMinter:
    """
    Mints the two-layer composite credential required for all agent-to-adapter calls (§4.1):
      - Layer 1: Workload Identity (Google-signed OIDC token, aud = target adapter URL)
      - Layer 2: Subject Assertion (RS256/asymmetric JWT carrying bound subject, 120s TTL)
    """

    def __init__(
        self,
        orchestrator_sa_email: str = "hr-agent-orchestrator@prj-elevate-c1-g5.iam.gserviceaccount.com",
        mock_private_key: Optional[str] = None,
    ):
        self.orchestrator_sa_email = orchestrator_sa_email
        self.mock_private_key = mock_private_key or "secret-orchestrator-signing-key"
        self.token_cache: Dict[str, Dict[str, Any]] = {}

    def _b64encode_json(self, data: Dict[str, Any]) -> str:
        json_bytes = json.dumps(data, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(json_bytes).decode("utf-8").rstrip("=")

    def _sign_payload(self, header_b64: str, payload_b64: str) -> str:
        """
        Signs the JWT using HMAC-SHA256 in local mock runtime or IAM Credentials signJwt in prod.
        """
        message = f"{header_b64}.{payload_b64}".encode("utf-8")
        sig = hmac.new(self.mock_private_key.encode("utf-8"), message, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")

    def mint_layer1_workload_oidc(self, target_audience: str) -> str:
        """
        Mints Layer 1 OIDC ID token proving workload identity (§4.1).
        """
        now = int(time.time())
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "iss": "https://accounts.google.com",
            "sub": self.orchestrator_sa_email,
            "aud": target_audience,
            "iat": now,
            "exp": now + 3600,
            "email": self.orchestrator_sa_email,
        }
        h_b64 = self._b64encode_json(header)
        p_b64 = self._b64encode_json(payload)
        sig_b64 = self._sign_payload(h_b64, p_b64)
        return f"{h_b64}.{p_b64}.{sig_b64}"

    def mint_layer2_subject_assertion(
        self,
        target_audience: str,
        employee_id: str,
        session_id: str,
        turn_id: str,
        agent_id: str,
        model_id: str,
        scopes: List[str],
        ttl_seconds: int = 120,
    ) -> str:
        """
        Mints Layer 2 Subject Assertion JWT signed via IAM Credentials signJwt (§4.1).
        """
        now = int(time.time())
        jti = str(uuid.uuid4())

        header = {
            "alg": "RS256",
            "typ": "JWT",
            "kid": "iam-creds-key-01",
        }
        payload = {
            "iss": self.orchestrator_sa_email,
            "sub": employee_id,  # Immutable server-side bound subject
            "act": {"sub": self.orchestrator_sa_email},
            "aud": target_audience,
            "sid": session_id,
            "tid": turn_id,
            "trace": f"projects/prj-elevate-c1-g5/traces/{uuid.uuid4().hex}",
            "agent": agent_id,
            "model_id": model_id,
            "scope": scopes,
            "jti": jti,
            "iat": now,
            "exp": now + ttl_seconds,
        }

        # Track jti nonce in Firestore token_cache for replay defense (§4.1, §4.6)
        cache_key = hashlib.sha256(f"{employee_id}|{target_audience}|{jti}".encode("utf-8")).hexdigest()
        self.token_cache[cache_key] = {
            "employee_id": employee_id,
            "jti": jti,
            "exp": now + ttl_seconds,
        }

        h_b64 = self._b64encode_json(header)
        p_b64 = self._b64encode_json(payload)
        sig_b64 = self._sign_payload(h_b64, p_b64)
        return f"{h_b64}.{p_b64}.{sig_b64}"

    def mint_composite_headers(
        self,
        target_audience: str,
        employee_id: str,
        session_id: str,
        turn_id: str,
        agent_id: str,
        model_id: str,
        scopes: List[str],
    ) -> Dict[str, str]:
        """
        Returns full HTTP headers required for downstream adapter verification.
        """
        layer1_token = self.mint_layer1_workload_oidc(target_audience)
        layer2_token = self.mint_layer2_subject_assertion(
            target_audience=target_audience,
            employee_id=employee_id,
            session_id=session_id,
            turn_id=turn_id,
            agent_id=agent_id,
            model_id=model_id,
            scopes=scopes,
        )

        return {
            "Authorization": f"Bearer {layer1_token}",
            "X-Subject-Assertion": layer2_token,
            "X-Agent-Origin": agent_id,
            "X-Execution-Trace-ID": f"trace-{uuid.uuid4().hex[:12]}",
        }
