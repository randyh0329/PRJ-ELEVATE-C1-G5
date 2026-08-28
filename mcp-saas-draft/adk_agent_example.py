"""
Example Google ADK Agent using Live SaaS FastMCP Tools.
Demonstrates both:
  1. Direct Google GenAI SDK native tool binding (Python callable function declarations)
  2. Google ADK McpToolset (Streamable HTTP with X-MCP-Token header)
"""

import os
import asyncio
from src.adk_tools import WORKWEEK_ADK_TOOLS, ITSM_ADK_TOOLS, ALL_SAAS_ADK_TOOLS

# Option A: Native Google GenAI SDK (google-genai)
# ==============================================================================
def create_genai_agent_with_native_tools():
    """
    Creates a Gemini agent using native Python functions as tools.
    The SDK automatically generates function declarations from type hints and docstrings.
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="What are my current leave balances in WorkWeek and do I have any open IT tickets?",
            config=types.GenerateContentConfig(
                tools=ALL_SAAS_ADK_TOOLS,
                temperature=0.1
            )
        )
        print("Agent Response:\n", response.text)
    except ImportError:
        print("[Note] google-genai is not installed in the active environment.")


# Option B: Google ADK McpToolset (StreamableHTTPConnectionParams)
# ==============================================================================
def create_adk_agent_with_streamable_http():
    """
    Creates a Google ADK Agent using the official McpToolset connector.
    As documented in the OpenAPI specification:
      - Bypasses IAP via custom header X-MCP-Token
      - Does NOT send standard Authorization header
    """
    try:
        from google.adk.agents import Agent
        from google.adk.tools.mcp_tool import McpToolset
        from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

        token = os.environ.get("SAAS_MCP_CREDENTIAL", "mcp_local_dev_placeholder_set_SAAS_MCP_CREDENTIAL")

        workweek_mcp = McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url="https://mock-saas.aishprabhat.demo.altostrat.com/work-week/mcp/",
                headers={"X-MCP-Token": token}
            )
        )

        serviceimmediately_mcp = McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url="https://mock-saas.aishprabhat.demo.altostrat.com/service-immediately/mcp/",
                headers={"X-MCP-Token": token}
            )
        )

        agent = Agent(
            name="enterprise_hr_it_agent",
            model="gemini-3.5-flash",
            description="Enterprise assistant managing WorkWeek HR and ServiceImmediately IT tickets.",
            instruction="Assist the user using tools from WorkWeek and ServiceImmediately FastMCP systems.",
            tools=[workweek_mcp, serviceimmediately_mcp],
        )
        print(f"ADK Agent successfully initialized with {len(agent.tools)} MCP toolsets.")
    except ImportError:
        print("[Note] google-adk is not installed in the active environment.")


if __name__ == "__main__":
    print("Initializing Google ADK and GenAI Agent examples...")
    create_genai_agent_with_native_tools()
    create_adk_agent_with_streamable_http()
