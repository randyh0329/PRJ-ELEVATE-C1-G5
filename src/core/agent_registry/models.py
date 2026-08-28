"""Data models for Agent Registry discovery, trace, and diagnostics."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class A2AAgentCardMetadata(BaseModel):
    """Metadata extracted from discovered A2A Agent Card."""

    name: str
    version: str
    description: str
    provider: str
    endpoint_url: str
    skills: list[str] = Field(default_factory=list)
    capabilities: dict[str, Any] = Field(default_factory=dict)


class FastMCPToolMetadata(BaseModel):
    """Metadata extracted from discovered FastMCP Tools."""

    server_path: str
    endpoint_url: str
    tools_count: int
    tools: list[dict[str, Any]] = Field(default_factory=list)


class AgentRegistryTrace(BaseModel):
    """Execution trace and proof of Agent Registry live operation."""

    architecture: str = "AGENT_REGISTRY_A2A_MCP"
    discovery_status: str = "SUCCESS"
    target_a2a_agent: A2AAgentCardMetadata | None = None
    target_mcp_tools: FastMCPToolMetadata | None = None
    resolved_action: str
    discovery_latency_ms: float = 0.0
    execution_latency_ms: float = 0.0
    total_latency_ms: float = 0.0
    is_live_verified: bool = True
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class AgentRegistryError(Exception):
    """Structured error for Fail-Fast diagnostics during testing."""

    def __init__(
        self,
        message: str,
        stage: str,
        endpoint: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.stage = stage  # e.g., "A2A_DISCOVERY", "MCP_DISCOVERY"
        self.endpoint = endpoint
        self.details = details or {}
