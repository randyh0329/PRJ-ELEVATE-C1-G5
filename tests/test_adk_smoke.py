"""
Smoke tests for Google ADK (Agent Development Kit) and FastMCP Toolset integration.
Verifies Phase 1 foundation requirements.
"""
import pytest

pytest.importorskip("google.adk", reason="google-adk package is not installed")


def test_adk_core_imports():
    """Verify core Google ADK symbols can be imported cleanly."""
    from google.adk import Agent, Context, Runner, Workflow
    assert Agent is not None
    assert Context is not None
    assert Runner is not None
    assert Workflow is not None


def test_adk_mcp_toolset_imports():
    """Verify ADK FastMCP Toolset and Connection Params can be imported."""
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StreamableHTTPConnectionParams
    assert McpToolset is not None
    assert StreamableHTTPConnectionParams is not None


def test_adk_mcp_toolset_instantiation():
    """Verify instantiation of McpToolset with headers and custom FastMCP endpoints."""
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StreamableHTTPConnectionParams

    dummy_token = "mcp_token_test_12345"
    workweek_params = StreamableHTTPConnectionParams(
        url="https://mock-saas.aishprabhat.demo.altostrat.com/workweek/mcp/",
        headers={"X-MCP-Token": dummy_token}
    )
    workweek_toolset = McpToolset(connection_params=workweek_params)
    assert workweek_toolset is not None
    assert workweek_toolset.connection_params.headers.get("X-MCP-Token") == dummy_token

    itsm_params = StreamableHTTPConnectionParams(
        url="https://mock-saas.aishprabhat.demo.altostrat.com/service-immediately/mcp/",
        headers={"X-MCP-Token": dummy_token}
    )
    itsm_toolset = McpToolset(connection_params=itsm_params)
    assert itsm_toolset is not None
    assert itsm_toolset.connection_params.headers.get("X-MCP-Token") == dummy_token


def test_adk_agent_definition():
    """Verify that an ADK Agent can be configured with McpToolset and Gemini 3.7 Flash."""
    from google.adk import Agent
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StreamableHTTPConnectionParams

    params = StreamableHTTPConnectionParams(
        url="https://mock-saas.aishprabhat.demo.altostrat.com/workweek/mcp/",
        headers={"X-MCP-Token": "test_token"}
    )
    toolset = McpToolset(connection_params=params)

    agent = Agent(
        name="test_enterprise_adk_agent",
        model="gemini-3.7-flash",
        description="Smoke test enterprise HR agent",
        instruction="Assist employee with WorkWeek HCM self-service operations.",
        tools=[toolset]
    )
    assert agent.name == "test_enterprise_adk_agent"
    assert agent.model == "gemini-3.7-flash"
    assert len(agent.tools) == 1
