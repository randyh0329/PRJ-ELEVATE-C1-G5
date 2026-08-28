"""Unit and integration tests for zero-impact Agent Registry testing architecture."""
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_agent_card_endpoint() -> None:
    """Verify official A2A Agent Card discovery endpoint."""
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "altostrat-hr-policy-rag"
    assert "skills" in data
    skill_ids = [s["id"] for s in data["skills"]]
    assert "policy_answer" in skill_ids
    assert "policy_search" in skill_ids


def test_legacy_mode_zero_impact() -> None:
    """Verify that use_agent_registry=False strictly executes the legacy path."""
    resp = client.post("/chat", json={
        "employee_id": "EMP-1001",
        "message": "What is my current leave balance?",
        "use_agent_registry": False,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] in ["UC_1_2_WORKWEEK_LEAVE", "UC_1_2_VIEW_LEAVE_BALANCES", "LEAVE_BALANCES"]
    assert data.get("processing_metadata", {}).get("architecture") != "AGENT_REGISTRY_A2A_MCP"


def test_agent_registry_mode_a2a_policy_query() -> None:
    """Verify that use_agent_registry=True dynamically resolves A2A Agent Card and skills."""
    resp = client.post("/chat", json={
        "employee_id": "EMP-1001",
        "message": "What is the bereavement leave policy?",
        "use_agent_registry": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "UC_1_1_POLICY_QUERY"
    assert data["action_performed"] == "A2A_SKILL_POLICY_ANSWER"
    meta = data["processing_metadata"]
    assert meta["architecture"] == "AGENT_REGISTRY_A2A_MCP"
    assert meta["target_a2a_agent"]["name"] == "altostrat-hr-policy-rag"
    assert "policy_answer" in meta["target_a2a_agent"]["skills"]
    assert meta["is_live_verified"] is True
    assert meta["total_latency_ms"] > 0


def test_agent_registry_mode_fastmcp_query() -> None:
    """Verify that use_agent_registry=True discovers FastMCP tools."""
    resp = client.post("/chat", json={
        "employee_id": "EMP-509",
        "message": "What are my vacation days remaining?",
        "use_agent_registry": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "UC_1_2_VIEW_LEAVE_BALANCES"
    assert data["action_performed"] == "MCP_TOOL_GET_EMPLOYEE_BALANCES"
    meta = data["processing_metadata"]
    assert meta["architecture"] == "AGENT_REGISTRY_A2A_MCP"
    assert meta["target_mcp_tools"]["tools_count"] > 0
    assert meta["is_live_verified"] is True


def test_agent_registry_fail_fast_diagnostics(monkeypatch) -> None:
    """Verify Fail-Fast returns structured diagnostics when discovery fails."""
    from src.core.agent_registry import agent_registry_client
    from src.core.agent_registry.models import AgentRegistryError

    def failing_discover(custom_url=None):
        raise AgentRegistryError(
            message="Connection refused to registry endpoint",
            stage="A2A_DISCOVERY",
            endpoint="http://invalid-registry-endpoint:9999",
            details={"connection": "failed"},
        )

    monkeypatch.setattr(agent_registry_client, "discover_a2a_agent", failing_discover)

    resp = client.post("/chat", json={
        "employee_id": "EMP-1001",
        "message": "What is the bereavement policy?",
        "use_agent_registry": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action_performed"] == "FAIL_FAST_REGISTRY_ERROR"
    assert data["intent"] == "REGISTRY_FAIL_FAST"
    assert "Agent Registry Fail-Fast Diagnostic" in data["response"]
    assert data["processing_metadata"]["stage"] == "A2A_DISCOVERY"
