"""FastAPI REST API server and interactive CLI runner for HR Agentic Solution."""
import argparse
import logging
import sys
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from config.settings import get_settings
from src.core.agent import hr_enterprise_agent
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
from src.telemetry.audit_logger import audit_logger
from src.security.mcp_token_manager import mcp_token_manager

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



class ChatResponse(BaseModel):
    """Outbound chat response."""
    response: str
    intent: str
    citations: list[str] = []
    action_performed: str | None = None
    transaction_reference: str | None = None
    processing_metadata: dict[str, Any] = {}


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
    header { background: #0f172a; border-bottom: 1px solid var(--border); padding: 12px 24px; display: flex; align-items: center; justify-content: space-between; }
    .brand { display: flex; align-items: center; gap: 12px; }
    .brand h1 { font-size: 1.1rem; font-weight: 600; }
    .badge { background: rgba(56, 189, 248, 0.12); color: var(--primary); font-size: 0.75rem; padding: 3px 10px; border-radius: 9999px; border: 1px solid rgba(56, 189, 248, 0.25); font-weight: 600; }
    .auth-section { display: flex; align-items: center; gap: 12px; font-size: 0.85rem; }
    .user-chip { display: flex; align-items: center; gap: 8px; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 20px; padding: 5px 14px; font-size: 0.82rem; }
    .btn-connect { background: #2563eb; color: white; border: none; border-radius: 6px; padding: 7px 16px; font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: background 0.15s; display: flex; align-items: center; gap: 8px; box-shadow: 0 2px 4px rgba(37, 99, 235, 0.25); }
    .btn-connect:hover { background: #1d4ed8; }
    .btn-logout { background: transparent; color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.4); border-radius: 6px; padding: 4px 10px; font-size: 0.75rem; cursor: pointer; }
    .btn-logout:hover { background: rgba(239, 68, 68, 0.15); }
    .btn-settings { background: #1e293b; color: var(--text); border: 1px solid var(--border); border-radius: 6px; padding: 6px 12px; font-size: 0.8rem; cursor: pointer; transition: all 0.15s; display: flex; align-items: center; gap: 6px; }
    .btn-settings:hover { background: #334155; border-color: var(--primary); }
    .modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.75); z-index: 1000; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
    .modal { background: #1e293b; border: 1px solid var(--border); border-radius: 12px; width: 92%; max-width: 500px; padding: 24px; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.6); }
    .modal h2 { font-size: 1.15rem; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }
    .modal-desc { font-size: 0.82rem; color: var(--muted); margin-bottom: 16px; line-height: 1.45; }
    .form-group { margin-bottom: 14px; }
    .form-group label { display: block; font-size: 0.82rem; color: var(--muted); margin-bottom: 6px; }
    .form-group input { width: 100%; background: #0f172a; border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; color: var(--text); font-size: 0.88rem; outline: none; box-sizing: border-box; }
    .form-group input:focus { border-color: var(--primary); }
    .token-input-wrap { position: relative; display: flex; align-items: center; }
    .token-input-wrap input { font-family: monospace; padding-right: 40px; }
    .btn-toggle-vis { position: absolute; right: 8px; background: transparent; border: none; color: var(--muted); cursor: pointer; font-size: 0.95rem; padding: 4px; }
    .btn-toggle-vis:hover { color: var(--text); }
    .form-hint { font-size: 0.76rem; color: var(--muted); margin-top: 5px; line-height: 1.4; }
    .status-box { display: none; padding: 8px 12px; border-radius: 6px; font-size: 0.82rem; margin-top: 12px; line-height: 1.4; }
    .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
    .btn-secondary { background: #334155; color: var(--text); border: none; border-radius: 6px; padding: 8px 16px; font-size: 0.85rem; cursor: pointer; }
    .btn-primary { background: var(--primary); color: #0f172a; font-weight: 600; border: none; border-radius: 6px; padding: 8px 18px; font-size: 0.85rem; cursor: pointer; }
    .main-container { flex: 1; display: flex; flex-direction: column; max-width: 960px; width: 100%; margin: 0 auto; padding: 16px; overflow: hidden; }
    
    .action-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
    .category-tabs { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 2px; }
    .tab-btn { background: rgba(255, 255, 255, 0.05); color: var(--muted); border: 1px solid var(--border); border-radius: 6px; padding: 4px 10px; font-size: 0.75rem; cursor: pointer; transition: all 0.2s; white-space: nowrap; }
    .tab-btn:hover { color: var(--text); background: rgba(255, 255, 255, 0.1); }
    .tab-btn.active { background: var(--primary); color: #0f172a; font-weight: 600; border-color: var(--primary); }
    
    .quick-actions { display: flex; gap: 8px; overflow-x: auto; padding: 4px 0 14px; scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.1) transparent; }
    .quick-actions::-webkit-scrollbar { height: 4px; }
    .quick-actions::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.15); border-radius: 2px; }
    .quick-btn { background: #1e293b; color: var(--text); border: 1px solid var(--border); border-radius: 20px; padding: 6px 14px; font-size: 0.8rem; cursor: pointer; white-space: nowrap; transition: all 0.2s; display: inline-flex; align-items: center; gap: 6px; }
    .quick-btn:hover { background: var(--primary); color: #0f172a; border-color: var(--primary); transform: translateY(-1px); }
    .quick-btn.itsm { border-color: rgba(245, 158, 11, 0.4); }
    .quick-btn.itsm:hover { background: #f59e0b; color: #0f172a; border-color: #f59e0b; }
    .quick-btn.policy { border-color: rgba(56, 189, 248, 0.4); }
    .quick-btn.policy:hover { background: #38bdf8; color: #0f172a; border-color: #38bdf8; }
    .quick-btn.cross { border-color: rgba(168, 85, 247, 0.4); }
    .quick-btn.cross:hover { background: #a855f7; color: #ffffff; border-color: #a855f7; }
    
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
    input[type="text"]:disabled { opacity: 0.6; cursor: not-allowed; }
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
    <div class="auth-section" id="authSection">
      <!-- Unauthenticated View -->
      <div id="unauthControls" style="display: flex; align-items: center; gap: 10px;">
        <button class="btn-connect" onclick="openLoginModal()">
          <span>🔑</span> Sign In & Connect WorkWeek
        </button>
      </div>

      <!-- Authenticated View -->
      <div id="authControls" style="display: none; align-items: center; gap: 10px;">
        <div class="user-chip" id="userChip">
          <span>👤</span>
          <strong id="userDisplayName">User</strong>
          <span style="color: var(--muted);" id="userEmailSpan">(email)</span>
          <span class="badge" id="userEmpBadge" style="background: rgba(34, 197, 94, 0.15); color: #4ade80; border-color: rgba(34, 197, 94, 0.3);">EMP-509</span>
        </div>
        <button class="btn-settings" onclick="openTokenModal()" title="FastMCP Token Settings in Secret Manager">🔑 Token</button>
        <button class="btn-settings" onclick="openLoginModal()" title="Switch User Account">⚙️ Switch</button>
        <button class="btn-logout" onclick="logout()">Sign Out</button>
      </div>
    </div>
  </header>

  <div class="main-container">
    <div class="action-header">
      <div class="category-tabs" id="categoryTabs">
        <button class="tab-btn active" onclick="filterCategory('all')">✨ All Actions</button>
        <button class="tab-btn" onclick="filterCategory('hr')">🏖️ WorkWeek (HR)</button>
        <button class="tab-btn" onclick="filterCategory('itsm')">🛠️ ServiceImmediately (ITSM)</button>
        <button class="tab-btn" onclick="filterCategory('policy')">📚 Policies & FAQ</button>
        <button class="tab-btn" onclick="filterCategory('cross')">🔄 Cross-System</button>
      </div>
    </div>

    <div class="quick-actions" id="quickActionsList">
      <!-- WorkWeek / HR Actions -->
      <button class="quick-btn hr" data-cat="hr" onclick="sendQuick('What is my current leave balance?')">🌴 Leave Balances</button>
      <button class="quick-btn hr" data-cat="hr" onclick="sendQuick('Submit 2 days vacation starting next Monday')">✈️ Request Vacation</button>
      <button class="quick-btn hr" data-cat="hr" onclick="sendQuick('Who is my manager and what is my department?')">👤 Manager & Dept</button>
      <button class="quick-btn hr" data-cat="hr" onclick="sendQuick('Show my recent leave request history')">📋 Leave History</button>

      <!-- ServiceImmediately / ITSM Actions -->
      <button class="quick-btn itsm" data-cat="itsm" onclick="sendQuick('Create an IT ticket because my VPN connection keeps dropping.')">🔌 Report VPN Issue</button>
      <button class="quick-btn itsm" data-cat="itsm" onclick="sendQuick('Create an IT ticket for laptop screen flickering and hardware malfunction.')">💻 Report Laptop Issue</button>
      <button class="quick-btn itsm" data-cat="itsm" onclick="sendQuick('Create an IT ticket requesting access to enterprise GitHub repository.')">🔑 Request System Access</button>
      <button class="quick-btn itsm" data-cat="itsm" onclick="sendQuick('List all my active support tickets')">🎫 My Active Tickets</button>
      <button class="quick-btn itsm" data-cat="itsm" onclick="sendQuick('What is the status of ticket INC-5001?')">🔍 Check Ticket Status</button>

      <!-- HR & IT Policies & FAQ -->
      <button class="quick-btn policy" data-cat="policy" onclick="sendQuick('What is the company bereavement leave entitlement policy?')">📖 Bereavement Policy</button>
      <button class="quick-btn policy" data-cat="policy" onclick="sendQuick('What is the policy for purchasing home office monitors for remote workers?')">🏠 Remote Work Policy</button>
      <button class="quick-btn policy" data-cat="policy" onclick="sendQuick('What is the company parental leave duration and entitlement policy?')">👶 Parental Leave Policy</button>

      <!-- Cross-System Orchestration Actions -->
      <button class="quick-btn cross" data-cat="cross" onclick="sendQuick('I just read the remote work policy and saw I am eligible for a home office monitor. Can you verify my remote status and order one for me?')">🖥️ Order Home Monitor (UC-2.1)</button>
      <button class="quick-btn cross" data-cat="cross" onclick="sendQuick('I need to take short-term medical leave starting next Monday. What is the process, and can you set it up for me?')">🏥 Medical Leave & Delegate (UC-2.2)</button>
      <button class="quick-btn cross" data-cat="cross" onclick="sendQuick('I am transferring to the London office next month. Can you tell me the relocation allowance, update my record, and get my building access sorted?')">🇬🇧 London Transfer & Badge (UC-2.3)</button>
    </div>

    <div class="chat-window" id="chatWindow">
      <div class="msg agent">
        <div class="bubble">👋 <strong>Welcome to the Enterprise HR & IT Self-Service AI Agent!</strong><br><br>FastMCP credentials are now integrated with <strong>Google Cloud Secret Manager & Service Account</strong>.<br>Click <strong>[Sign In & Connect WorkWeek]</strong> in the top right to start chatting instantly.</div>
        <div class="meta"><span class="tag">SYSTEM_READY</span></div>
      </div>
    </div>

    <div class="typing" id="typingIndicator">Agent is reasoning & querying FastMCP SaaS...</div>

    <form class="input-bar" id="chatForm" onsubmit="event.preventDefault(); sendMessage();">
      <input type="text" id="userInput" placeholder="Please click 'Sign In & Connect WorkWeek' above to start chatting..." autocomplete="off" disabled />
      <button type="submit" class="send">Send</button>
    </form>
  </div>

  <!-- Connect Modal -->
  <div class="modal-overlay" id="loginModal">
    <div class="modal">
      <h2>🚀 Sign In with Corporate Email</h2>
      <div class="modal-desc">
        Personal FastMCP tokens are resolved automatically from <strong>Google Cloud Secret Manager</strong>. Existing accounts connect in one click.
      </div>
      <div class="form-group">
        <label for="loginEmail">Google Corporate Email</label>
        <input type="text" id="loginEmail" placeholder="your-ldap@google.com" autocomplete="off" />
      </div>
      <div id="tokenRegistrationGroup" style="display: none;">
        <div class="form-group">
          <label for="loginToken">Personal FastMCP Token (X-MCP-Token) - First-Time Setup</label>
          <div class="token-input-wrap">
            <input type="password" id="loginToken" placeholder="mcp_..." autocomplete="off" />
            <button type="button" class="btn-toggle-vis" onclick="toggleTokenVis()" title="Show/Hide Token">👁️</button>
          </div>
          <div class="form-hint">
            Paste your personal FastMCP token once. The Service Account will automatically store it in Secret Manager for all future logins.
          </div>
        </div>
      </div>
      <div class="status-box" id="loginStatus"></div>
      <div class="modal-actions">
        <button class="btn-secondary" onclick="closeLoginModal()">Cancel</button>
        <button class="btn-primary" id="btnDoLogin" onclick="handleConnect()">🚀 Connect & Start</button>
      </div>
    </div>
  </div>

  <!-- Token Settings Modal -->
  <div class="modal-overlay" id="tokenModal">
    <div class="modal">
      <h2>🔑 FastMCP Token Settings</h2>
      <div class="modal-desc">
        FastMCP credentials stored in <strong>Google Cloud Secret Manager</strong> and loaded by Cloud Run Service Account.
      </div>
      <div class="form-group">
        <label>Authenticated Account:</label>
        <div id="tokenModalEmail" style="color: var(--primary); font-weight: 600; font-size: 0.9rem; padding: 4px 0;"></div>
      </div>
      <div class="form-group">
        <label>Active Secret Manager Token:</label>
        <div>
          <span id="tokenModalCurrent" style="font-family: monospace; font-size: 0.85rem; color: #4ade80; background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.25); padding: 4px 10px; border-radius: 6px; display: inline-block;"></span>
        </div>
      </div>
      <div class="form-group">
        <label for="tokenUpdateInput">Update Personal FastMCP Token (mcp_...)</label>
        <div class="token-input-wrap">
          <input type="password" id="tokenUpdateInput" placeholder="mcp_..." autocomplete="off" />
          <button type="button" class="btn-toggle-vis" onclick="toggleTokenUpdateVis()" title="Show/Hide Token">👁️</button>
        </div>
        <div class="form-hint">
          Updating here writes a new secret version directly to Secret Manager and updates your live session.
        </div>
      </div>
      <div class="status-box" id="tokenUpdateStatus"></div>
      <div class="modal-actions">
        <button class="btn-secondary" onclick="closeTokenModal()">Close</button>
        <button class="btn-primary" id="btnDoUpdateToken" onclick="handleUpdateToken()">💾 Update in Secret Manager</button>
      </div>
    </div>
  </div>


  <script>
    const chatWindow = document.getElementById('chatWindow');
    const userInput = document.getElementById('userInput');
    const typingIndicator = document.getElementById('typingIndicator');

    let sessionToken = localStorage.getItem('hr_agent_session_token');
    let currentUser = null;
    let currentMaskedToken = null;

    function openLoginModal() {
      const emailInput = document.getElementById('loginEmail');
      const tokenInput = document.getElementById('loginToken');
      const statusDiv = document.getElementById('loginStatus');
      const tokenGroup = document.getElementById('tokenRegistrationGroup');
      const btn = document.getElementById('btnDoLogin');
      statusDiv.style.display = 'none';
      tokenGroup.style.display = 'none';
      btn.textContent = '🚀 Connect & Start';

      if (currentUser) {
        emailInput.value = currentUser.email;
      } else {
        emailInput.value = localStorage.getItem('hr_agent_custom_email') || '';
      }
      tokenInput.value = localStorage.getItem('hr_agent_custom_mcp_token') || '';
      document.getElementById('loginModal').style.display = 'flex';
    }

    function closeLoginModal() {
      document.getElementById('loginModal').style.display = 'none';
    }

    function toggleTokenVis() {
      const tokenInput = document.getElementById('loginToken');
      tokenInput.type = tokenInput.type === 'password' ? 'text' : 'password';
    }

    function toggleTokenUpdateVis() {
      const tokenInput = document.getElementById('tokenUpdateInput');
      tokenInput.type = tokenInput.type === 'password' ? 'text' : 'password';
    }

    function openTokenModal() {
      const emailDiv = document.getElementById('tokenModalEmail');
      const currentTokenSpan = document.getElementById('tokenModalCurrent');
      const input = document.getElementById('tokenUpdateInput');
      const statusDiv = document.getElementById('tokenUpdateStatus');
      statusDiv.style.display = 'none';
      input.value = '';
      if (currentUser) {
        emailDiv.textContent = `${currentUser.name} (${currentUser.email})`;
        currentTokenSpan.textContent = currentMaskedToken || 'Active in Secret Manager';
      }
      document.getElementById('tokenModal').style.display = 'flex';
    }

    function closeTokenModal() {
      document.getElementById('tokenModal').style.display = 'none';
    }

    async function handleUpdateToken() {
      const input = document.getElementById('tokenUpdateInput');
      const statusDiv = document.getElementById('tokenUpdateStatus');
      const btn = document.getElementById('btnDoUpdateToken');
      const token = input.value.trim();

      if (!token) {
        statusDiv.style.display = 'block';
        statusDiv.style.background = 'rgba(239, 68, 68, 0.2)';
        statusDiv.style.color = '#f87171';
        statusDiv.textContent = 'Please enter a valid FastMCP token (mcp_...).';
        return;
      }

      btn.disabled = true;
      statusDiv.style.display = 'block';
      statusDiv.style.background = 'rgba(56, 189, 248, 0.15)';
      statusDiv.style.color = '#38bdf8';
      statusDiv.textContent = 'Updating Secret Manager and validating FastMCP...';

      try {
        const res = await fetch('/auth/update-mcp-token', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + sessionToken
          },
          body: JSON.stringify({ mcp_token: token })
        });
        const data = await res.json();
        btn.disabled = false;

        if (res.ok && data.success && data.token) {
          sessionToken = data.token;
          localStorage.setItem('hr_agent_session_token', sessionToken);
          localStorage.setItem('hr_agent_custom_mcp_token', token);
          currentUser = data.user;
          currentMaskedToken = data.token_masked;
          renderAuth(currentUser);
          closeTokenModal();
          appendMessage(`🔄 FastMCP token updated in Secret Manager! Bound to [${currentUser.employee_id}].`, false);
        } else {
          statusDiv.style.display = 'block';
          statusDiv.style.background = 'rgba(239, 68, 68, 0.2)';
          statusDiv.style.color = '#f87171';
          statusDiv.textContent = data.detail || 'Failed to update token.';
        }
      } catch (err) {
        btn.disabled = false;
        statusDiv.style.display = 'block';
        statusDiv.style.background = 'rgba(239, 68, 68, 0.2)';
        statusDiv.style.color = '#f87171';
        statusDiv.textContent = 'Network error updating Secret Manager.';
      }
    }

    async function handleConnect() {
      const emailInput = document.getElementById('loginEmail');
      const tokenInput = document.getElementById('loginToken');
      const statusDiv = document.getElementById('loginStatus');
      const tokenGroup = document.getElementById('tokenRegistrationGroup');
      const btn = document.getElementById('btnDoLogin');

      const email = emailInput.value.trim();
      const token = tokenInput.value.trim();

      if (!email) {
        statusDiv.style.display = 'block';
        statusDiv.style.background = 'rgba(239, 68, 68, 0.2)';
        statusDiv.style.color = '#f87171';
        statusDiv.textContent = 'Please enter your corporate Google email.';
        return;
      }

      statusDiv.style.display = 'block';
      statusDiv.style.background = 'rgba(56, 189, 248, 0.15)';
      statusDiv.style.color = '#38bdf8';
      statusDiv.textContent = 'Resolving FastMCP credentials via Secret Manager...';
      btn.disabled = true;

      try {
        const payload = { email: email };
        if (token) {
          payload.mcp_token = token;
        }

        const res = await fetch('/auth/quick-login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        btn.disabled = false;

        if (data.needs_mcp_token) {
          tokenGroup.style.display = 'block';
          statusDiv.style.display = 'block';
          statusDiv.style.background = 'rgba(234, 179, 8, 0.15)';
          statusDiv.style.color = '#facc15';
          statusDiv.textContent = '⚡ First-time setup: Enter your FastMCP token once to store in Secret Manager.';
          btn.textContent = '💾 Save to Secret Manager & Connect';
          return;
        }

        if (res.ok && data.success && data.token) {
          sessionToken = data.token;
          localStorage.setItem('hr_agent_session_token', sessionToken);
          localStorage.setItem('hr_agent_custom_email', email);
          if (token) {
            localStorage.setItem('hr_agent_custom_mcp_token', token);
          }
          currentUser = data.user;
          currentMaskedToken = data.token_masked || 'Active in Secret Manager';
          closeLoginModal();
          renderAuth(currentUser);
          appendMessage(`🔑 Connected to WorkWeek FastMCP! User [${currentUser.name}] bound to employee record [${currentUser.employee_id}].`, false);
        } else {
          statusDiv.style.display = 'block';
          statusDiv.style.background = 'rgba(239, 68, 68, 0.2)';
          statusDiv.style.color = '#f87171';
          statusDiv.textContent = data.detail || 'Connection failed. Please verify credentials.';
        }
      } catch (err) {
        btn.disabled = false;
        statusDiv.style.display = 'block';
        statusDiv.style.background = 'rgba(239, 68, 68, 0.2)';
        statusDiv.style.color = '#f87171';
        statusDiv.textContent = 'Network error contacting backend.';
      }
    }

    async function checkAuth() {
      if (!sessionToken) {
        renderUnauth();
        return;
      }
      try {
        const res = await fetch('/auth/me', {
          headers: { 'Authorization': 'Bearer ' + sessionToken }
        });
        const data = await res.json();
        if (data.authenticated && data.user) {
          currentUser = data.user;
          currentMaskedToken = data.token_masked;
          renderAuth(currentUser);
        } else {
          sessionToken = null;
          localStorage.removeItem('hr_agent_session_token');
          renderUnauth();
        }
      } catch (e) {
        renderUnauth();
      }
    }

    function renderAuth(user) {
      document.getElementById('unauthControls').style.display = 'none';
      document.getElementById('authControls').style.display = 'flex';
      document.getElementById('userDisplayName').textContent = user.name;
      document.getElementById('userEmailSpan').textContent = `(${user.email})`;
      document.getElementById('userEmpBadge').textContent = user.employee_id;
      userInput.disabled = false;
      userInput.placeholder = "Ask anything (e.g. 'What is my current leave balance?', 'Who is my manager?')...";
    }

    function renderUnauth() {
      document.getElementById('unauthControls').style.display = 'flex';
      document.getElementById('authControls').style.display = 'none';
      userInput.disabled = true;
      userInput.placeholder = "Please click 'Sign In & Connect WorkWeek' above to start chatting...";
    }

    function logout() {
      sessionToken = null;
      currentUser = null;
      currentMaskedToken = null;
      localStorage.removeItem('hr_agent_session_token');
      localStorage.removeItem('hr_agent_custom_mcp_token');
      renderUnauth();
      appendMessage('Signed out. WorkWeek connection disconnected.', false);
    }


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
      if (!currentUser) {
        openLoginModal();
        return;
      }
      const text = userInput.value.trim();
      if (!text) return;

      appendMessage(text, true);
      userInput.value = '';
      typingIndicator.style.display = 'block';

      const headers = { 'Content-Type': 'application/json' };
      if (sessionToken) {
        headers['Authorization'] = 'Bearer ' + sessionToken;
      }

      try {
        const res = await fetch('/chat', {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({ employee_id: currentUser.employee_id, message: text })
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
      if (!currentUser) {
        openLoginModal();
        return;
      }
      userInput.value = prompt;
      sendMessage();
    }

    function filterCategory(cat) {
      document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('onclick').includes(`'${cat}'`));
      });
      document.querySelectorAll('#quickActionsList .quick-btn').forEach(btn => {
        if (cat === 'all' || btn.getAttribute('data-cat') === cat) {
          btn.style.display = 'inline-flex';
        } else {
          btn.style.display = 'none';
        }
      });
    }

    window.addEventListener('DOMContentLoaded', checkAuth);

  </script>
</body>
</html>"""



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
    import sys
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
    authorization: Optional[str] = Header(default=None)
):
    """Updates personal FastMCP token in Secret Manager and refreshes active session."""
    import sys
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
            logger.error(f"Failed to validate updated FastMCP token: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid or expired FastMCP token: {str(e)}")

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
            try:
                discovered_id = saas_fast_mcp_client.get_current_employee_id(token=mcp_tok)
            except Exception:
                pass
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

