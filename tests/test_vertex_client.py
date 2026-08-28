"""The Vertex AI Gemini client: credentials, model fallback, schema shaping.

None of this is exercised by the rest of the suite, because `tests/conftest.py`
replaces `route_intent` and `select_workweek_tool` wholesale with a
deterministic mock so the other tests run offline. That is the right trade for
those tests and it leaves the client itself untested - including the credential
chain, which fails in four distinct ways and is the first thing to break in a
new environment.

Everything below stays offline: the HTTP client, the metadata server and the
gcloud subprocess are all substituted. The two routing methods are called
through the module-level references captured at import time, before the autouse
mock in `conftest.py` can rebind them.
"""

from __future__ import annotations

import datetime
import json
import subprocess

import httpx
import pytest

from src.integrations.vertex.client import VertexGeminiClient
from src.models.routing import SupervisorRoutingDecision

# Captured before the autouse `mock_vertex_gemini` fixture patches the class.
_REAL_ROUTE_INTENT = VertexGeminiClient.route_intent
_REAL_SELECT_TOOL = VertexGeminiClient.select_workweek_tool

_ROUTING_JSON = json.dumps(
    {
        "intent": "UC_1_1_POLICY_QA",
        "target_agent": "POLICY_SPECIALIST",
        "confidence": 0.95,
        "reasoning": "handbook question",
    }
)


@pytest.fixture
def no_ambient_credentials(monkeypatch):
    """Remove every credential source, so each test opts into exactly one."""
    monkeypatch.delenv("VERTEX_AI_TOKEN", raising=False)
    monkeypatch.delenv("GCP_ACCESS_TOKEN", raising=False)
    monkeypatch.setattr(
        httpx.Client, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("no metadata"))
    )
    monkeypatch.setattr("src.integrations.vertex.client.shutil.which", lambda _: None)
    monkeypatch.setattr("src.integrations.vertex.client.os.path.isfile", lambda _: False)


@pytest.fixture
def client(monkeypatch) -> VertexGeminiClient:
    monkeypatch.setenv("VERTEX_AI_TOKEN", "test-token")
    return VertexGeminiClient(project_id="p", region="us-central1", model_id="gemini-2.5-flash")


def _response(status: int, payload: dict | None = None, text: str = "") -> httpx.Response:
    request = httpx.Request("POST", "https://example.invalid")
    if payload is not None:
        return httpx.Response(status, json=payload, request=request)
    return httpx.Response(status, text=text, request=request)


def _ok(body: str = _ROUTING_JSON) -> httpx.Response:
    return _response(200, {"candidates": [{"content": {"parts": [{"text": body}]}}]})


# --- construction ------------------------------------------------------------


def test_explicit_arguments_win_over_settings():
    client = VertexGeminiClient(project_id="proj", region="asia-southeast1", model_id="m")
    assert (client.project_id, client.region, client.model_id) == ("proj", "asia-southeast1", "m")


def test_the_model_id_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("VERTEX_MODEL_ID", "gemini-3.7-flash")
    assert VertexGeminiClient().model_id == "gemini-3.7-flash"


# --- the credential chain ----------------------------------------------------


@pytest.mark.parametrize("var", ["VERTEX_AI_TOKEN", "GCP_ACCESS_TOKEN"])
def test_an_environment_token_short_circuits_everything(monkeypatch, var):
    monkeypatch.delenv("VERTEX_AI_TOKEN", raising=False)
    monkeypatch.delenv("GCP_ACCESS_TOKEN", raising=False)
    monkeypatch.setenv(var, "env-token")

    assert VertexGeminiClient()._get_auth_token() == "env-token"


def test_a_cached_token_is_reused_until_it_expires(monkeypatch):
    client = VertexGeminiClient()
    client._cached_token = "cached"
    client._token_expiry = 1e12

    monkeypatch.setenv("VERTEX_AI_TOKEN", "fresh")
    assert client._get_auth_token() == "cached"

    # Past expiry the cache is ignored and the chain runs again.
    client._token_expiry = 0.0
    assert client._get_auth_token() == "fresh"


def test_the_metadata_server_is_used_on_cloud_run(monkeypatch, no_ambient_credentials):
    """Second in the chain: no env token, but running on GCE/Cloud Run."""
    seen = {}

    def _get(self, url, headers=None, **kwargs):
        seen["url"] = url
        seen["headers"] = headers
        return _response(200, {"access_token": "metadata-token", "expires_in": 1200})

    monkeypatch.setattr(httpx.Client, "get", _get)

    client = VertexGeminiClient()
    assert client._get_auth_token() == "metadata-token"
    assert "metadata.google.internal" in seen["url"]
    assert seen["headers"] == {"Metadata-Flavor": "Google"}
    # Expiry is shortened by a minute so a token is never used at the boundary.
    assert client._token_expiry < 1200 + __import__("time").time()


def test_a_metadata_response_without_a_token_falls_through(monkeypatch, no_ambient_credentials):
    monkeypatch.setattr(httpx.Client, "get", lambda *a, **k: _response(200, {"expires_in": 3600}))

    with pytest.raises(PermissionError):
        VertexGeminiClient()._get_auth_token()


def test_a_non_200_from_the_metadata_server_falls_through(monkeypatch, no_ambient_credentials):
    monkeypatch.setattr(httpx.Client, "get", lambda *a, **k: _response(404, text="nope"))

    with pytest.raises(PermissionError):
        VertexGeminiClient()._get_auth_token()


def test_gcloud_is_the_local_developer_fallback(monkeypatch, no_ambient_credentials):
    monkeypatch.setattr("src.integrations.vertex.client.shutil.which", lambda _: "/bin/gcloud")
    monkeypatch.setattr("src.integrations.vertex.client.os.path.isfile", lambda p: p == "/bin/gcloud")
    monkeypatch.setattr("src.integrations.vertex.client.os.access", lambda p, mode: True)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "adc-token\n", "")
    )

    assert VertexGeminiClient()._get_auth_token() == "adc-token"


def test_gcloud_warning_banners_are_not_mistaken_for_the_token(
    monkeypatch, no_ambient_credentials
):
    """`gcloud` prints advisories on stdout; the token is the last real line."""
    noisy = "WARNING: quota project not set\nIf you need to set it, run...\nya29.real-token\n"
    monkeypatch.setattr("src.integrations.vertex.client.shutil.which", lambda _: "/bin/gcloud")
    monkeypatch.setattr("src.integrations.vertex.client.os.path.isfile", lambda p: True)
    monkeypatch.setattr("src.integrations.vertex.client.os.access", lambda p, mode: True)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, noisy, ""))

    assert VertexGeminiClient()._get_auth_token() == "ya29.real-token"


def test_the_second_gcloud_subcommand_is_tried_when_the_first_fails(
    monkeypatch, no_ambient_credentials
):
    """ADC may be absent while a user credential is present."""
    calls = []

    def _run(cmd, **kwargs):
        calls.append(cmd[1:])
        if "application-default" in cmd:
            raise OSError("no ADC")
        return subprocess.CompletedProcess(cmd, 0, "user-token", "")

    monkeypatch.setattr("src.integrations.vertex.client.shutil.which", lambda _: "/bin/gcloud")
    monkeypatch.setattr("src.integrations.vertex.client.os.path.isfile", lambda p: True)
    monkeypatch.setattr("src.integrations.vertex.client.os.access", lambda p, mode: True)
    monkeypatch.setattr(subprocess, "run", _run)

    assert VertexGeminiClient()._get_auth_token() == "user-token"
    assert len(calls) == 2


def test_gcloud_output_that_is_only_banners_yields_no_token(monkeypatch, no_ambient_credentials):
    """Exit 0 with nothing but advisories is not a credential.

    The loop must move on to the next subcommand rather than caching the empty
    string as a token, which would then be sent as `Bearer ` on every call.
    """
    monkeypatch.setattr("src.integrations.vertex.client.shutil.which", lambda _: "/bin/gcloud")
    monkeypatch.setattr("src.integrations.vertex.client.os.path.isfile", lambda p: True)
    monkeypatch.setattr("src.integrations.vertex.client.os.access", lambda p, mode: True)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "WARNING: nope\n", "")
    )

    client = VertexGeminiClient()
    with pytest.raises(PermissionError):
        client._get_auth_token()
    assert client._cached_token is None


def test_a_nonzero_gcloud_exit_is_not_treated_as_a_token(monkeypatch, no_ambient_credentials):
    monkeypatch.setattr("src.integrations.vertex.client.shutil.which", lambda _: "/bin/gcloud")
    monkeypatch.setattr("src.integrations.vertex.client.os.path.isfile", lambda p: True)
    monkeypatch.setattr("src.integrations.vertex.client.os.access", lambda p, mode: True)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "not logged in")
    )

    with pytest.raises(PermissionError, match="Could not authenticate"):
        VertexGeminiClient()._get_auth_token()


def test_no_credentials_anywhere_is_a_clear_error(no_ambient_credentials):
    """The message names all three sources, because that is the fix."""
    with pytest.raises(PermissionError) as err:
        VertexGeminiClient()._get_auth_token()

    message = str(err.value)
    assert "ADC" in message and "Metadata Server" in message and "VERTEX_AI_TOKEN" in message


# --- structured generation ---------------------------------------------------


def test_a_structured_response_is_validated_into_the_model(client, monkeypatch):
    monkeypatch.setattr(client._http_client, "post", lambda *a, **k: _ok())

    decision = client.generate_structured("q", "sys", SupervisorRoutingDecision)

    assert isinstance(decision, SupervisorRoutingDecision)
    assert decision.intent == "UC_1_1_POLICY_QA"


def test_the_request_carries_the_schema_the_prompt_and_the_token(client, monkeypatch):
    sent = {}

    def _post(url, json=None, headers=None):
        sent.update(url=url, payload=json, headers=headers)
        return _ok()

    monkeypatch.setattr(client._http_client, "post", _post)
    client.generate_structured("how much leave", "you are a router", SupervisorRoutingDecision)

    assert sent["headers"]["Authorization"] == "Bearer test-token"
    assert "us-central1-aiplatform.googleapis.com" in sent["url"]
    assert sent["payload"]["contents"][0]["parts"][0]["text"] == "how much leave"
    assert sent["payload"]["systemInstruction"]["parts"][0]["text"] == "you are a router"
    assert sent["payload"]["generationConfig"]["responseMimeType"] == "application/json"


def test_a_404_falls_back_to_the_next_candidate_model(monkeypatch):
    """`gemini-3.7-flash` is not available in every project; 2.5 is the backstop."""
    monkeypatch.setenv("VERTEX_AI_TOKEN", "t")
    client = VertexGeminiClient(project_id="p", model_id="gemini-3.7-flash")
    urls = []

    def _post(url, json=None, headers=None):
        urls.append(url)
        return _response(404, text="not found") if len(urls) == 1 else _ok()

    monkeypatch.setattr(client._http_client, "post", _post)
    assert client.generate_structured("q", "s", SupervisorRoutingDecision).confidence == 0.95

    assert "gemini-3.7-flash" in urls[0]
    assert "/locations/global/" in urls[0]
    assert "gemini-2.5-flash" in urls[1]


def test_the_thinking_budget_is_disabled_only_for_the_3_7_router(monkeypatch):
    """Routing is a latency-critical classification, not a reasoning task (NFR-2.1)."""
    monkeypatch.setenv("VERTEX_AI_TOKEN", "t")
    payloads = []

    def _capture(client):
        monkeypatch.setattr(
            client._http_client, "post", lambda url, json=None, headers=None: (payloads.append(json), _ok())[1]
        )

    fast = VertexGeminiClient(project_id="p", model_id="gemini-3.7-flash")
    _capture(fast)
    fast.generate_structured("q", "s", SupervisorRoutingDecision)

    other = VertexGeminiClient(project_id="p", model_id="gemini-2.5-flash")
    _capture(other)
    other.generate_structured("q", "s", SupervisorRoutingDecision)

    assert payloads[0]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert "thinkingConfig" not in payloads[1]["generationConfig"]


def test_a_persistent_error_is_raised_rather_than_swallowed(client, monkeypatch):
    monkeypatch.setattr(client._http_client, "post", lambda *a, **k: _response(403, text="denied"))

    with pytest.raises(RuntimeError, match="403"):
        client.generate_structured("q", "s", SupervisorRoutingDecision)


def test_a_last_candidate_404_is_an_error_not_a_silent_none(client, monkeypatch):
    """The fallback `continue` must not run off the end of the candidate list."""
    monkeypatch.setattr(client._http_client, "post", lambda *a, **k: _response(404, text="gone"))

    with pytest.raises(RuntimeError):
        client.generate_structured("q", "s", SupervisorRoutingDecision)


def test_a_malformed_body_surfaces_as_an_error(client, monkeypatch):
    monkeypatch.setattr(client._http_client, "post", lambda *a, **k: _ok("this is not json"))

    with pytest.raises(json.JSONDecodeError):
        client.generate_structured("q", "s", SupervisorRoutingDecision)


def test_the_schema_is_stripped_of_keys_vertex_rejects(client):
    schema = {
        "$defs": {"Nested": {}},
        "title": "SupervisorRoutingDecision",
        "description": "docstring",
        "type": "object",
        "properties": {"intent": {"type": "string"}},
    }

    cleaned = client._clean_schema(schema)

    assert set(cleaned) == {"type", "properties"}
    # The input is not mutated - the caller may still need the full schema.
    assert "$defs" in schema


# --- the two routing entry points --------------------------------------------


def test_routing_pins_the_reference_date_into_the_prompt(client, monkeypatch):
    """Relative dates ("next Monday") are meaningless without an anchor."""
    sent = {}
    monkeypatch.setattr(
        client._http_client,
        "post",
        lambda url, json=None, headers=None: (sent.update(payload=json), _ok())[1],
    )

    _REAL_ROUTE_INTENT(client, "book leave next Monday", datetime.date(2026, 8, 27))

    assert "[Reference Today: 2026-08-27]" in sent["payload"]["contents"][0]["parts"][0]["text"]
    instruction = sent["payload"]["systemInstruction"]["parts"][0]["text"]
    assert "2026-08-27" in instruction
    assert "Thursday" in instruction


def test_tool_selection_forbids_backdating(client, monkeypatch):
    sent = {}
    body = json.dumps(
        {"tool_name": "get_employee_balances", "reasoning": "balance lookup"}
    )
    monkeypatch.setattr(
        client._http_client,
        "post",
        lambda url, json=None, headers=None: (sent.update(payload=json), _ok(body))[1],
    )

    selection = _REAL_SELECT_TOOL(client, "what is my balance", datetime.date(2026, 8, 27))

    assert selection.tool_name == "get_employee_balances"
    assert "MUST NEVER be submitted for dates in the past" in (
        sent["payload"]["systemInstruction"]["parts"][0]["text"]
    )


def test_the_reference_date_defaults_to_the_business_today(client, monkeypatch):
    """Asia/Singapore, not the host clock - see src/core/clock.py."""
    sent = {}
    monkeypatch.setattr(
        client._http_client,
        "post",
        lambda url, json=None, headers=None: (sent.update(payload=json), _ok())[1],
    )
    monkeypatch.setattr(
        "src.integrations.vertex.client.business_today", lambda: datetime.date(2026, 1, 2)
    )

    _REAL_ROUTE_INTENT(client, "book leave tomorrow")

    assert "2026-01-02" in sent["payload"]["contents"][0]["parts"][0]["text"]
