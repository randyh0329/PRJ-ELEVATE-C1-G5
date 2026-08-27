"""The SaaS FastMCP client, offline.

`tests/test_saas_mcp_integration.py` covers this against the live demo tenant
and skips whenever the shared token is expired - which it currently is, so in
practice the JSON-RPC envelope, the header policy and every response parser
have been going untested. These tests substitute the transport instead, so they
run the same code with no network and no credential.

Two behaviours here are load-bearing and easy to break by accident. The client
must never send an `Authorization` header: the mock SaaS sits behind Google
Cloud IAP, and the GFE intercepts `Authorization` before the request reaches the
MCP server, so the custom `X-MCP-Token` header is what makes the call work at
all. And every high-level helper parses a *text* payload out of the MCP content
block, so a malformed response has to degrade to a default rather than raise
into the middle of an agent turn.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from config.settings import get_settings
from src.integrations.mcp.client import SaaSFastMCPClient, current_mcp_token


class Recorder:
    """A transport that records requests and replays a programmed response."""

    def __init__(self, response: httpx.Response | None = None):
        self.response = response or _result({})
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.response

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    @property
    def payload(self) -> dict:
        return json.loads(self.last.content)

    @property
    def arguments(self) -> dict:
        return self.payload["params"]["arguments"]


def _result(result: dict) -> httpx.Response:
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": "x", "result": result})


def _text(body: str) -> httpx.Response:
    """The shape every high-level helper actually parses: text in a content block."""
    return _result({"content": [{"type": "text", "text": body}]})


@pytest.fixture
def transport() -> Recorder:
    return Recorder()


@pytest.fixture
def client(transport) -> SaaSFastMCPClient:
    mcp = SaaSFastMCPClient(base_url="https://saas.invalid/", mcp_token="tok-1")
    mcp._sync_client = httpx.Client(transport=httpx.MockTransport(transport))
    return mcp


def _respond(client: SaaSFastMCPClient, response: httpx.Response) -> Recorder:
    """Rebind the client's transport to return `response`."""
    recorder = Recorder(response)
    client._sync_client = httpx.Client(transport=httpx.MockTransport(recorder))
    return recorder


# --- headers -----------------------------------------------------------------


def test_the_authorization_header_is_never_sent(client):
    """IAP at the GFE intercepts it before the MCP server ever sees the request."""
    assert "Authorization" not in client._get_headers()


def test_the_configured_token_is_the_default(client):
    assert client._get_headers()["X-MCP-Token"] == "tok-1"


def test_the_token_falls_back_to_settings():
    assert SaaSFastMCPClient()._get_headers()["X-MCP-Token"] == (
        get_settings().SAAS_MCP_CREDENTIAL
    )


def test_a_per_request_token_overrides_the_context_and_the_default(client):
    token = current_mcp_token.set("ctx-token")
    try:
        assert client._get_headers()["X-MCP-Token"] == "ctx-token"
        assert client._get_headers(override_token="explicit")["X-MCP-Token"] == "explicit"
    finally:
        current_mcp_token.reset(token)


def test_the_client_accepts_the_event_stream_content_type(client):
    """FastMCP answers `tools/call` with SSE unless both types are offered."""
    assert "text/event-stream" in client._get_headers()["Accept"]


def test_a_trailing_slash_on_the_base_url_is_not_doubled():
    assert SaaSFastMCPClient(base_url="https://saas.invalid/").base_url == "https://saas.invalid"


# --- transport lifecycle -----------------------------------------------------


def test_the_sync_client_is_reused():
    mcp = SaaSFastMCPClient()
    assert mcp._get_sync_client() is mcp._get_sync_client()


def test_a_closed_sync_client_is_replaced():
    mcp = SaaSFastMCPClient()
    first = mcp._get_sync_client()
    first.close()

    assert mcp._get_sync_client() is not first


async def test_the_async_client_is_reused_within_one_loop():
    mcp = SaaSFastMCPClient()
    assert await mcp._get_async_client() is await mcp._get_async_client()


async def test_a_closed_async_client_is_replaced():
    mcp = SaaSFastMCPClient()
    first = await mcp._get_async_client()
    await first.aclose()

    assert await mcp._get_async_client() is not first


async def test_a_client_from_another_loop_is_discarded():
    """Connections belong to the loop that opened them; reusing one raises."""
    mcp = SaaSFastMCPClient()
    stale = await mcp._get_async_client()

    # Simulate having been built under a loop that has since gone away.
    other_loop = asyncio.new_event_loop()
    mcp._bound_loop = other_loop
    try:
        assert await mcp._get_async_client() is not stale
        assert mcp._bound_loop is asyncio.get_running_loop()
    finally:
        other_loop.close()


# --- the JSON-RPC envelope ---------------------------------------------------


def test_a_tool_call_is_well_formed_json_rpc(client, transport):
    client.call_tool_sync("work-week/mcp/", "get_employee_balances", {"employee_id": "EMP-1"})

    assert transport.payload == {
        "jsonrpc": "2.0",
        "id": "sync-call-get_employee_balances",
        "method": "tools/call",
        "params": {
            "name": "get_employee_balances",
            "arguments": {"employee_id": "EMP-1"},
        },
    }


@pytest.mark.parametrize("path", ["work-week/mcp/", "/work-week/mcp", "work-week/mcp"])
def test_the_server_path_is_normalised_however_it_is_written(client, transport, path):
    client.call_tool_sync(path, "t", {})
    assert str(transport.last.url) == "https://saas.invalid/work-week/mcp/"


def test_the_per_call_token_reaches_the_wire(client, transport):
    client.call_tool_sync("work-week/mcp/", "t", {}, override_token="one-shot")
    assert transport.last.headers["X-MCP-Token"] == "one-shot"


def test_a_result_envelope_is_unwrapped(client):
    _respond(client, _result({"content": [{"text": "hi"}]}))
    assert client.call_tool_sync("p", "t", {}) == {"content": [{"text": "hi"}]}


def test_a_response_with_no_result_key_is_returned_whole(client):
    """A JSON-RPC `error` body carries the reason, so it must not be discarded."""
    _respond(client, httpx.Response(200, json={"jsonrpc": "2.0", "error": {"code": -32602}}))

    assert client.call_tool_sync("p", "t", {})["error"] == {"code": -32602}


@pytest.mark.parametrize("status", [401, 429, 500])
def test_a_non_200_names_the_status_in_the_error(client, status):
    _respond(client, httpx.Response(status, text="upstream said no"))

    with pytest.raises(RuntimeError, match=f"HTTP {status}"):
        client.call_tool_sync("p", "t", {})


# --- resources ---------------------------------------------------------------


def test_a_resource_read_uses_the_resources_method(client, transport):
    client.read_resource_sync("work-week/mcp/", "workweek://employees/EMP-1/profile")

    assert transport.payload["method"] == "resources/read"
    assert transport.payload["params"] == {"uri": "workweek://employees/EMP-1/profile"}


def test_a_resource_read_without_a_result_key_is_returned_whole(client):
    _respond(client, httpx.Response(200, json={"jsonrpc": "2.0", "error": "nope"}))
    assert client.read_resource_sync("p", "u") == {"jsonrpc": "2.0", "error": "nope"}


def test_a_failed_resource_read_raises(client):
    _respond(client, httpx.Response(404, text="no such resource"))

    with pytest.raises(RuntimeError, match="resource read failed with HTTP 404"):
        client.read_resource_sync("p", "u")


# --- the async path ----------------------------------------------------------


async def test_an_async_tool_call_is_well_formed(client):
    recorder = Recorder(_result({"ok": True}))
    client._async_client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    client._bound_loop = asyncio.get_running_loop()

    assert await client.call_tool_async("work-week/mcp/", "t", {"a": 1}) == {"ok": True}
    assert recorder.payload["id"] == "async-call-t"
    assert recorder.payload["params"]["arguments"] == {"a": 1}


async def test_an_async_response_with_no_result_is_returned_whole(client):
    recorder = Recorder(httpx.Response(200, json={"error": "x"}))
    client._async_client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    client._bound_loop = asyncio.get_running_loop()

    assert await client.call_tool_async("p", "t", {}) == {"error": "x"}


async def test_an_async_failure_raises(client):
    recorder = Recorder(httpx.Response(503, text="unavailable"))
    client._async_client = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    client._bound_loop = asyncio.get_running_loop()

    with pytest.raises(RuntimeError, match="HTTP 503"):
        await client.call_tool_async("p", "t", {})


# --- session identity --------------------------------------------------------


def test_the_employee_id_comes_from_structured_content(client):
    _respond(client, _result({"structuredContent": {"result": "EMP-777"}}))
    assert client.get_current_employee_id() == "EMP-777"


def test_a_bare_result_string_is_accepted(client):
    _respond(client, _result({"result": "EMP-778"}))
    assert client.get_current_employee_id() == "EMP-778"


def test_the_text_content_block_is_the_last_resort(client):
    _respond(client, _text("EMP-779"))
    assert client.get_current_employee_id() == "EMP-779"


def test_the_resolved_id_is_cached(client):
    recorder = _respond(client, _result({"structuredContent": {"result": "EMP-777"}}))

    assert client.get_current_employee_id() == "EMP-777"
    assert client.get_current_employee_id() == "EMP-777"
    assert len(recorder.requests) == 1


def test_a_caller_supplied_token_bypasses_the_cache(client):
    """The cache is keyed to the ambient session; another token is another user."""
    client._cached_employee_id = "EMP-777"
    recorder = _respond(client, _text("EMP-888"))

    assert client.get_current_employee_id(token="other-session") == "EMP-888"
    assert recorder.last.headers["X-MCP-Token"] == "other-session"
    # ... and must not overwrite the ambient session's identity.
    assert client._cached_employee_id == "EMP-777"


def test_a_structured_identity_resolved_by_token_is_also_not_cached(client):
    """Same rule as the text path: a foreign token must not poison the cache."""
    recorder = _respond(client, _result({"structuredContent": {"result": "EMP-888"}}))

    assert client.get_current_employee_id(token="other-session") == "EMP-888"
    assert recorder.last.headers["X-MCP-Token"] == "other-session"
    assert client._cached_employee_id is None


def test_an_unusable_response_falls_back_to_the_demo_identity(client):
    _respond(client, _result({"structuredContent": {"result": None}, "content": []}))
    assert client.get_current_employee_id() == "EMP-509"


def test_a_transport_failure_falls_back_when_the_session_is_ambient(client):
    _respond(client, httpx.Response(500, text="down"))
    assert client.get_current_employee_id() == "EMP-509"


def test_a_transport_failure_raises_when_a_token_was_supplied(client):
    """An explicit token that cannot be resolved is an auth failure, not a default.

    Silently answering EMP-509 would hand one user another user's records.
    """
    _respond(client, httpx.Response(401, text="unauthorized"))

    with pytest.raises(RuntimeError):
        client.get_current_employee_id(token="bad-token")


# --- WorkWeek helpers: text parsing ------------------------------------------


def test_balances_are_parsed_out_of_the_prose_response(client):
    _respond(
        client,
        _text(
            "Employee EMP-509 Leave Balances:\n"
            "- Vacation: 15.0 days remaining (5.0/20.0 used)\n"
            "- Sick: 10.0 days remaining (0.0/10.0 used)"
        ),
    )

    assert client.get_employee_balances("EMP-509") == {
        "vacation_days_remaining": 15.0,
        "sick_days_remaining": 10.0,
    }


def test_unparseable_balances_degrade_to_the_documented_defaults(client):
    """A parser exception here would surface as a 500 mid-conversation."""
    _respond(client, _text("Vacation: not-a-number days remaining"))

    assert client.get_employee_balances("EMP-509") == {
        "vacation_days_remaining": 15.0,
        "sick_days_remaining": 10.0,
    }


def test_an_empty_balance_response_still_returns_both_keys(client):
    _respond(client, _result({}))
    assert set(client.get_employee_balances("EMP-509")) == {
        "vacation_days_remaining",
        "sick_days_remaining",
    }


def test_personal_info_is_parsed_out_of_the_prose_response(client):
    _respond(client, _text("Profile:\n- Address: 1 Marina Bay, Singapore\n- Phone: +65 6555 0100"))

    assert client.get_personal_info("EMP-509") == {
        "address": "1 Marina Bay, Singapore",
        "phone": "+65 6555 0100",
    }


def test_personal_info_missing_from_the_response_comes_back_empty(client):
    _respond(client, _text("Profile unavailable"))
    assert client.get_personal_info("EMP-509") == {"address": "", "phone": ""}


def test_a_non_text_personal_info_payload_does_not_raise(client):
    """A server that answers with structured content instead of prose.

    Both callers of this treat an empty field as "not on file", so degrading is
    the honest outcome; raising would take down the turn.
    """
    _respond(client, _result({"content": [{"text": {"address": "1 Marina Bay"}}]}))

    assert client.get_personal_info("EMP-509") == {"address": "", "phone": ""}


# --- WorkWeek helpers: the profile resource ----------------------------------


def test_the_profile_resource_is_json_inside_a_contents_block(client):
    _respond(client, _result({"contents": [{"text": json.dumps({"jobTitle": "Engineer"})}]}))

    assert client.get_employee_profile("EMP-509") == {"jobTitle": "Engineer"}


def test_a_missing_profile_resource_falls_back_to_the_personal_info_tool(client):
    """Not every deployment exposes the resource; the tool is always there."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body["method"])
        if body["method"] == "resources/read":
            return httpx.Response(404, text="no resource")
        return _text("- Address: 1 Marina Bay\n- Phone: +65 6555 0100")

    client._sync_client = httpx.Client(transport=httpx.MockTransport(handler))

    assert client.get_employee_profile("EMP-509") == {
        "address": "1 Marina Bay",
        "phone": "+65 6555 0100",
    }
    assert calls == ["resources/read", "tools/call"]


def test_both_profile_paths_failing_yields_an_empty_profile(client):
    _respond(client, httpx.Response(500, text="down"))
    assert client.get_employee_profile("EMP-509") == {}


def test_a_profile_resource_returning_invalid_json_falls_back(client):
    def handler(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["method"] == "resources/read":
            return _result({"contents": [{"text": "<html>login</html>"}]})
        return _text("- Address: A\n- Phone: P")

    client._sync_client = httpx.Client(transport=httpx.MockTransport(handler))

    assert client.get_employee_profile("EMP-509") == {"address": "A", "phone": "P"}


# --- WorkWeek helpers: list responses ----------------------------------------


def test_leave_requests_are_decoded_from_the_text_block(client):
    _respond(client, _text(json.dumps([{"request_id": 12, "status": "APPROVED"}])))
    assert client.get_leave_requests("EMP-509") == [{"request_id": 12, "status": "APPROVED"}]


def test_undecodable_leave_requests_become_an_empty_list(client):
    _respond(client, _text("No leave requests found."))
    assert client.get_leave_requests("EMP-509") == []


def test_tickets_are_decoded_from_the_text_block(client):
    _respond(client, _text(json.dumps([{"ticket_id": "INC-1"}])))
    assert client.list_tickets("EMP-509") == [{"ticket_id": "INC-1"}]


def test_undecodable_tickets_become_an_empty_list(client):
    _respond(client, _text("none"))
    assert client.list_tickets("EMP-509") == []


# --- argument marshalling ----------------------------------------------------


def test_update_personal_info_sends_all_three_fields(client, transport):
    client.update_personal_info("EMP-1", "2 Raffles Place", "+65 6555 0101")

    assert transport.payload["params"]["name"] == "update_personal_info"
    assert transport.arguments == {
        "employee_id": "EMP-1",
        "address": "2 Raffles Place",
        "phone": "+65 6555 0101",
    }


def test_request_time_off_sends_the_full_leave_record(client, transport):
    client.request_time_off("EMP-1", "2026-09-01", "2026-09-03", "Vacation", 3)

    assert transport.arguments == {
        "employee_id": "EMP-1",
        "start_date": "2026-09-01",
        "end_date": "2026-09-03",
        "leave_type": "Vacation",
        "days": 3,
    }


def test_a_request_id_given_as_text_is_coerced_to_an_integer(client, transport):
    """The router extracts it from prose, so it arrives as a string."""
    client.cancel_leave_request("EMP-1", "4012")

    assert transport.arguments == {"employee_id": "EMP-1", "request_id": 4012}


def test_creating_a_ticket_defaults_the_assignment_group(client, transport):
    client.create_ticket("EMP-1", "Hardware", "Laptop will not boot", "P2")

    assert transport.arguments["assignment_group"] == "Service Desk"
    assert transport.arguments["short_description"] == "Laptop will not boot"
    assert str(transport.last.url).endswith("/service-immediately/mcp/")


def test_a_ticket_comment_records_its_author(client, transport):
    client.add_ticket_comment("INC-1", "EMP-1", "any update?")

    assert transport.arguments == {
        "ticket_id": "INC-1",
        "author": "EMP-1",
        "comment": "any update?",
    }


def test_a_status_update_defaults_its_notes_and_actor(client, transport):
    client.update_ticket_status("INC-1", "Resolved")

    assert transport.arguments == {
        "ticket_id": "INC-1",
        "status": "Resolved",
        "resolution_notes": "",
        "updated_by": "System",
    }
