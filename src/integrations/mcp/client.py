"""
SaaS FastMCP Client supporting Synchronous and Asynchronous execution.
Connects directly to:
  - WorkWeek FastMCP Server:            https://mock-saas.aishprabhat.demo.altostrat.com/work-week/mcp/
  - ServiceImmediately FastMCP Server:  https://mock-saas.aishprabhat.demo.altostrat.com/service-immediately/mcp/
Authenticates using the custom 'X-MCP-Token' header to bypass Google Cloud IAP at the Google Frontend (GFE) layer.
"""

import asyncio
import contextvars
import json
import logging
from typing import Any

import httpx

from config.settings import get_settings

logger = logging.getLogger("integrations.mcp")

# ContextVar for per-request / per-user custom MCP token injection
current_mcp_token: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_mcp_token", default=None)


class SaaSFastMCPClient:
    """Enterprise FastMCP client with dual Sync/Async support."""

    def __init__(
        self,
        base_url: str | None = None,
        mcp_token: str | None = None,
        timeout: float = 15.0
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.SAAS_MCP_BASE_URL).rstrip("/")
        self.mcp_token = mcp_token or settings.SAAS_MCP_CREDENTIAL
        self.timeout = timeout
        self._async_client: httpx.AsyncClient | None = None
        self._sync_client: httpx.Client | None = None
        self._bound_loop = None
        self._cached_employee_id: str | None = None

    def _get_headers(self, override_token: str | None = None) -> dict[str, str]:
        # NOTE: Do NOT send 'Authorization' header to avoid GFE intercepting!
        token = override_token or current_mcp_token.get() or self.mcp_token
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-MCP-Token": token,
        }


    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None or self._sync_client.is_closed:
            self._sync_client = httpx.Client(timeout=self.timeout)
        return self._sync_client

    async def _get_async_client(self) -> httpx.AsyncClient:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if (
            self._async_client is None
            or self._async_client.is_closed
            or getattr(self, "_bound_loop", None) != current_loop
        ):
            self._bound_loop = current_loop
            self._async_client = httpx.AsyncClient(timeout=self.timeout)
        return self._async_client

    def call_tool_sync(
        self,
        server_path: str,
        tool_name: str,
        arguments: dict[str, Any],
        override_token: str | None = None
    ) -> dict[str, Any]:
        """Synchronously invoke an MCP tool via JSON-RPC 2.0."""
        client = self._get_sync_client()
        clean_path = server_path.strip("/")
        url = f"{self.base_url}/{clean_path}/"

        payload = {
            "jsonrpc": "2.0",
            "id": f"sync-call-{tool_name}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        resp = client.post(url, json=payload, headers=self._get_headers(override_token=override_token))
        if resp.status_code == 200:
            data = resp.json()
            if "result" in data:
                return data["result"]
            return data

        logger.error("Sync MCP call %s to %s failed with %s: %s", tool_name, url, resp.status_code, resp.text)
        raise RuntimeError(f"FastMCP call failed with HTTP {resp.status_code}: {resp.text}")

    def read_resource_sync(self, server_path: str, uri: str, override_token: str | None = None) -> dict[str, Any]:
        """Synchronously reads an MCP resource (JSON-RPC 'resources/read')."""
        client = self._get_sync_client()
        clean_path = server_path.strip("/")
        url = f"{self.base_url}/{clean_path}/"

        payload = {
            "jsonrpc": "2.0",
            "id": "resource-read",
            "method": "resources/read",
            "params": {"uri": uri}
        }

        resp = client.post(url, json=payload, headers=self._get_headers(override_token=override_token))

        if resp.status_code == 200:
            data = resp.json()
            if "result" in data:
                return data["result"]
            return data

        logger.error("Sync MCP resource read %s at %s failed: %s %s", uri, url, resp.status_code, resp.text)
        raise RuntimeError(f"FastMCP resource read failed with HTTP {resp.status_code}: {resp.text}")

    def get_employee_profile(self, employee_id: str) -> dict[str, Any]:
        """Reads WorkWeek employee profile resource (workweek://employees/{id}/profile)."""
        uri = f"workweek://employees/{employee_id}/profile"
        try:
            res = self.read_resource_sync("work-week/mcp/", uri)
            contents = res.get("contents", [{}])[0].get("text", "{}")
            return json.loads(contents)
        except Exception as e:
            logger.warning("Failed to read employee profile resource %s: %s", uri, e)
            try:
                return self.get_personal_info(employee_id)
            except Exception:
                return {}

    async def call_tool_async(

        self,
        server_path: str,
        tool_name: str,
        arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Asynchronously invoke an MCP tool via JSON-RPC 2.0."""
        client = await self._get_async_client()
        clean_path = server_path.strip("/")
        url = f"{self.base_url}/{clean_path}/"

        payload = {
            "jsonrpc": "2.0",
            "id": f"async-call-{tool_name}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        resp = await client.post(url, json=payload, headers=self._get_headers())
        if resp.status_code == 200:
            data = resp.json()
            if "result" in data:
                return data["result"]
            return data

        logger.error("Async MCP call %s to %s failed with %s: %s", tool_name, url, resp.status_code, resp.text)
        raise RuntimeError(f"FastMCP call failed with HTTP {resp.status_code}: {resp.text}")

    # =========================================================================
    # High-level WorkWeek FastMCP Operations
    # =========================================================================

    def get_current_employee_id(self, token: str | None = None) -> str:
        """Resolves authenticated session employee ID (e.g. 'EMP-509')."""
        if not token and self._cached_employee_id:
            return self._cached_employee_id
        try:
            res = self.call_tool_sync("work-week/mcp/", "get_current_employee_id", {}, override_token=token)
            eid = res.get("structuredContent", {}).get("result") or res.get("result")
            if isinstance(eid, str):
                if not token:
                    self._cached_employee_id = eid
                return eid
            if "content" in res and isinstance(res["content"], list) and len(res["content"]) > 0:
                discovered = res["content"][0].get("text", "EMP-509")
                if not token:
                    self._cached_employee_id = discovered
                return discovered
        except Exception as e:
            logger.warning("Unable to fetch employee id from session: %s", e)
            if token:
                raise
        return "EMP-509"



    def get_employee_balances(self, employee_id: str) -> dict[str, float]:
        """Fetches vacation and sick balances from live WorkWeek FastMCP."""
        res = self.call_tool_sync("work-week/mcp/", "get_employee_balances", {"employee_id": employee_id})
        # Parse content text: "Employee EMP-509 Leave Balances:\n- Vacation: 15.0 days remaining (5.0/20.0 used)\n- Sick: 10.0 days remaining (0.0/10.0 used)"
        text = res.get("content", [{}])[0].get("text", "")
        vacation = 15.0
        sick = 10.0
        try:
            for line in text.splitlines():
                if "Vacation:" in line:
                    vacation = float(line.split("Vacation:")[1].split("days")[0].strip())
                elif "Sick:" in line:
                    sick = float(line.split("Sick:")[1].split("days")[0].strip())
        except Exception as e:
            logger.warning("Error parsing live balance text: %s", e)
        return {"vacation_days_remaining": vacation, "sick_days_remaining": sick}

    def get_personal_info(self, employee_id: str) -> dict[str, str]:
        """Fetches address and phone from live WorkWeek FastMCP."""
        res = self.call_tool_sync("work-week/mcp/", "get_personal_info", {"employee_id": employee_id})
        text = res.get("content", [{}])[0].get("text", "")
        address = ""
        phone = ""
        try:
            for line in text.splitlines():
                if "- Address:" in line:
                    address = line.split("- Address:")[1].strip()
                elif "- Phone:" in line:
                    phone = line.split("- Phone:")[1].strip()
        except Exception:
            pass
        return {"address": address, "phone": phone}


    def update_personal_info(self, employee_id: str, address: str, phone: str) -> dict[str, Any]:
        """Updates contact info in live WorkWeek FastMCP."""
        return self.call_tool_sync("work-week/mcp/", "update_personal_info", {
            "employee_id": employee_id,
            "address": address,
            "phone": phone
        })

    def request_time_off(
        self,
        employee_id: str,
        start_date: str,
        end_date: str,
        leave_type: str,
        days: float
    ) -> dict[str, Any]:
        """Submits time off into live WorkWeek FastMCP."""
        return self.call_tool_sync("work-week/mcp/", "request_time_off", {
            "employee_id": employee_id,
            "start_date": start_date,
            "end_date": end_date,
            "leave_type": leave_type,
            "days": days
        })

    def get_leave_requests(self, employee_id: str) -> list[dict[str, Any]]:
        """Fetches leave request history from live WorkWeek FastMCP."""
        res = self.call_tool_sync("work-week/mcp/", "get_leave_requests", {"employee_id": employee_id})
        text = res.get("content", [{}])[0].get("text", "[]")
        try:
            return json.loads(text)
        except Exception:
            return []

    def cancel_leave_request(self, employee_id: str, request_id: int) -> dict[str, Any]:
        """Cancels a leave request in live WorkWeek FastMCP."""
        return self.call_tool_sync("work-week/mcp/", "cancel_leave_request", {
            "employee_id": employee_id,
            "request_id": int(request_id)
        })

    # =========================================================================
    # High-level ServiceImmediately FastMCP Operations
    # =========================================================================

    def list_tickets(self, employee_id: str) -> list[dict[str, Any]]:
        """Lists incidents from live ServiceImmediately FastMCP."""
        res = self.call_tool_sync("service-immediately/mcp/", "list_tickets", {"employee_id": employee_id})
        text = res.get("content", [{}])[0].get("text", "[]")
        try:
            return json.loads(text)
        except Exception:
            return []

    def create_ticket(
        self,
        requested_by: str,
        category: str,
        short_description: str,
        priority: str,
        assignment_group: str = "Service Desk"
    ) -> dict[str, Any]:
        """Creates a ticket in live ServiceImmediately FastMCP."""
        return self.call_tool_sync("service-immediately/mcp/", "create_ticket", {
            "requested_by": requested_by,
            "category": category,
            "short_description": short_description,
            "priority": priority,
            "assignment_group": assignment_group
        })

    def add_ticket_comment(self, ticket_id: str, author: str, comment: str) -> dict[str, Any]:
        """Adds a comment in live ServiceImmediately FastMCP."""
        return self.call_tool_sync("service-immediately/mcp/", "add_ticket_comment", {
            "ticket_id": ticket_id,
            "author": author,
            "comment": comment
        })

    def update_ticket_status(
        self,
        ticket_id: str,
        status: str,
        resolution_notes: str = "",
        updated_by: str = "System"
    ) -> dict[str, Any]:
        """Updates ticket status in live ServiceImmediately FastMCP."""
        return self.call_tool_sync("service-immediately/mcp/", "update_ticket_status", {
            "ticket_id": ticket_id,
            "status": status,
            "resolution_notes": resolution_notes,
            "updated_by": updated_by
        })


saas_fast_mcp_client = SaaSFastMCPClient()
