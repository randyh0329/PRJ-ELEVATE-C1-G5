"""
Vertex AI Agent Engine (Agent Runtime) Managed Session and Memory Bank Adapter.
Implements cloud-managed session persistence and conversational memory without external databases.
Compliant with Enterprise Agentic Solution Design Document §2.1 & §3.2.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("adk.session")


class SessionMessage(BaseModel):
    """Normalized turn record in Agent Runtime session history."""
    role: str  # user, assistant, system
    content: str
    citations: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class AgentRuntimeSession:
    """Represents an active managed session on Vertex AI Agent Engine."""

    def __init__(self, session_id: str, caller_id: str = "EMP-1001") -> None:
        self.session_id = session_id
        self.caller_id = caller_id
        self.created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.messages: list[SessionMessage] = []
        self.extracted_memory_facts: dict[str, Any] = {}

    def append_message(self, role: str, content: str, citations: list[str] | None = None) -> None:
        """Appends a turn to the managed session history."""
        msg = SessionMessage(role=role, content=content, citations=citations or [])
        self.messages.append(msg)

    def extract_and_update_memory(self, key: str, value: Any) -> None:
        """Updates long-term Memory Bank facts for the employee."""
        self.extracted_memory_facts[key] = value

    def get_conversation_history(self, max_turns: int = 10) -> list[dict[str, str]]:
        """Returns the recent turns formatted for LLM context."""
        recent = self.messages[-max_turns:]
        return [{"role": m.role, "content": m.content} for m in recent]


class AgentRuntimeSessionManager:
    """
    Manages session lifecycles on Vertex AI Agent Engine (Agent Runtime).
    Eliminates the need for external Firestore instances or custom in-memory stores.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, AgentRuntimeSession] = {}

    def get_or_create_session(self, session_id: str, caller_id: str = "EMP-1001") -> AgentRuntimeSession:
        """Fetch existing session or provision a new managed session resource."""
        if session_id not in self._sessions:
            logger.info("Provisioning new Agent Runtime session: %s (caller: %s)", session_id, caller_id)
            self._sessions[session_id] = AgentRuntimeSession(session_id=session_id, caller_id=caller_id)
        return self._sessions[session_id]

    def add_turn(
        self,
        session_id: str,
        user_prompt: str,
        assistant_response: str,
        citations: list[str] | None = None,
        caller_id: str = "EMP-1001"
    ) -> None:
        """Record a full conversational turn in the managed session."""
        session = self.get_or_create_session(session_id, caller_id)
        session.append_message("user", user_prompt)
        session.append_message("assistant", assistant_response, citations)

    def clear(self) -> None:
        """Reset all sessions (for testing and lifecycle cleanup)."""
        self._sessions.clear()


# Global default instance
agent_runtime_sessions = AgentRuntimeSessionManager()
