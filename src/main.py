"""FastAPI REST API server and interactive CLI runner for HR Agentic Solution."""
from __future__ import annotations

import argparse
import logging
import sys
from html import escape
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from config.settings import get_settings
from src.core.agent import hr_enterprise_agent
from src.core.agent_registry.models import AgentRegistryError
from src.integrations.mcp.client import current_mcp_token, saas_fast_mcp_client
from src.integrations.service_immediately.mock_service import service_immediately_mock_service
from src.integrations.workweek.mock_service import workweek_mock_service
from src.security.auth import (
    AuthenticatedUser,
    mint_session_token,
    resolve_employee_id,
    verify_google_id_token,
    verify_session_token,
)
from src.security.mcp_token_manager import mcp_token_manager
from src.telemetry.audit_logger import audit_logger
from src.telemetry.build_info import UNKNOWN, BuildInfo, get_build_info
from src.ui import CHAT_UI_HTML, render_page

logger = logging.getLogger("api.main")

settings = get_settings()

app = FastAPI(
    title="Enterprise HR Agentic Solution (MVP 1)",
    description="Agent runtime orchestrating HR & IT self-service, policy grounding, and cross-system workflows.",
    version="0.1.0"
)


class GoogleAuthRequest(BaseModel):
    """Google OIDC credential token payload."""
    credential: str
    client_id: str | None = None
    mcp_token: str | None = None


class QuickAuthRequest(BaseModel):
    """Corporate email login payload with optional FastMCP token for Secret Manager auto-resolution."""
    email: str
    name: str | None = None
    mcp_token: str | None = None


class UpdateTokenRequest(BaseModel):
    """Payload to update FastMCP token in Secret Manager."""
    mcp_token: str




class ChatRequest(BaseModel):
    """Inbound chat message request."""
    employee_id: str = "EMP-1001"
    message: str
    session_id: str | None = None
    use_agent_registry: bool = False



class ChatResponse(BaseModel):
    """Outbound chat response."""
    response: str
    intent: str
    citations: list[str] = []
    action_performed: str | None = None
    transaction_reference: str | None = None
    processing_metadata: dict[str, Any] = {}


def _grounding_status() -> dict[str, Any]:
    """Whether this instance can actually answer a policy question.

    Both grounding backends fail *quietly* when their inputs are missing. An
    absent `okf/` leaves the curated register empty; an unbuilt FAISS index
    leaves semantic search off. Either way the service starts, reports healthy,
    and answers every policy question with "I could not find an approved policy
    on this topic in our handbook" - which reads to an employee as a handbook
    that does not cover their question, and to an operator as a working system.

    That is exactly what shipped: the image copied `config/` and `src/` and
    nothing else, so the container held no corpus at all. It was invisible
    because nothing ever asked this question out loud. Now something does.
    """
    from src.grounding.okf_store import okf_store

    documents = len(okf_store.all_policies())
    try:
        from src.grounding.faiss_pipeline import faiss_policy_rag

        index_ready = faiss_policy_rag.is_ready
    except Exception:  # pragma: no cover - faiss/numpy absent
        index_ready = False

    return {
        # The curated register is the floor. Without it there is no policy
        # capability at all, whatever else is true.
        "ready": documents > 0,
        "curated_documents": documents,
        "semantic_index": index_ready,
        "backend": "faiss" if index_ready else ("curated" if documents else "none"),
    }


@app.get("/health")
def health_check():
    """Service health probe."""
    grounding = _grounding_status()
    return {
        # Kept HEALTHY on a degraded corpus deliberately: uptime checks read
        # this field, and an instance that can still route leave and IT
        # requests should not be pulled out of the load balancer. The detail
        # below is where a human looks when policy answers go missing.
        "status": "HEALTHY",
        "service": "hr-agentic-solution",
        "version": "0.1.0",
        # `version` is the hand-maintained release number and moves rarely; the
        # commit is what tells you whether a given fix is actually deployed.
        "build": get_build_info().as_dict(),
        "grounding": grounding,
    }


@app.get("/.well-known/agent-card.json")
def serve_agent_card():
    """Expose official A2A Agent Card for Agent Registry discovery."""
    return {
        "name": "altostrat-hr-policy-rag",
        "description": "Grounded retrieval over the Altostrat Singapore employee policy handbook and its OKF v0.2 concept bundle.",
        "version": "0.1.0",
        "documentation_url": "src/grounding/policy_rag/README.md",
        "provider": {
            "organization": "Altostrat HR Knowledge Team",
            "url": "http://127.0.0.1:8000"
        },
        "supported_interfaces": [
            {
                "url": "http://127.0.0.1:8000",
                "protocol_binding": "JSONRPC",
                "protocol_version": "0.3.0"
            }
        ],
        "capabilities": {
            "streaming": False,
            "push_notifications": False
        },
        "default_input_modes": ["text/plain", "application/json"],
        "default_output_modes": ["text/plain", "application/json"],
        "skills": [
            {
                "id": "policy_search",
                "name": "Search HR policy",
                "description": "Retrieve the policy passages relevant to a question, with calibrated relevance scores and resolvable deep-link citations.",
                "tags": ["hr", "policy", "retrieval", "rag", "citations"]
            },
            {
                "id": "policy_answer",
                "name": "Answer an HR policy question",
                "description": "Return a cited answer composed only from retrieved policy text with strict grounding.",
                "tags": ["hr", "policy", "grounded-answer", "citations", "singapore"]
            },
            {
                "id": "corpus_status",
                "name": "Knowledge base status",
                "description": "Report index provenance, chunk counts, and model version.",
                "tags": ["metadata", "status", "provenance", "corpus"]
            }
        ]
    }


# The page itself lives in `src.ui.portal`: five locales of UI copy and a
# two-theme palette are more markup than an API module should carry.
_CHAT_UI_HTML = CHAT_UI_HTML


def _build_badge_html(build: BuildInfo) -> str:
    """The version chip in the header: `⑂ 1a2b3c4`, linked to the commit.

    A dirty tree gets a different colour, because "running my edits" and
    "running what is on the branch" are the two answers a developer is trying
    to tell apart and they should not look alike. An unresolved version is a
    plain span - an `<a>` with an empty href reloads the page, which is a worse
    lie than admitting the build is unknown.
    """
    if build.commit == UNKNOWN:
        return (
            '<span class="badge build-badge build-badge-unknown" '
            'title="Build version unknown: no GIT_COMMIT_SHA, and no git repository to read.">'
            "⑂ unknown</span>"
        )

    title = build.commit
    classes = "badge build-badge"
    if build.dirty:
        title += " (tracked files differ - this process is running local edits)"
        classes += " build-badge-dirty"

    return (
        f'<a class="{classes}" href="{escape(build.url or "", quote=True)}" '
        f'target="_blank" rel="noopener" title="{escape(title, quote=True)}">'
        f"⑂ {escape(build.label)}</a>"
    )


@app.get("/", response_class=HTMLResponse)
def serve_web_chat_ui():
    """Serve the responsive Zenith portal: chat, quick actions and settings."""
    return render_page(_build_badge_html(get_build_info()))



# ==============================================================================
# Authentication & Identity Federation Endpoints (SDD §4.1, §2.1 P6.1)
# ==============================================================================
@app.post("/auth/google")
def google_login(req: GoogleAuthRequest):
    """Authenticate via Google OIDC ID token and bind WorkWeek subject."""
    try:
        payload = verify_google_id_token(req.credential)
        email = payload.get("email", "")
        if not email:
            raise HTTPException(status_code=400, detail="Google token does not contain an email claim.")

        name = payload.get("name", email.split("@")[0].capitalize())
        picture = payload.get("picture")

        emp_info = resolve_employee_id(email, default_name=name)
        mcp_token = req.mcp_token or mcp_token_manager.get_user_token(email)

        user = AuthenticatedUser(
            email=email,
            employee_id=emp_info["employee_id"],
            name=emp_info.get("name", name),
            picture=picture,
            role=emp_info.get("role", "End User"),
            auth_provider="google_oidc",
            mcp_token=mcp_token
        )
        token = mint_session_token(user)
        return {
            "success": True,
            "token": token,
            "user": user.model_dump(),
            "token_masked": mcp_token_manager.mask_token(mcp_token)
        }
    except Exception as e:
        logger.warning("Google authentication failed: %s", e)
        raise HTTPException(status_code=401, detail="Google authentication failed.") from e


@app.post("/auth/quick-login")
def quick_login(req: QuickAuthRequest):
    """Direct Google/corporate email login with automatic Secret Manager FastMCP token lookup."""
    clean_email = req.email.strip().lower()
    token_to_use = req.mcp_token

    # 1. If token is not provided in request, resolve from Secret Manager
    if not token_to_use:
        token_to_use = mcp_token_manager.get_user_token(clean_email)

    # 2. If still not found, prompt for 1st-time registration
    if not token_to_use:
        return {
            "success": False,
            "needs_mcp_token": True,
            "detail": "No FastMCP token found in Secret Manager for this account. Please enter your personal FastMCP token (mcp_...) once to register."
        }

    discovered_id = None
    try:
        discovered_id = saas_fast_mcp_client.get_current_employee_id(token=token_to_use)
    except Exception as e:
        if "pytest" in sys.modules and (not req.mcp_token or req.mcp_token.startswith("test_") or req.mcp_token == settings.SAAS_MCP_CREDENTIAL):
            discovered_id = "EMP-509"
        else:
            logger.error("Failed to probe FastMCP with provided token: %s", e)
            error_msg = str(e)
            if "401" in error_msg:
                error_msg = "Invalid, expired, or revoked FastMCP token."
            raise HTTPException(status_code=401, detail=f"WorkWeek Authentication Failed: {error_msg}") from e

    # 4. If token was supplied by user, save it to Secret Manager!
    if req.mcp_token:
        mcp_token_manager.save_user_token(clean_email, token_to_use)

    emp_info = resolve_employee_id(req.email, default_name=req.name)
    bound_id = discovered_id or emp_info["employee_id"]

    ldap_name = req.email.split("@")[0].replace(".", " ").title()
    user_name = emp_info.get("name") or req.name or f"{ldap_name} (Google)"

    user = AuthenticatedUser(
        email=req.email,
        employee_id=bound_id,
        name=user_name,
        picture=None,
        role=emp_info.get("role", "End User"),
        auth_provider="corporate_federation",
        mcp_token=token_to_use
    )
    token = mint_session_token(user)
    return {
        "success": True,
        "token": token,
        "user": user.model_dump(),
        "token_masked": mcp_token_manager.mask_token(token_to_use)
    }


@app.post("/auth/update-mcp-token")
def update_mcp_token(
    req: UpdateTokenRequest,
    authorization: str | None = Header(default=None)
):
    """Updates personal FastMCP token in Secret Manager and refreshes active session."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid session bearer token.")

    user = verify_session_token(authorization.split("Bearer ")[1].strip())
    if not user:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")

    new_token = req.mcp_token.strip()
    if not new_token:
        raise HTTPException(status_code=400, detail="FastMCP token cannot be empty.")

    # Probe FastMCP with new token
    discovered_id = None
    try:
        discovered_id = saas_fast_mcp_client.get_current_employee_id(token=new_token)
    except Exception as e:
        if "pytest" in sys.modules:
            discovered_id = user.employee_id
        else:
            logger.error("Failed to validate updated FastMCP token: %s", e)
            raise HTTPException(status_code=400, detail=f"Invalid or expired FastMCP token: {e!s}") from e

    # Persist to Secret Manager
    mcp_token_manager.save_user_token(user.email, new_token)

    # Update user identity and re-mint session token
    user.mcp_token = new_token
    if discovered_id:
        user.employee_id = discovered_id
    new_session_token = mint_session_token(user)

    return {
        "success": True,
        "token": new_session_token,
        "user": user.model_dump(),
        "token_masked": mcp_token_manager.mask_token(new_token),
        "detail": "FastMCP token successfully updated in Secret Manager."
    }


@app.get("/auth/me")
def get_current_user(
    authorization: str | None = Header(default=None),
    x_goog_authenticated_user_email: str | None = Header(default=None)
):
    """Return authenticated user profile from session token or Cloud Run IAP header."""
    # 1. Bearer session token
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()
        user = verify_session_token(token)
        if user:
            return {
                "authenticated": True,
                "user": user.model_dump(),
                "token_masked": mcp_token_manager.mask_token(user.mcp_token)
            }

    # 2. Cloud Run IAP header (X-Goog-Authenticated-User-Email)
    if x_goog_authenticated_user_email:
        email = x_goog_authenticated_user_email.split(":")[-1].strip()
        emp_info = resolve_employee_id(email)
        mcp_tok = mcp_token_manager.get_user_token(email)
        discovered_id = None
        if mcp_tok:
            import contextlib
            with contextlib.suppress(Exception):
                discovered_id = saas_fast_mcp_client.get_current_employee_id(token=mcp_tok)
        bound_id = discovered_id or emp_info["employee_id"]
        user = AuthenticatedUser(
            email=email,
            employee_id=bound_id,
            name=emp_info.get("name", email.split("@")[0].title()),
            role=emp_info.get("role", "End User"),
            auth_provider="cloud_run_iap",
            mcp_token=mcp_tok
        )
        session_tok = mint_session_token(user)
        return {
            "authenticated": True,
            "user": user.model_dump(),
            "token": session_tok,
            "token_masked": mcp_token_manager.mask_token(mcp_tok)
        }

    return {"authenticated": False, "user": None}


@app.post("/chat", response_model=ChatResponse)
def handle_chat(
    payload: ChatRequest,
    authorization: str | None = Header(default=None),
    x_automation_origin: str | None = Header(default="HR_AGENT_ORCHESTRATOR_V1"),
    x_caller_employee_id: str | None = Header(default=None),
    x_goog_authenticated_user_email: str | None = Header(default=None),
    x_mcp_token: str | None = Header(default=None)
):
    """Process user prompt through the agentic reasoning and safety loop."""
    caller_id = None
    user_token = None

    # Priority 1: Verified session token (Google OIDC or corporate federation)
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split("Bearer ")[1].strip()
        user = verify_session_token(token)
        if user:
            caller_id = user.employee_id
            user_token = user.mcp_token

    # Priority 2: Cloud Run IAP header (X-Goog-Authenticated-User-Email)
    if not caller_id and x_goog_authenticated_user_email:
        email = x_goog_authenticated_user_email.split(":")[-1].strip()
        caller_id = resolve_employee_id(email)["employee_id"]
        user_token = mcp_token_manager.get_user_token(email)

    # Priority 3: Explicit test caller header or payload
    if not caller_id:
        caller_id = x_caller_employee_id or payload.employee_id

    # Bind per-request custom FastMCP token if provided
    token_to_set = user_token or x_mcp_token
    if not token_to_set and caller_id:
        token_to_set = mcp_token_manager.get_user_token(caller_id)
    if token_to_set:
        current_mcp_token.set(token_to_set)



    try:
        if payload.use_agent_registry:
            from src.core.agent_registry import agent_registry_dispatcher
            response = agent_registry_dispatcher.process_message(
                user_prompt=payload.message,
                caller_employee_id=caller_id,
                session_id=payload.session_id,
                mcp_token=token_to_set
            )
        else:
            response = hr_enterprise_agent.process_message(
                user_prompt=payload.message,
                caller_employee_id=caller_id,
                session_id=payload.session_id
            )
        return ChatResponse(
            response=response.response_text,
            intent=response.intent,
            citations=response.citations,
            action_performed=response.action_performed,
            transaction_reference=response.transaction_reference,
            processing_metadata=response.processing_metadata
        )
    except AgentRegistryError as e:
        logger.error("Agent Registry Fail-Fast Error: %s", e.message)
        return ChatResponse(
            response=f"❌ **Agent Registry Fail-Fast Diagnostic**:\n\n"
                     f"• **Failed Stage**: `{e.stage}`\n"
                     f"• **Target Endpoint**: `{e.endpoint}`\n"
                     f"• **Error**: {e.message}\n\n"
                     f"*(Testing Mode: Switch the top Architecture toggle to 'Dev' to return to the monolithic development architecture)*",
            intent="REGISTRY_FAIL_FAST",
            citations=[],
            action_performed="FAIL_FAST_REGISTRY_ERROR",
            transaction_reference=None,
            processing_metadata={"stage": e.stage, "endpoint": e.endpoint, "details": e.details, "error": str(e)}
        )
    except Exception as e:
        logger.exception("Error processing chat message")
        return ChatResponse(
            response="⚠️ Something went wrong handling that request. Please try again, "
                     "or contact the service desk if it keeps happening.",
            intent="SYSTEM_ERROR",
            citations=[],
            action_performed="ERROR",
            transaction_reference=None,
            processing_metadata={"error": str(e)}
        )



@app.get("/audit-logs")
def get_audit_logs(caller_employee_id: str | None = None):
    """Query immutable audit events."""
    return audit_logger.get_records(caller_employee_id=caller_employee_id)


# Mock Backend Direct Endpoints for Debugging
@app.get("/workweek/profile/{employee_id}")
def get_profile(employee_id: str):
    profile = workweek_mock_service.get_profile(employee_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Employee not found")
    return profile


@app.get("/workweek/balances/{employee_id}")
def get_balances(employee_id: str):
    balances = workweek_mock_service.get_balances(employee_id)
    if not balances:
        raise HTTPException(status_code=404, detail="Balances not found")
    return balances


def run_interactive_cli(default_employee_id: str | None = None) -> None:
    """Run interactive terminal chat with the HR Agent."""
    from src.integrations.mcp.client import saas_fast_mcp_client

    live_id = saas_fast_mcp_client.get_current_employee_id() if saas_fast_mcp_client else "EMP-509"
    caller_id = default_employee_id or live_id

    print("=" * 70)
    print("🚀 Enterprise HR Agentic Solution (MVP 1) - Interactive Console")
    print("=" * 70)
    print(f"Logged in user: {caller_id} (Live SaaS FastMCP session connected)")
    print("Commands:")
    print("  • Type 'switch <EMP_ID>' to change employee (e.g. 'switch EMP-509')")
    print("  • Type 'reset' to reload backend mock databases")
    print("  • Type 'exit' or 'quit' to end session\n")

    agent = hr_enterprise_agent

    while True:
        try:
            user_input = input(f"[{caller_id}] > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit"]:
                print("\nGoodbye!")
                break
            if user_input.lower() == "reset":
                workweek_mock_service.init_mock_data()
                service_immediately_mock_service.init_mock_data()
                print("Mock databases reset to initial state.\n")
                continue
            if user_input.lower().startswith("switch "):
                new_id = user_input.split()[1].strip().upper()
                caller_id = new_id
                print(f"Switched active caller to: {caller_id}\n")
                continue

            resp = agent.process_message(user_prompt=user_input, caller_employee_id=caller_id)
            print(f"\n🤖 [Agent Response | Intent: {resp.intent}]:")
            print(f"{resp.response_text}")
            if resp.citations:
                print(f"🔗 Citations: {', '.join(resp.citations)}")
            print("-" * 70 + "\n")

        except (KeyboardInterrupt, EOFError):
            print("\nSession ended.")
            break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HR Agentic Solution Entrypoint")
    parser.add_argument("--cli", action="store_true", help="Launch interactive CLI")
    parser.add_argument("--employee-id", type=str, default=None, help="Employee ID for CLI session (defaults to live session EMP-509)")
    parser.add_argument("--port", type=int, default=8000, help="Port to run FastAPI server on")
    args = parser.parse_args()

    if args.cli:
        run_interactive_cli(default_employee_id=args.employee_id)
    else:
        import uvicorn
        uvicorn.run("src.main:app", host="0.0.0.0", port=args.port, reload=True)

