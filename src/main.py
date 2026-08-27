"""FastAPI REST API server and interactive CLI runner for HR Agentic Solution."""
import argparse
import sys
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
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


@app.get("/", response_class=HTMLResponse)
def serve_web_chat_ui():
    """Serve responsive interactive web chat UI for testing agent features."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Enterprise HR Agentic Solution (MVP 1)</title>
  <style>
    :root {
      --bg: #0b1120;
      --panel: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --muted: #94a3b8;
      --primary: #38bdf8;
      --primary-hover: #0284c7;
      --bubble-user: #2563eb;
      --bubble-agent: #1e293b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); display: flex; flex-direction: column; height: 100vh; }
    header { background: #0f172a; border-bottom: 1px solid var(--border); padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand h1 { font-size: 1.1rem; font-weight: 600; }
    .badge { background: rgba(56, 189, 248, 0.12); color: var(--primary); font-size: 0.75rem; padding: 3px 10px; border-radius: 9999px; border: 1px solid rgba(56, 189, 248, 0.25); font-weight: 600; }
    .emp-selector { display: flex; align-items: center; gap: 10px; font-size: 0.85rem; color: var(--muted); }
    select { background: #1e293b; color: var(--text); border: 1px solid var(--border); padding: 6px 12px; border-radius: 6px; outline: none; font-size: 0.85rem; }
    .main-container { flex: 1; display: flex; flex-direction: column; max-width: 900px; width: 100%; margin: 0 auto; padding: 16px; overflow: hidden; }
    .quick-actions { display: flex; gap: 8px; overflow-x: auto; padding: 4px 0 14px; scrollbar-width: none; }
    .quick-btn { background: #1e293b; color: var(--text); border: 1px solid var(--border); border-radius: 20px; padding: 6px 14px; font-size: 0.8rem; cursor: pointer; white-space: nowrap; transition: all 0.2s; }
    .quick-btn:hover { background: var(--primary); color: #0f172a; border-color: var(--primary); }
    .chat-window { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 16px; padding-right: 6px; }
    .msg { display: flex; flex-direction: column; max-width: 82%; }
    .msg.user { align-self: flex-end; }
    .msg.agent { align-self: flex-start; }
    .bubble { padding: 12px 16px; border-radius: 14px; line-height: 1.55; font-size: 0.925rem; white-space: pre-wrap; word-break: break-word; }
    .msg.user .bubble { background: var(--bubble-user); color: white; border-bottom-right-radius: 3px; }
    .msg.agent .bubble { background: var(--bubble-agent); border: 1px solid var(--border); border-bottom-left-radius: 3px; }
    .meta { font-size: 0.72rem; color: var(--muted); margin-top: 4px; display: flex; gap: 8px; align-items: center; }
    .meta .tag { background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px; }
    .citations { margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.08); font-size: 0.8rem; }
    .citations a { color: var(--primary); text-decoration: none; }
    .input-bar { display: flex; gap: 10px; padding-top: 14px; }
    input[type="text"] { flex: 1; background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; color: var(--text); font-size: 0.95rem; outline: none; }
    input[type="text"]:focus { border-color: var(--primary); }
    button.send { background: var(--primary); color: #0f172a; font-weight: 600; border: none; border-radius: 8px; padding: 12px 24px; cursor: pointer; transition: background 0.2s; }
    button.send:hover { background: var(--primary-hover); }
    .typing { display: none; color: var(--muted); font-size: 0.85rem; font-style: italic; margin-bottom: 6px; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>🚀 HR Agentic Solution</h1>
      <span class="badge">Google Cloud MVP 1</span>
    </div>
    <div class="emp-selector">
      <span>Logged In As:</span>
      <select id="empSelect">
        <option value="EMP-509" selected>EMP-509 (Romij Employee - Solutions Acceleration Architect)</option>
        <option value="EMP-1001">EMP-1001 (John Doe - Staff Software Engineer)</option>
        <option value="EMP-1002">EMP-1002 (Sarah Smith - Senior PM)</option>
      </select>
    </div>
  </header>

  <div class="main-container">
    <div class="quick-actions">
      <button class="quick-btn" onclick="sendQuick('What is my current leave balance?')">🏖️ Leave Balances</button>
      <button class="quick-btn" onclick="sendQuick('Who is my manager?')">👤 Who is my Manager?</button>
      <button class="quick-btn" onclick="sendQuick('What is my department?')">🏢 My Department</button>
      <button class="quick-btn" onclick="sendQuick('What is my registered address?')">📍 Registered Address</button>
      <button class="quick-btn" onclick="sendQuick('What is my Job Profile?')">📋 Complete Profile</button>
      <button class="quick-btn" onclick="sendQuick('What is the bereavement leave policy?')">📖 Bereavement Policy</button>
      <button class="quick-btn" onclick="sendQuick('Submit 2 days vacation starting next Monday')">✈️ Request Time Off</button>
    </div>

    <div class="chat-window" id="chatWindow">
      <div class="msg agent">
        <div class="bubble">Hello! I am your Enterprise HR & IT Self-Service AI Agent. How can I assist you today? You can ask about your leave balances, view your job profile, check company policies, or submit requests.</div>
        <div class="meta"><span class="tag">SYSTEM_READY</span></div>
      </div>
    </div>

    <div class="typing" id="typingIndicator">Agent is reasoning & querying FastMCP SaaS...</div>

    <form class="input-bar" id="chatForm" onsubmit="event.preventDefault(); sendMessage();">
      <input type="text" id="userInput" placeholder="Ask anything (e.g. 'What is my current leave balance?', 'Who is my manager?')..." autocomplete="off" />
      <button type="submit" class="send">Send</button>
    </form>
  </div>

  <script>
    const chatWindow = document.getElementById('chatWindow');
    const userInput = document.getElementById('userInput');
    const empSelect = document.getElementById('empSelect');
    const typingIndicator = document.getElementById('typingIndicator');

    function appendMessage(text, isUser, meta = null, citations = []) {
      const msgDiv = document.createElement('div');
      msgDiv.className = 'msg ' + (isUser ? 'user' : 'agent');
      
      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      bubble.textContent = text;

      if (citations && citations.length > 0) {
        const citeDiv = document.createElement('div');
        citeDiv.className = 'citations';
        citeDiv.innerHTML = '<strong>References:</strong> ' + citations.map(c => `<a href="${c.url || '#'}" target="_blank">${c.title || c}</a>`).join(', ');
        bubble.appendChild(citeDiv);
      }

      msgDiv.appendChild(bubble);

      if (meta) {
        const metaDiv = document.createElement('div');
        metaDiv.className = 'meta';
        metaDiv.innerHTML = `<span class="tag">${meta.intent || 'AGENT'}</span>` + (meta.action ? `<span class="tag">${meta.action}</span>` : '');
        msgDiv.appendChild(metaDiv);
      }

      chatWindow.appendChild(msgDiv);
      chatWindow.scrollTop = chatWindow.scrollHeight;
    }

    async function sendMessage() {
      const text = userInput.value.trim();
      if (!text) return;

      const empId = empSelect.value;
      appendMessage(text, true);
      userInput.value = '';
      typingIndicator.style.display = 'block';

      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ employee_id: empId, message: text })
        });
        const data = await res.json();
        typingIndicator.style.display = 'none';

        if (res.ok) {
          appendMessage(data.response, false, { intent: data.intent, action: data.action_performed }, data.citations);
        } else {
          appendMessage("Error: " + (data.detail || "Unable to process message"), false);
        }
      } catch (err) {
        typingIndicator.style.display = 'none';
        appendMessage("Network error communicating with HR Agent backend.", false);
      }
    }

    function sendQuick(prompt) {
      userInput.value = prompt;
      sendMessage();
    }
  </script>
</body>
</html>"""



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


def run_interactive_cli(default_employee_id: Optional[str] = None) -> None:
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

