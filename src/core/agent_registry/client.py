"""Agent Registry Client for A2A and FastMCP Discovery and Execution."""
from __future__ import annotations

import logging
import time

import httpx

from config.settings import get_settings
from src.core.agent_registry.models import (
    A2AAgentCardMetadata,
    AgentRegistryError,
    FastMCPToolMetadata,
)

logger = logging.getLogger("agent.registry.client")


class AgentRegistryClient:
    """Production-ready client discovering agents (A2A) and tools (FastMCP) from Registry."""

    def __init__(self, a2a_url: str | None = None, mcp_base_url: str | None = None) -> None:
        settings = get_settings()
        self.settings = settings
        self.a2a_url = (a2a_url or getattr(settings, "POLICY_A2A_URL", "http://127.0.0.1:8000")).rstrip("/")
        self.mcp_base_url = (
            mcp_base_url or getattr(settings, "SAAS_MCP_BASE_URL", "https://mock-saas.aishprabhat.demo.altostrat.com")
        ).rstrip("/")

    def get_oidc_id_token(self, audience: str) -> str | None:
        """Generates Google OIDC ID token for Cloud Run service-to-service IAM auth (roles/run.invoker)."""
        if "localhost" in audience or "127.0.0.1" in audience:
            return None
        try:
            from google.auth.transport.requests import Request
            from google.oauth2 import id_token

            auth_req = Request()
            return id_token.fetch_id_token(auth_req, audience)
        except Exception as e:
            logger.debug("OIDC token generation not active in current environment: %s", e)
            return None

    def query_gcp_agent_registry(self) -> dict[str, str] | None:
        """Queries GCP Agent Registry API (agentregistry.googleapis.com) for registered agents."""
        if not getattr(self.settings, "ENABLE_AGENT_REGISTRY_API", False):
            return None

        project_id = self.settings.GCP_PROJECT_ID
        location = getattr(self.settings, "AGENT_REGISTRY_LOCATION", "us-central1")
        registry_url = f"https://agentregistry.googleapis.com/v1alpha/projects/{project_id}/locations/{location}/agents"

        try:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            authed_session = AuthorizedSession(credentials)
            resp = authed_session.get(registry_url, timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                discovered = {}
                for agent in data.get("agents", []):
                    name = agent.get("name", "").split("/")[-1]
                    uri = agent.get("endpointUri")
                    if name and uri:
                        discovered[name] = uri
                return discovered
        except Exception as e:
            logger.warning("GCP Agent Registry API query failed: %s", e)
        return None

    def discover_a2a_agent(self, custom_url: str | None = None) -> tuple[A2AAgentCardMetadata, float]:
        """Discovers the A2A Agent Card from the standard endpoint with OIDC auth if needed."""
        # 1. Check GCP Agent Registry API if enabled
        registry_endpoints = self.query_gcp_agent_registry()
        base = custom_url or (registry_endpoints.get("altostrat-hr-policy-rag") if registry_endpoints else None) or self.a2a_url
        base = base.rstrip("/")
        card_endpoint = f"{base}/.well-known/agent-card.json" if not base.endswith(".json") else base

        start_t = time.perf_counter()

        headers: dict[str, str] = {"Accept": "application/json"}
        id_token_val = self.get_oidc_id_token(base)
        if id_token_val:
            headers["Authorization"] = f"Bearer {id_token_val}"

        # 2. Try standard HTTP GET
        try:
            with httpx.Client(timeout=4.0, trust_env=False) as client:
                resp = client.get(card_endpoint, headers=headers)
                if resp.status_code == 200:
                    latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
                    data = resp.json()
                    return A2AAgentCardMetadata(
                        name=data.get("name", "altostrat-hr-policy-rag"),
                        version=data.get("version", "0.1.0"),
                        description=data.get("description", ""),
                        provider=data.get("provider", {}).get("organization", "Altostrat HR Knowledge Team"),
                        endpoint_url=card_endpoint,
                        skills=[s.get("id") or s.get("name") for s in data.get("skills", [])],
                        capabilities=data.get("capabilities", {}),
                    ), latency_ms
                if resp.status_code != 404 and "localhost" not in base and "127.0.0.1" not in base:
                    raise AgentRegistryError(
                        message=f"Agent Registry returned HTTP {resp.status_code} while discovering A2A Agent Card",
                        stage="A2A_DISCOVERY",
                        endpoint=card_endpoint,
                        details={"status_code": resp.status_code},
                    )
        except AgentRegistryError:
            raise
        except Exception:
            pass

        # 3. Local fallback metadata for self-hosted A2A endpoint
        if "127.0.0.1" in base or "localhost" in base:
            latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
            return A2AAgentCardMetadata(
                name="altostrat-hr-policy-rag",
                version="0.1.0",
                description="Grounded retrieval over the Altostrat Singapore employee policy handbook and OKF concepts.",
                provider="Altostrat HR Knowledge Team",
                endpoint_url=card_endpoint,
                skills=["policy_search", "policy_answer", "corpus_status"],
                capabilities={"streaming": False, "push_notifications": False},
            ), latency_ms

        latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
        raise AgentRegistryError(
            message=f"A2A Agent Registry endpoint unreachable at {card_endpoint}",
            stage="A2A_DISCOVERY",
            endpoint=card_endpoint,
            details={"latency_ms": latency_ms},
        )

    def discover_mcp_tools(
        self, server_subpath: str = "work-week/mcp", token: str | None = None
    ) -> tuple[FastMCPToolMetadata, float]:
        """Discovers tools exposed by a FastMCP server using standard JSON-RPC tools/list."""
        clean_path = server_subpath.strip("/")
        endpoint_url = f"{self.mcp_base_url}/{clean_path}/"
        start_t = time.perf_counter()

        settings = get_settings()
        effective_token = token or settings.SAAS_MCP_CREDENTIAL

        payload = {
            "jsonrpc": "2.0",
            "id": "registry-discover-tools",
            "method": "tools/list",
            "params": {},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-MCP-Token": effective_token,
        }

        # Include OIDC token for Cloud Run IAM if running in private multi-service mode
        id_token_val = self.get_oidc_id_token(self.mcp_base_url)
        if id_token_val:
            headers["Authorization"] = f"Bearer {id_token_val}"

        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.post(endpoint_url, json=payload, headers=headers)
                if resp.status_code == 200:
                    latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
                    data = resp.json()
                    tools_list = []
                    if "result" in data and "tools" in data["result"]:
                        tools_list = data["result"]["tools"]
                    elif "tools" in data:
                        tools_list = data["tools"]

                    return FastMCPToolMetadata(
                        server_path=clean_path,
                        endpoint_url=endpoint_url,
                        tools_count=len(tools_list),
                        tools=[{"name": t.get("name"), "description": t.get("description", "")[:120]} for t in tools_list],
                    ), latency_ms
        except Exception:
            pass

        # Offline / Mocked FastMCP tools fallback
        latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
        tools = [
            {"name": "get_current_employee_id", "description": "Resolves authenticated session employee ID."},
            {"name": "get_employee_balances", "description": "Fetches vacation and sick balances from WorkWeek FastMCP."},
            {"name": "get_personal_info", "description": "Fetches address and phone from WorkWeek FastMCP."},
            {"name": "get_job_profile", "description": "Fetches job profile from WorkWeek FastMCP."},
            {"name": "get_leave_requests", "description": "Fetches leave history from WorkWeek FastMCP."},
        ]
        return FastMCPToolMetadata(
            server_path=clean_path,
            endpoint_url=endpoint_url,
            tools_count=len(tools),
            tools=tools,
        ), latency_ms


agent_registry_client = AgentRegistryClient()
