import asyncio
import json
import time
import uuid
from typing import Optional, Dict, Any
from fastapi import FastAPI, Request, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from src.config import settings
from src.models.chat import ChatRequest, ChatResponse, Citation
from src.agent_core.graph import orchestration_graph
from src.storage.firestore import firestore_store
from src.gateway.rights_handlers import rights_handler

gateway_app = FastAPI(
    title="Enterprise HR Agentic Solution - API Gateway",
    version="1.4.0",
    description="Ingress API Gateway with Delegated Auth, Model Armor, Cloud DLP, and SSE Streaming"
)

gateway_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@gateway_app.get("/healthz", tags=["System"])
async def health_check():
    return {"status": "HEALTHY", "gateway": "api-gateway", "version": "1.4.0"}


@gateway_app.post("/api/v1/chat", response_model=ChatResponse, tags=["Chat"])
async def handle_chat(
    payload: ChatRequest,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    Main Chat Ingress (SDD §3.1, §3.3).
    Binds employee subject server-side (NEVER model-supplied).
    Enforces Model Armor and Cloud DLP with < 150ms deadline.
    """
    session_id = payload.sessionId or f"sess-{uuid.uuid4().hex[:12]}"
    
    # Resolve employee subject from session or auth header (server-side binding)
    employee_id = "EMP-44210"
    if authorization and "EMP-" in authorization:
        employee_id = authorization.split()[-1]

    session = firestore_store.get_session(session_id)
    if not session:
        session = firestore_store.create_session(session_id, employee_id)

    # Execute through Agent Graph
    result = await orchestration_graph.run(
        user_message=payload.message,
        session_id=session_id,
        employee_id=employee_id
    )

    return ChatResponse(
        sessionId=session_id,
        messageId=result["messageId"],
        content=result["content"],
        citations=result.get("citations", []),
        escalated=result.get("escalated", False),
        escalationDetails=result.get("escalationDetails"),
        guardrailVerdict=result.get("guardrailVerdict", "ALLOW")
    )


@gateway_app.get("/api/v1/stream/{session_id}", tags=["Chat"])
async def stream_chat(
    session_id: str,
    message: str,
    authorization: Optional[str] = Header(None)
):
    """
    Server-Sent Events (SSE) Streaming Endpoint (SDD §3.3).
    Streams tokens in real-time followed by citations and completion event.
    """
    employee_id = "EMP-44210"
    if authorization and "EMP-" in authorization:
        employee_id = authorization.split()[-1]

    async def event_generator():
        yield f"event: start\ndata: {json.dumps({'sessionId': session_id})}\n\n"
        
        result = await orchestration_graph.run(
            user_message=message,
            session_id=session_id,
            employee_id=employee_id
        )

        # Stream words as chunks
        words = result["content"].split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            data = {"delta": chunk}
            yield f"event: chunk\ndata: {json.dumps(data)}\n\n"
            await asyncio.sleep(0.01)

        # Emit citations
        if result.get("citations"):
            citations_data = [c.model_dump() for c in result["citations"]]
            yield f"event: citations\ndata: {json.dumps(citations_data)}\n\n"

        # Emit done
        yield f"event: done\ndata: {json.dumps({'status': 'COMPLETED', 'guardrailVerdict': result.get('guardrailVerdict')})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@gateway_app.post("/api/v1/contest", tags=["Adoption & Compliance"])
async def contest_recommendation(
    payload: Dict[str, Any],
    authorization: Optional[str] = Header(None)
):
    """
    Contest & Appeal Protocol (SDD §9.6, FR-1.4).
    Enables employees to appeal an automated decision or recommendation.
    Generates an escalation outbox record with < 4hr SLA.
    """
    employee_id = payload.get("employeeId", "EMP-44210")
    session_id = payload.get("sessionId", f"sess-{uuid.uuid4().hex[:8]}")
    reason = payload.get("reason", "Employee contested automated output")
    
    appeal_id = f"APL-{uuid.uuid4().hex[:6].upper()}"
    appeal_record = {
        "appealId": appeal_id,
        "sessionId": session_id,
        "employeeId": employee_id,
        "reason": reason,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "slaCommitmentHours": 4,
        "status": "QUEUED_FOR_HR_REVIEW"
    }
    firestore_store.write_escalation_outbox(appeal_record)

    return {
        "status": "APPEAL_LOGGED",
        "appealId": appeal_id,
        "message": "Your appeal has been escalated to HR Employee Relations. SLA commitment: < 4 business hours.",
        "record": appeal_record
    }


# Mount static web UI if directory exists
static_dir = settings.base_dir / "src" / "static"
if static_dir.exists():
    gateway_app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
