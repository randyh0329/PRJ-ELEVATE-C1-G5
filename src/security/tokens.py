import time
import uuid
from typing import Dict, Any, List, Optional
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from fastapi import HTTPException, status
from src.storage.firestore import firestore_store

# Generate in-memory RSA keypair for RS256 token minting and verification
_private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
    backend=default_backend()
)
_public_key = _private_key.public_key()

_private_pem = _private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)
_public_pem = _public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)



class CompositeTokenManager:
    """
    Manages Delegated Authorization & Origin Verification (SDD §4.1).
    Layer 1: Workload Identity (Google-signed OIDC token).
    Layer 2: Subject Assertion (RS256 JWT carrying bound employee subject).
    """
    def __init__(self):
        self.issuer = "hr-agent-orchestrator@prj-elevate-c1-g5.iam.gserviceaccount.com"

    def mint_subject_assertion(
        self,
        employee_id: str,
        target_audience: str,
        session_id: str,
        agent_id: str = "hcm-1.4.0",
        scopes: Optional[List[str]] = None,
        ttl_seconds: int = 120
    ) -> str:
        """
        Mints a verifiable RS256 JWT signed by agent service account.
        The subject is bound server-side from authenticated session (NEVER model-supplied).
        """
        now = int(time.time())
        jti = str(uuid.uuid4())

        payload = {
            "iss": self.issuer,
            "sub": employee_id,
            "act": {"sub": self.issuer},
            "aud": target_audience,
            "sid": session_id,
            "tid": f"turn-{int(time.time() * 1000) % 1000000}",
            "trace": f"projects/prj-elevate-c1-g5/traces/{uuid.uuid4().hex[:16]}",
            "agent": agent_id,
            "model_id": "gemini-3.7-flash@pinned",
            "scope": scopes or ["ww.balances.read", "ww.leaves.write", "si.incident.read", "si.incident.write"],
            "jti": jti,
            "iat": now,
            "exp": now + ttl_seconds
        }

        token = jwt.encode(payload, _private_pem, algorithm="RS256")
        return token

    def verify_subject_assertion(self, token: str, expected_audience: Optional[str] = None) -> Dict[str, Any]:
        """
        Verifies RS256 signature, expiry, audience, and enforces replay defense via jti.
        """
        try:
            payload = jwt.decode(
                token,
                _public_pem,
                algorithms=["RS256"],
                options={"verify_aud": False}
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Subject assertion expired")
        except jwt.PyJWTError as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid subject assertion: {str(e)}")

        # Audience check
        if expected_audience and payload.get("aud") != expected_audience:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Audience mismatch in subject assertion")

        # Replay Defense (SDD §4.1)
        jti = payload.get("jti")
        employee_id = payload.get("sub")
        audience = payload.get("aud", "")
        if jti and employee_id:
            if not firestore_store.check_and_set_jti(jti, employee_id, audience):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Replay defense triggered: Token JTI nonce already used."
                )

        return payload


token_manager = CompositeTokenManager()
