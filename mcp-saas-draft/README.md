# SaaS MCP Integration & Google ADK Tools (`mcp-saas-draft`)

[English](README.md) | [한국어](README.ko.md) | [日本語](README.ja.md) | [繁體中文 (台灣)](README.zh-TW.md) | [Bahasa Indonesia](README.id.md)

---

## 📌 Overview
This module provides a production-grade **Model Context Protocol (MCP)** integration connecting **Google ADK (Agent Development Kit)** and **Google GenAI (Gemini)** agents to the enterprise SaaS portal (`https://mock-saas.aishprabhat.demo.altostrat.com/`).

It mounts two live **FastMCP** Streamable HTTP micro-services:
1. **WorkWeek HCM MCP**: Employee profile management, live leave balances, time-off requests, and contact info.
2. **ServiceImmediately ITSM MCP**: IT support tickets, status lifecycle transitions, comments, and priority assignment.

---

## ⚡ Critical Architecture & Authentication

> [!IMPORTANT]
> **Why `X-MCP-Token` is required and standard `Authorization` MUST NOT be sent:**
> - The SaaS portal domain is hosted behind Google Cloud infrastructure.
> - The FastMCP endpoints (`/work-week/mcp/` and `/service-immediately/mcp/`) are configured to **bypass Identity-Aware Proxy (IAP)**, but **Google Frontend (GFE)** intercepts any request containing a standard `Authorization` header and attempts to validate it as a Google OIDC JWT.
> - If you send `Authorization: Bearer <mcp_token>`, GFE rejects the request with `401 Invalid IAP credentials: Unable to parse JWT`.
> - **Solution**: Send your MCP token **strictly** via the custom header:
>   ```http
>   X-MCP-Token: mcp_your_token_here
>   Accept: application/json
>   ```
>   Do **NOT** include the `Authorization` header.

### Endpoints
- **WorkWeek Server**: `https://mock-saas.aishprabhat.demo.altostrat.com/work-week/mcp/`
- **ServiceImmediately Server**: `https://mock-saas.aishprabhat.demo.altostrat.com/service-immediately/mcp/`
- **Transport**: Stateless Streamable HTTP (JSON-RPC 2.0)

---

## 🛠️ Available MCP Tools

### 📅 WorkWeek HCM Tools (`/work-week/mcp/`)
| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `get_current_employee_id` | *None* | Resolves the employee ID of the authenticated user session (e.g. `EMP-509`). |
| `get_employee_balances` | `employee_id` | Fetches remaining vacation and sick leave balances. |
| `request_time_off` | `start_date`, `end_date`, `leave_type`, `days`, `employee_id` | Submits a time-off request (Dates: `YYYY-MM-DD`, leave_type: `'Vacation'` or `'Sick'`). |
| `get_personal_info` | `employee_id` | Retrieves personal contact details (residential address and phone number). |
| `update_personal_info` | `address`, `phone`, `employee_id` | Updates personal contact details (minimum 5 chars for address, E.164 phone). |
| `get_leave_requests` | `employee_id` | Retrieves historical leave requests for the employee. |
| `cancel_leave_request` | `request_id`, `employee_id` | Cancels a pending/approved leave request and refunds the days back to balance. |

### 🎫 ServiceImmediately ITSM Tools (`/service-immediately/mcp/`)
| Tool Name | Parameters | Description |
| :--- | :--- | :--- |
| `list_tickets` | `employee_id` | Lists all incident tickets requested by the employee. |
| `create_ticket` | `category`, `short_description`, `priority`, `assignment_group`, `requested_by` | Submits a new support ticket (`priority`: `'1 - Critical'`, `'2 - High'`, `'3 - Moderate'`, `'4 - Low'`). |
| `add_ticket_comment` | `ticket_id`, `comment`, `author` | Appends a note/comment to the ticket activity timeline. |
| `update_ticket_status` | `ticket_id`, `status`, `resolution_notes`, `updated_by` | Updates ticket lifecycle state (`New` ➔ `In Progress` ➔ `Resolved` ➔ `Closed`). |

---

## 🚀 Quickstart & Manual Testing

### 1. Installation
```bash
pip install -r requirements.txt
```

### 2. Set Environment Variable (Optional)
The code defaults to your team's assigned MCP token, but you can override it:
```bash
export SAAS_MCP_CREDENTIAL="mcp_local_dev_placeholder_set_SAAS_MCP_CREDENTIAL"
```

### 3. Run the Interactive Manual Test
```bash
# Interactive menu mode
python manual_test_mcp.py

# Or run all live tests sequentially
python manual_test_mcp.py --all
```

**Verified Live Output:**
- Authenticated Employee: `EMP-509` (`Romij Employee`)
- Office Address: `Singapore Office, 80 Pasir Panjang Rd, Singapore`
- Vacation Balance: `15.0 days remaining (5.0/20.0 used)`
- Existing Tickets: `INC0003359` (HR Services), `INC0003333` (Inquiry / Help)

---

## 🤖 Google ADK Agent Integration

### Option A: Google ADK `McpToolset`
```python
from google.adk.agents import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

workweek_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://mock-saas.aishprabhat.demo.altostrat.com/work-week/mcp/",
        headers={"X-MCP-Token": "mcp_local_dev_placeholder_set_SAAS_MCP_CREDENTIAL"}
    )
)

serviceimmediately_mcp = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url="https://mock-saas.aishprabhat.demo.altostrat.com/service-immediately/mcp/",
        headers={"X-MCP-Token": "mcp_local_dev_placeholder_set_SAAS_MCP_CREDENTIAL"}
    )
)

agent = Agent(
    name="enterprise_assistant",
    model="gemini-3.5-flash",
    instruction="Assist employees with WorkWeek leave requests and ServiceImmediately support tickets.",
    tools=[workweek_mcp, serviceimmediately_mcp]
)
```

### Option B: Google GenAI SDK (`google-genai`)
```python
from google import genai
from src.adk_tools import ALL_SAAS_ADK_TOOLS

client = genai.Client()
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents="How many vacation days do I have left in WorkWeek?",
    config={"tools": ALL_SAAS_ADK_TOOLS, "temperature": 0.1}
)
print(response.text)
```
