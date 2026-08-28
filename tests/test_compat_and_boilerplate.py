"""The compatibility shims and the deferred-integration placeholders.

Two things get pinned here that are easy to break silently.

The `app.*` package re-exports `src.*` so that older import paths keep working.
Nothing else imports it, so a rename in `src` would break those paths without a
single test noticing - which is precisely the failure a compatibility layer
exists to prevent.

The `saas_boilerplate` adapters are §7.7.3 post-MVP scaffolding. Every method
raises. That is the contract: MVP-1 must not appear to write to a live Workday
or ServiceNow tenant and quietly do nothing. A future implementation replaces
the raise; until then, the raise is the behaviour under test.
"""

from __future__ import annotations

import importlib
import sys

import pytest


def test_the_app_namespace_still_resolves():
    """Every name the `app` compatibility bridge advertises is importable."""
    import app
    import app.agents
    import app.saga
    import app.security

    for module in (app, app.agents, app.saga, app.security):
        for name in module.__all__:
            assert getattr(module, name) is not None, f"{module.__name__}.{name}"


def test_the_shims_forward_to_the_same_objects():
    """A shim that returns a *copy* of a class would break `isinstance` at runtime."""
    import app
    import app.agents
    import app.saga
    from src.core.agents.hcm import HCMSpecialistNode
    from src.core.graph import AgentOrchestrationGraph
    from src.saga.ledger import SagaLedgerManager

    assert app.agents.HCMSpecialistNode is HCMSpecialistNode
    assert app.saga.SagaLedgerManager is SagaLedgerManager
    assert app.AgentOrchestrationGraph is AgentOrchestrationGraph


@pytest.mark.parametrize(
    "module_name",
    [
        "app.agents.hcm",
        "app.agents.itsm",
        "app.agents.policy",
        "app.agents.saga",
        "app.agents.supervisor",
        "app.saga.compensation",
        "app.saga.dispatcher",
        "app.saga.ledger",
        "app.security.dlp",
        "app.security.model_armor",
        "app.security.token_minter",
    ],
)
def test_each_star_import_shim_loads(module_name: str):
    """The single-line `from src... import *` modules execute without error."""
    assert importlib.import_module(module_name) is not None


# ---------------------------------------------------------------------------
# Deferred live-SaaS adapters (§7.7.3 P6.x)
# ---------------------------------------------------------------------------


async def test_workday_live_refuses_rather_than_no_ops():
    from src.integrations.saas_boilerplate import WorkdayLiveClientBoilerplate

    client = WorkdayLiveClientBoilerplate(client_id="id", client_secret="secret")
    assert client.base_url == "https://api.workday.com/v40"
    assert client._access_token is None

    with pytest.raises(NotImplementedError, match="deferred beyond MVP 1"):
        await client.authenticate_oauth2()
    with pytest.raises(NotImplementedError, match="deferred beyond MVP 1"):
        await client.get_worker_profile("E7741903")
    with pytest.raises(NotImplementedError, match="deferred beyond MVP 1"):
        await client.submit_time_off_request("E7741903", {"days": 2})


async def test_servicenow_live_refuses_rather_than_no_ops():
    from src.integrations.saas_boilerplate import ServiceNowLiveClientBoilerplate

    client = ServiceNowLiveClientBoilerplate()
    assert client.instance_url.endswith("/api/now")
    assert client._bearer_token is None

    with pytest.raises(NotImplementedError, match="deferred beyond MVP 1"):
        await client.authenticate()
    with pytest.raises(NotImplementedError, match="deferred beyond MVP 1"):
        await client.create_incident({"short_description": "laptop"})
    with pytest.raises(NotImplementedError, match="deferred beyond MVP 1"):
        await client.create_catalog_request("item-1", {"model": "M4"})


async def test_a2a_protocol_refuses_rather_than_no_ops():
    from src.integrations.saas_boilerplate import A2AProtocolBoilerplate
    from src.integrations.saas_boilerplate.a2a_protocol import AgentMessage, BaseA2AProtocol

    protocol = A2AProtocolBoilerplate()
    assert issubclass(A2AProtocolBoilerplate, BaseA2AProtocol)
    assert protocol.topic_id.startswith("projects/")

    message = AgentMessage(
        message_id="msg-1",
        sender_agent_id="supervisor",
        target_agent_id="hcm",
        conversation_id="sess-1",
        intent="SUBMIT_LEAVE",
    )
    # The envelope stamps its own timestamp so a caller cannot forget to.
    assert message.timestamp.startswith("20")
    assert message.payload == {}

    with pytest.raises(NotImplementedError, match="deferred beyond MVP 1"):
        await protocol.send_message(message)
    with pytest.raises(NotImplementedError, match="deferred beyond MVP 1"):
        await protocol.broadcast_event("SAGA_STARTED", {"saga_id": "saga-1"})


def test_the_a2a_interface_cannot_be_subclassed_without_implementing_it():
    """`BaseA2AProtocol` is abstract, so a partial adapter fails at construction."""
    from src.integrations.saas_boilerplate.a2a_protocol import BaseA2AProtocol

    class Partial(BaseA2AProtocol):
        async def send_message(self, message):
            return {}

    with pytest.raises(TypeError, match="broadcast_event"):
        Partial()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_fall_back_when_pydantic_settings_is_absent(monkeypatch):
    """`config.settings` degrades to plain pydantic rather than failing to import.

    The fallback exists so the package imports in a minimal environment. It is
    only reachable when `pydantic_settings` is missing, so the import has to be
    blocked to reach it at all.
    """
    monkeypatch.setitem(sys.modules, "pydantic_settings", None)
    monkeypatch.delitem(sys.modules, "config.settings", raising=False)

    settings_module = importlib.import_module("config.settings")
    try:
        # `SettingsConfigDict` degrades to `dict`, so `model_config` is inert
        # rather than absent, and the defaults still resolve.
        assert settings_module.Settings().BUSINESS_TIMEZONE == "Asia/Singapore"
    finally:
        monkeypatch.undo()
        importlib.reload(importlib.import_module("config.settings"))


def test_settings_are_cached():
    """`get_settings` is `lru_cache`d - callers share one instance."""
    from config.settings import get_settings

    assert get_settings() is get_settings()
