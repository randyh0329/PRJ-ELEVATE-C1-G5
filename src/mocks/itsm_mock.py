import time
import uuid
from typing import Optional, Dict
from fastapi import APIRouter, Request, Header, HTTPException, status
from src.models.serviceimmediately import (
    IncidentDetails,
    CreateIncidentRequest,
    CreateIncidentResponse,
    PostCommentRequest,
    UpdateStatusRequest,
    UpdateStatusResponse,
    CommentItem,
    PriorityEnum,
    TicketStateEnum,
)
from src.mocks.state_manager import state_manager
from src.mocks.fidelity import fidelity_engine

router = APIRouter(prefix="/api/v1/incidents", tags=["ServiceImmediately ITSM Mock"])

# Track recent creations for 10-minute duplicate suppression (FR-4.3)
recent_creations: Dict[str, float] = {}


@router.get("/{ticket_id}", response_model=IncidentDetails, operation_id="si.get_incident")
async def get_incident(
    ticket_id: str,
    request: Request,
    x_subject_assertion: Optional[str] = Header(None, alias="X-Subject-Assertion")
):
    await fidelity_engine.apply_fidelity(request, "si.get_incident")
    inc = state_manager.get_incident(ticket_id)
    if not inc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {ticket_id} not found")

    comments = [CommentItem(**c) for c in inc.get("comments", [])]
    return IncidentDetails(
        ticketId=inc["ticketId"],
        shortDescription=inc["shortDescription"],
        description=inc.get("description"),
        category=inc["category"],
        priority=PriorityEnum(inc["priority"]),
        state=TicketStateEnum(inc["state"]),
        assignee=inc["assignee"],
        comments=comments
    )


@router.post("", response_model=CreateIncidentResponse, status_code=status.HTTP_201_CREATED, operation_id="si.create_incident")
async def create_incident(
    payload: CreateIncidentRequest,
    request: Request,
    x_subject_assertion: Optional[str] = Header(None, alias="X-Subject-Assertion"),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key")
):
    await fidelity_engine.apply_fidelity(request, "si.create_incident")
    fidelity_engine.check_and_record_idempotency(x_idempotency_key)

    # 1. FR-4.3 Priority Verification: '1 - Critical' requires outage, security, or safety keywords
    if payload.priority == PriorityEnum.CRITICAL:
        full_text = f"{payload.shortDescription} {payload.description or ''}".lower()
        critical_keywords = ["outage", "security", "safety", "sev1", "breach", "emergency", "fire", "down"]
        if not any(k in full_text for k in critical_keywords):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Priority verification failed. '1 - Critical' requires verified outage, security, or safety justification."
            )

    # 2. FR-4.3 Duplicate Suppression: Matching ticket within 10 minutes
    now = time.time()
    dedup_key = f"{payload.category}:{payload.shortDescription.strip().lower()}"
    if dedup_key in state_manager.recent_creations:
        last_time = state_manager.recent_creations[dedup_key]
        if (now - last_time) < 600:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Duplicate incident suppressed: identical ticket created within the last 10 minutes."
            )
    state_manager.recent_creations[dedup_key] = now


    ticket_id = f"INC{str(uuid.uuid4().int)[:6]}"
    actor_origin = request.headers.get("X-Agent-Origin", "AI_AGENT_WORKLOAD")

    new_inc = {
        "ticketId": ticket_id,
        "shortDescription": payload.shortDescription,
        "description": payload.description,
        "category": payload.category,
        "priority": payload.priority.value,
        "state": TicketStateEnum.NEW.value,
        "assignee": "IT Helpdesk",
        "requestorId": "EMP-44210",
        "createdBy": actor_origin,
        "comments": [
            {
                "author": f"System Agent ({actor_origin})",
                "body": f"Incident logged automatically via verified automation origin: {actor_origin}",
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            }
        ],
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

    state_manager.create_incident(new_inc)
    resp = CreateIncidentResponse(ticketId=ticket_id)
    fidelity_engine.record_idempotency_result(x_idempotency_key, resp.model_dump())
    return resp


@router.post("/{ticket_id}/comments", status_code=status.HTTP_201_CREATED, operation_id="si.post_comment")
async def post_comment(
    ticket_id: str,
    payload: PostCommentRequest,
    request: Request,
    x_subject_assertion: Optional[str] = Header(None, alias="X-Subject-Assertion")
):
    await fidelity_engine.apply_fidelity(request, "si.post_comment")
    inc = state_manager.get_incident(ticket_id)
    if not inc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {ticket_id} not found")

    author = request.headers.get("X-Agent-Origin", "Employee Self-Service")
    comment = {
        "author": author,
        "body": payload.body,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    state_manager.add_incident_comment(ticket_id, comment)
    return {"status": "COMMENT_POSTED", "ticketId": ticket_id}


@router.patch("/{ticket_id}/status", response_model=UpdateStatusResponse, operation_id="si.update_status")
async def update_status(
    ticket_id: str,
    payload: UpdateStatusRequest,
    request: Request,
    x_subject_assertion: Optional[str] = Header(None, alias="X-Subject-Assertion")
):
    await fidelity_engine.apply_fidelity(request, "si.update_status")
    inc = state_manager.get_incident(ticket_id)
    if not inc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incident {ticket_id} not found")

    current_state = inc.get("state", "New")
    target_state = payload.state.value

    # FR-4.3 Transition Constraints: Illegal transitions, e.g. New directly to Closed
    if current_state == TicketStateEnum.NEW.value and target_state == TicketStateEnum.CLOSED.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Illegal lifecycle transition: Incident cannot transition directly from 'New' to 'Closed'. Must go through 'In Progress' or 'Resolved'."
        )
    if current_state == TicketStateEnum.CLOSED.value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Illegal lifecycle transition: Incident is already 'Closed' and cannot be modified."
        )

    state_manager.update_incident_status(ticket_id, target_state, payload.resolutionNotes)
    return UpdateStatusResponse(status="UPDATED", ticketId=ticket_id, state=payload.state)
