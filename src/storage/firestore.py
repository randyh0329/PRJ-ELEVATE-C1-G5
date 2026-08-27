import hashlib
import time
from typing import Dict, Any, Optional, List
from src.models.saga import SagaRecord, SagaStep


class FirestoreStateStore:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.messages: Dict[str, List[Dict[str, Any]]] = {}
        self.sagas: Dict[str, Dict[str, Any]] = {}
        self.locks: Dict[str, Dict[str, Any]] = {}
        self.token_cache: Dict[str, Dict[str, Any]] = {}
        self.escalation_outbox: List[Dict[str, Any]] = []

    # 1. Idempotency Lock Management (SDD §5.8.2)
    def acquire_lock(self, employee_id: str, action: str, params: Dict[str, Any]) -> tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Derives deterministic idempotency key:
        sha256(employee_id + action + params_hash + 10_minute_epoch_window)
        Returns (acquired: bool, idempotency_key: str, completed_result: Optional[dict])
        """
        epoch_window = int(time.time() // 600)
        params_str = str(sorted(params.items()))
        raw_key = f"{employee_id}:{action}:{params_str}:{epoch_window}"
        key_digest = hashlib.sha256(raw_key.encode()).hexdigest()

        lock = self.locks.get(key_digest)
        now = time.time()
        if lock:
            if lock["status"] == "COMPLETED":
                return False, key_digest, lock.get("result")
            elif lock["status"] == "ACQUIRED":
                # If still within 10-minute TTL, block duplicate execution
                if (now - lock["acquired_at"]) < 600:
                    return False, key_digest, None

        # Acquire lock
        self.locks[key_digest] = {
            "status": "ACQUIRED",
            "acquired_at": now,
            "ttl": now + 600,
            "result": None
        }
        return True, key_digest, None

    def release_or_complete_lock(self, key_digest: str, result_payload: Dict[str, Any]):
        if key_digest in self.locks:
            self.locks[key_digest]["status"] = "COMPLETED"
            self.locks[key_digest]["result"] = result_payload

    # 2. Session Management (SDD §4.6)
    def create_session(self, session_id: str, employee_id: str, role: str = "EMPLOYEE") -> Dict[str, Any]:
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        # 30-day TTL
        ttl_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 30 * 86400))
        session = {
            "_id": session_id,
            "employeeId": employee_id,
            "role": role,
            "createdAt": now_str,
            "lastActivityAt": now_str,
            "status": "ACTIVE",
            "consent_state": "ACTIVE",
            "ttl_expiry": ttl_str
        }
        self.sessions[session_id] = session
        self.messages[session_id] = []
        return session

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.sessions.get(session_id)

    def revoke_session(self, session_id: str):
        if session_id in self.sessions:
            self.sessions[session_id]["status"] = "REVOKED"

    def add_message(self, session_id: str, message: Dict[str, Any]):
        if session_id not in self.messages:
            self.messages[session_id] = []
        self.messages[session_id].append(message)
        if session_id in self.sessions:
            self.sessions[session_id]["lastActivityAt"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        return self.messages.get(session_id, [])

    # 3. Saga State Management (SDD §4.6.1 & §5.4)
    def save_saga(self, saga_record: Dict[str, Any]):
        self.sagas[saga_record["_id"]] = saga_record

    def get_saga(self, saga_id: str) -> Optional[Dict[str, Any]]:
        return self.sagas.get(saga_id)

    # 4. Token Cache for Replay Defense (SDD §4.1)
    def check_and_set_jti(self, jti: str, employee_id: str, audience: str) -> bool:
        """Returns True if jti is fresh and recorded; False if replayed."""
        key = hashlib.sha256(f"{employee_id}|{audience}|{jti}".encode()).hexdigest()
        now = time.time()
        if key in self.token_cache:
            if now < self.token_cache[key]["ttl"]:
                return False  # Replay detected
        self.token_cache[key] = {
            "employeeId": employee_id,
            "audience": audience,
            "cachedAt": now,
            "ttl": now + 120  # 120s TTL
        }
        return True

    # 5. Escalation Outbox (SDD §5.7)
    def write_escalation_outbox(self, escalation_record: Dict[str, Any]):
        self.escalation_outbox.append(escalation_record)

    # 6. GDPR Article 17 Purge & Consent Withdrawal (SDD §4.6)
    def purge_employee_data(self, employee_id: str) -> int:
        purged_count = 0
        matching_sessions = [s_id for s_id, s in self.sessions.items() if s.get("employeeId") == employee_id]
        for s_id in matching_sessions:
            self.sessions.pop(s_id, None)
            self.messages.pop(s_id, None)
            purged_count += 1

        matching_sagas = [s_id for s_id, s in self.sagas.items() if s.get("employeeId") == employee_id]
        for s_id in matching_sagas:
            self.sagas.pop(s_id, None)
            purged_count += 1
        return purged_count

    def withdraw_consent(self, employee_id: str):
        matching_sessions = [s_id for s_id, s in self.sessions.items() if s.get("employeeId") == employee_id]
        for s_id in matching_sessions:
            if s_id in self.sessions:
                self.sessions[s_id]["consent_state"] = "WITHDRAWN"
            self.messages[s_id] = []  # wipe history immediately

    def clear(self):
        self.sessions.clear()
        self.messages.clear()
        self.sagas.clear()
        self.locks.clear()
        self.token_cache.clear()
        self.escalation_outbox.clear()


firestore_store = FirestoreStateStore()

