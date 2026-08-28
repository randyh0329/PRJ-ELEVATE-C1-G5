"""Unit tests for MCPTokenManager with Google Cloud Secret Manager & Smart Fallback."""

import time
from unittest.mock import MagicMock
from src.security.mcp_token_manager import MCPTokenManager


def test_mcp_token_manager_fallback_lookup():
    """Verify default fallback lookup when running offline/in tests."""
    mgr = MCPTokenManager()
    token = mgr.get_user_token("romij@google.com")
    assert token is not None
    assert token.startswith("mcp_")


def test_mcp_token_manager_save_and_retrieve():
    """Verify registering a new user token and retrieving it from memory store."""
    mgr = MCPTokenManager()
    test_email = "tester.new@google.com"
    test_token = "mcp_test_token_custom_abc123"

    assert mgr.save_user_token(test_email, test_token) is True
    retrieved = mgr.get_user_token(test_email)
    assert retrieved == test_token


def test_mcp_token_manager_masking():
    """Verify sensitive FastMCP token masking for UI security."""
    mgr = MCPTokenManager()
    masked = mgr.mask_token("mcp_ABCDefghIJKLmnopQRSTuvwxYZ0123456789wxyz")
    assert masked.startswith("mcp_ABCD...")
    assert masked.endswith("wxyz")
    assert "IJKLmnop" not in masked

    assert mgr.mask_token(None) == "None"
    assert mgr.mask_token("short") == "******"


def test_mcp_token_manager_secret_manager_integration():
    """Verify Secret Manager client interaction when GCP Secret Manager is mocked."""
    mgr = MCPTokenManager(project_id="test-prj", secret_id="mcp-user-tokens")
    
    # Mock Secret Manager client
    mock_client = MagicMock()
    mock_payload = MagicMock()
    mock_payload.data.decode.return_value = '{"alice@google.com": "mcp_alice_123"}'
    mock_version = MagicMock()
    mock_version.payload = mock_payload
    mock_client.access_secret_version.return_value = mock_version

    mgr._sm_client = mock_client
    mgr._use_secret_manager = True
    mgr._is_gcp_environment = lambda: True

    # Test reading
    token = mgr.get_user_token("alice@google.com")
    assert token == "mcp_alice_123"
    mock_client.access_secret_version.assert_called_once()

    # Test caching: second call should NOT access Secret Manager again
    token2 = mgr.get_user_token("alice@google.com")
    assert token2 == "mcp_alice_123"
    assert mock_client.access_secret_version.call_count == 1

    # Test writing to Secret Manager
    assert mgr.save_user_token("bob@google.com", "mcp_bob_456") is True
    mock_client.add_secret_version.assert_called_once()
