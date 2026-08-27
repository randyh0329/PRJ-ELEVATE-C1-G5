from __future__ import annotations

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documentTitle: str
    uri: str
    section: Optional[str] = None
    snippet: Optional[str] = None


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(..., min_length=1, max_length=4000)
    sessionId: Optional[str] = None
    stream: bool = True


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sessionId: str
    messageId: str
    content: str
    citations: List[Citation] = Field(default_factory=list)
    escalated: bool = False
    escalationDetails: Optional[Dict[str, Any]] = None
    guardrailVerdict: str = "ALLOW"


class PurgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employeeId: str
    confirmationToken: str


class WithdrawConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    employeeId: str
