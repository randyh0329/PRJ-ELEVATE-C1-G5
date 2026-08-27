"""FastAPI REST API server and interactive CLI runner for HR Agentic Solution."""
import argparse
import sys
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from src.core.agent import HREnterpriseAgent, hr_enterprise_agent
from src.telemetry.audit_logger import audit_logger
from src.integrations.workweek.mock_service import workweek_mock_service
from src.integrations.service_immediately.mock_service import service_immediately_mock_service
from config.settings import get_settings

settings = get_settings()

app = FastAPI(
    title="Enterprise HR Agentic Solution (MVP 1)",
    description="Agent runtime orchestrating HR & IT self-service, policy grounding, and cross-system workflows.",
    version="0.1.0"
)


class ChatRequest(BaseModel):
    """Inbound chat message request."""
    employee_id: str = "EMP-1001"
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Outbound chat response."""
    response: str
    intent: str
    citations: List[str] = []
    action_performed: Optional[str] = None
    transaction_reference: Optional[str] = None
    processing_metadata: Dict[str, Any] = {}


@app.get("/health")
def health_check():
    """Service health probe."""
    return {"status": "HEALTHY", "service": "hr-agentic-solution", "version": "0.1.0"}


@app.post("/chat", response_model=ChatResponse)
def handle_chat(
    payload: ChatRequest,
    x_automation_origin: Optional[str] = Header(default="HR_AGENT_ORCHESTRATOR_V1"),
    x_caller_employee_id: Optional[str] = Header(default=None)
):
    """Process user prompt through the agentic reasoning and safety loop."""
    caller_id = x_caller_employee_id or payload.employee_id
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


@app.get("/audit-logs")
def get_audit_logs(caller_employee_id: Optional[str] = None):
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


def run_interactive_cli() -> None:
    """Run interactive terminal chat with the HR Agent."""
    print("=" * 70)
    print("🚀 Enterprise HR Agentic Solution (MVP 1) - Interactive Console")
    print("=" * 70)
    print("Logged in as default test user: EMP-1001 (Jane Doe, Senior AI Engineer)")
    print("Type 'exit' or 'quit' to end session.")
    print("Type 'reset' to reload backend mock databases.\n")

    caller_id = "EMP-1001"
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
    parser.add_argument("--port", type=int, default=8000, help="Port to run FastAPI server on")
    args = parser.parse_args()

    if args.cli:
        run_interactive_cli()
    else:
        import uvicorn
        uvicorn.run("src.main:app", host="0.0.0.0", port=args.port, reload=True)
