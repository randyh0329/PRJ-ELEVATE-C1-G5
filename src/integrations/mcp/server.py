"""FastMCP Standalone Server for SaaS Integration Adapters (Cloud Run Microservice)."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.integrations.service_immediately.mock_service import service_immediately_mock_service
from src.integrations.workweek.mock_service import workweek_mock_service

logger = logging.getLogger("mcp.server")

app = FastAPI(
    title="SaaS Integration Adapters (FastMCP Service)",
    version="1.0.0",
    description="Dedicated microservice exposing WorkWeek and ServiceImmediately via FastMCP protocol.",
)


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: str | int = "1"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Liveness probe for Cloud Run."""
    return {"status": "HEALTHY", "service": "saas-integration-adapters"}


# ---------------------------------------------------------------------------
# WorkWeek FastMCP Handler
# ---------------------------------------------------------------------------
WORKWEEK_TOOLS = [
    {
        "name": "get_current_employee_id",
        "description": "Resolves the employee ID for the authenticated session.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_employee_balances",
        "description": "Fetches vacation and sick leave balances from WorkWeek.",
        "inputSchema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"],
        },
    },
    {
        "name": "get_personal_info",
        "description": "Fetches employee address and contact information.",
        "inputSchema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"],
        },
    },
    {
        "name": "get_job_profile",
        "description": "Fetches job profile, department, and direct manager info.",
        "inputSchema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"],
        },
    },
    {
        "name": "get_leave_requests",
        "description": "Retrieves pending and approved leave requests.",
        "inputSchema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"],
        },
    },
    {
        "name": "submit_time_off_request",
        "description": "Submits a new time-off or vacation request in WorkWeek.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "start_date": {"type": "string"},
                "end_date": {"type": "string"},
                "leave_type": {"type": "string"},
                "days": {"type": "number"},
            },
            "required": ["employee_id", "start_date", "end_date", "days"],
        },
    },
]


@app.post("/work-week/mcp/")
async def handle_workweek_mcp(req: JsonRpcRequest) -> dict[str, Any]:
    """Handles FastMCP JSON-RPC calls for WorkWeek."""
    method = req.method

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req.id,
            "result": {"tools": WORKWEEK_TOOLS},
        }

    if method == "tools/call":
        name = req.params.get("name")
        args = req.params.get("arguments", {})
        emp_id = args.get("employee_id", "EMP-509")

        if name == "get_current_employee_id":
            return {"jsonrpc": "2.0", "id": req.id, "result": {"employee_id": emp_id}}

        if name == "get_employee_balances":
            bal = workweek_mock_service.get_balances(emp_id)
            return {"jsonrpc": "2.0", "id": req.id, "result": bal or {"vacation_days_remaining": 14.0, "sick_days_remaining": 10.0}}

        if name == "get_personal_info":
            info = workweek_mock_service.get_personal_info(emp_id)
            return {"jsonrpc": "2.0", "id": req.id, "result": info or {}}

        if name == "get_job_profile":
            prof = workweek_mock_service.get_profile(emp_id)
            return {"jsonrpc": "2.0", "id": req.id, "result": prof or {}}

        if name == "get_leave_requests":
            leaves = workweek_mock_service.get_leave_requests(emp_id)
            return {"jsonrpc": "2.0", "id": req.id, "result": {"requests": leaves}}

        if name == "submit_time_off_request":
            res = workweek_mock_service.submit_leave_request(
                employee_id=emp_id,
                leave_type=args.get("leave_type", "vacation"),
                start_date=args.get("start_date", "2026-09-01"),
                end_date=args.get("end_date", "2026-09-02"),
                days=float(args.get("days", 2.0)),
            )
            return {"jsonrpc": "2.0", "id": req.id, "result": res}

        raise HTTPException(status_code=404, detail=f"Unknown tool {name}")

    if method == "resources/read":
        uri = req.params.get("uri", "")
        if "profile" in uri:
            return {"jsonrpc": "2.0", "id": req.id, "result": {"contents": [{"text": "profile data"}]}}
        return {"jsonrpc": "2.0", "id": req.id, "result": {"contents": []}}

    raise HTTPException(status_code=400, detail=f"Unsupported method {method}")


# ---------------------------------------------------------------------------
# ServiceImmediately FastMCP Handler
# ---------------------------------------------------------------------------
ITSM_TOOLS = [
    {
        "name": "get_user_tickets",
        "description": "Fetches ITSM tickets reported by or assigned to an employee.",
        "inputSchema": {
            "type": "object",
            "properties": {"employee_id": {"type": "string"}},
            "required": ["employee_id"],
        },
    },
    {
        "name": "create_incident",
        "description": "Creates a new incident or service request in ServiceImmediately.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "employee_id": {"type": "string"},
                "short_description": {"type": "string"},
                "urgency": {"type": "string"},
            },
            "required": ["employee_id", "short_description"],
        },
    },
]


@app.post("/service-immediately/mcp/")
async def handle_itsm_mcp(req: JsonRpcRequest) -> dict[str, Any]:
    """Handles FastMCP JSON-RPC calls for ServiceImmediately."""
    method = req.method

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req.id,
            "result": {"tools": ITSM_TOOLS},
        }

    if method == "tools/call":
        name = req.params.get("name")
        args = req.params.get("arguments", {})
        emp_id = args.get("employee_id", "EMP-509")

        if name == "get_user_tickets":
            tickets = service_immediately_mock_service.list_incidents(caller_id=emp_id)
            return {"jsonrpc": "2.0", "id": req.id, "result": {"tickets": tickets}}

        if name == "create_incident":
            ticket = service_immediately_mock_service.create_incident(
                caller_id=emp_id,
                short_description=args.get("short_description", "IT Support Request"),
                urgency=args.get("urgency", "medium"),
            )
            return {"jsonrpc": "2.0", "id": req.id, "result": ticket}

        raise HTTPException(status_code=404, detail=f"Unknown tool {name}")

    raise HTTPException(status_code=400, detail=f"Unsupported method {method}")
