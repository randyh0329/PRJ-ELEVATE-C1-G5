"""Session state and conversation context management."""
import datetime

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Single turn in a chat interaction."""
    role: str  # user, assistant, system
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    citations: list[str] | None = None


class SessionState(BaseModel):
    """Context state for an active user conversation."""
    session_id: str
    employee_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    last_active_at: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class SessionMemory:
    """Manages short-term conversation context in compliance with FR-3.4 (no static caching of leave balances)."""

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def get_or_create_session(self, session_id: str, employee_id: str) -> SessionState:
        """Fetch existing session or initialize a new one."""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionState(session_id=session_id, employee_id=employee_id)
        session = self._sessions[session_id]
        session.last_active_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return session

    def add_message(self, session_id: str, role: str, content: str, citations: list[str] | None = None) -> None:
        """Append a message to the session history."""
        if session_id in self._sessions:
            msg = ChatMessage(role=role, content=content, citations=citations)
            self._sessions[session_id].messages.append(msg)
            self._sessions[session_id].last_active_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def get_history(self, session_id: str) -> list[ChatMessage]:
        """Retrieve message history for a given session."""
        if session_id in self._sessions:
            return self._sessions[session_id].messages
        return []

    def clear(self) -> None:
        """Clear all active sessions."""
        self._sessions.clear()


# Global singleton session store
session_store = SessionMemory()
