from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from src.models.common import PriorityEnum, TicketStateEnum


class CommentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    author: str
    body: str = Field(..., max_length=4000)
    createdAt: str


class IncidentDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticketId: str = Field(..., pattern=r"^(INC|REQ)[0-9]{6,}$")
    shortDescription: str
    description: Optional[str] = None
    category: str
    priority: PriorityEnum
    state: TicketStateEnum
    assignee: str
    comments: List[CommentItem] = Field(default_factory=list)


class CreateIncidentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    shortDescription: str = Field(..., max_length=160)
    description: Optional[str] = Field(None, max_length=4000)
    priority: PriorityEnum


class CreateIncidentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticketId: str


class PostCommentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(..., max_length=4000)


class UpdateStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: TicketStateEnum
    resolutionNotes: Optional[str] = Field(None, max_length=4000)


class UpdateStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    ticketId: str
    state: TicketStateEnum
