import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional
import httpx


logger = logging.getLogger("saas_mcp_client")


class SaaSMCPClient:
    """
    SaaS MCP JSON-RPC Client for WorkWeek and ServiceImmediately.
    According to official OpenAPI specification:
      - Endpoints bypass IAP when using 'X-MCP-Token' custom header.
      - Standard 'Authorization' header MUST NOT be sent to avoid GFE intercepting.
      - Transport: Stateless Streamable HTTP FastMCP sub-applications.
        * WorkWeek: /work-week/mcp/
        * ServiceImmediately: /service-immediately/mcp/
    """

    DEFAULT_BASE_URL = "https://mock-saas.aishprabhat.demo.altostrat.com"

    def __init__(
        self,
        base_url: Optional[str] = None,
        mcp_token: Optional[str] = None,
        enable_mock_fallback: bool = False
    ):
        self.base_url = (base_url or os.environ.get("SAAS_MCP_BASE_URL", self.DEFAULT_BASE_URL)).rstrip("/")
        self.mcp_token = mcp_token or os.environ.get("SAAS_MCP_CREDENTIAL", "mcp_HiIwlFkRL-DrjYgdQvO-fMHg8Q8A_YskI5J00qrP8SA")
        self.enable_mock_fallback = enable_mock_fallback
        self._http_client: Optional[httpx.AsyncClient] = None
        self._cached_employee_id: Optional[str] = None

    async def get_client(self) -> httpx.AsyncClient:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if (
            self._http_client is None
            or self._http_client.is_closed
            or getattr(self, "_bound_loop", None) != current_loop
        ):
            self._bound_loop = current_loop
            self._http_client = httpx.AsyncClient(timeout=15.0)
        return self._http_client


    def _get_headers(self) -> Dict[str, str]:
        # NOTE: Do NOT include 'Authorization' header because GFE intercepts it!
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "X-MCP-Token": self.mcp_token,
        }

    async def get_current_employee_id(self) -> str:
        """Resolves employee ID from the authenticated user session."""
        if self._cached_employee_id:
            return self._cached_employee_id
        
        try:
            res = await self.call_tool(
                server_path="work-week/mcp/",
                tool_name="get_current_employee_id",
                arguments={}
            )
            # Response structuredContent is {'result': 'EMP-509'} or content text
            if isinstance(res, dict):
                eid = res.get("structuredContent", {}).get("result") or res.get("result")
                if isinstance(eid, str):
                    self._cached_employee_id = eid
                    return eid
                if "content" in res and isinstance(res["content"], list) and len(res["content"]) > 0:
                    self._cached_employee_id = res["content"][0].get("text", "EMP-509")
                    return self._cached_employee_id
        except Exception as e:
            logger.warning(f"Failed to get current employee id: {e}")

        return "EMP-509"

    async def call_tool(
        self,
        server_path: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executes a tool call on the remote SaaS MCP server via JSON-RPC 2.0 (tools/call).
        """
        client = await self.get_client()
        clean_path = server_path.strip("/")
        url = f"{self.base_url}/{clean_path}/"
        
        payload = {
            "jsonrpc": "2.0",
            "id": f"call-{tool_name}",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        try:
            resp = await client.post(url, json=payload, headers=self._get_headers())
            if resp.status_code == 200:
                data = resp.json()
                if "result" in data:
                    return data["result"]
                return data
            logger.warning(f"Remote MCP server {url} returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            logger.warning(f"Failed to connect to remote SaaS MCP server at {url}: {e}")

        if self.enable_mock_fallback:
            return self._mock_fallback(tool_name, arguments)
        
        raise RuntimeError(f"Failed to execute MCP tool '{tool_name}' on '{url}' (status={resp.status_code if 'resp' in locals() else 'error'})")

    def _mock_fallback(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "MOCK_FALLBACK", "tool": tool_name, "args": args}


saas_mcp_client = SaaSMCPClient()
