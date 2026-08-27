"""A2A surface: agent card discovery, skill dispatch, and the entitlement boundary.

The server is exercised in-process over httpx's ASGI transport, so these are
real JSON-RPC round trips with no port bound and no network.
"""

from __future__ import annotations

import json

import copy

import httpx
import pytest

from src.grounding.policy_rag.a2a_app.card import (
    AGENT_NAME,
    SKILL_CORPUS_STATUS,
    SKILL_POLICY_ANSWER,
    SKILL_POLICY_SEARCH,
)
from src.grounding.policy_rag.a2a_app.executor import ENTITLEMENTS_HEADER
from src.grounding.policy_rag.a2a_app.server import build_app
from src.grounding.policy_rag.embeddings import build_provider
from src.grounding.policy_rag.service import PolicyRagService

CARD_PATH = "/.well-known/agent-card.json"


@pytest.fixture(scope="module")
def app(config, index):
    """The A2A app, served by a copy of the service with the gate opened.

    The gate has to come down for these tests to mean anything. Under the
    hermetic `hash` embedding provider no passage scores above ~0.35, so at the
    production gate of 0.80 every search returns zero hits - and an assertion
    that no `references/` path leaked would pass without the ACL filter ever
    running. Opening the gate is what makes the entitlement and citation
    assertions below load-bearing. It is a property of the *fixture corpus*, not
    of the server: `build_app` is handed the same executor either way, and the
    gate itself is covered against a real model by `scripts/eval_retrieval.py`.
    """
    open_gate = copy.deepcopy(config)
    open_gate.retrieval.relevance_gate = 0.0
    ungated = PolicyRagService(open_gate, index, build_provider(open_gate.embedding))
    return build_app(service=ungated, public_url="http://testserver")


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


def rpc(question: str, *, skill: str, **params) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": "test-1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": "msg-1",
                "parts": [{"text": question}],
                "metadata": {"skill": skill, **params},
            }
        },
    }


def artifact_payloads(body: dict) -> tuple[list[str], list[dict]]:
    """Pull text and JSON data parts out of a JSON-RPC message/send response."""
    result = body.get("result") or {}
    texts: list[str] = []
    payloads: list[dict] = []
    for artifact in result.get("artifacts", []):
        for part in artifact.get("parts", []):
            if "data" in part:
                payloads.append(part["data"])
            elif part.get("text"):
                texts.append(part["text"])
    return texts, payloads


# --- discovery ----------------------------------------------------------------


async def test_agent_card_is_discoverable(client):
    response = await client.get(CARD_PATH)
    assert response.status_code == 200
    card = response.json()
    assert card["name"] == AGENT_NAME
    skill_ids = {s["id"] for s in card["skills"]}
    assert skill_ids == {SKILL_POLICY_SEARCH, SKILL_POLICY_ANSWER, SKILL_CORPUS_STATUS}


async def test_card_advertises_a_reachable_interface(client):
    """A consuming agent has to learn the endpoint from the card alone."""
    card = (await client.get(CARD_PATH)).json()
    interfaces = card.get("supportedInterfaces") or []
    assert interfaces
    assert any(i.get("url") for i in interfaces)
    assert {i.get("protocolBinding") for i in interfaces} >= {"JSONRPC"}


async def test_healthz(client):
    response = await client.get("/healthz")
    assert response.status_code == 200


# --- skills -------------------------------------------------------------------


async def test_policy_answer_returns_text_and_structured_parts(client):
    response = await client.post("/", json=rpc("vacation leave accrual", skill=SKILL_POLICY_ANSWER))
    assert response.status_code == 200
    texts, payloads = artifact_payloads(response.json())
    assert texts, "an artifact must carry a human-readable text part"
    assert payloads, "an artifact must carry a machine-readable data part"
    body = payloads[0]
    assert body["skill"] == SKILL_POLICY_ANSWER
    assert body["decision"] in {"ANSWER", "ESCALATE", "REFUSE"}


async def test_policy_search_returns_chunks_without_composing_prose(client):
    response = await client.post("/", json=rpc("vacation leave accrual", skill=SKILL_POLICY_SEARCH))
    _, payloads = artifact_payloads(response.json())
    body = payloads[0]
    assert body["skill"] == SKILL_POLICY_SEARCH
    assert "hits" in body
    assert "answer" not in body


async def test_corpus_status_reports_provenance(client):
    response = await client.post("/", json=rpc("", skill=SKILL_CORPUS_STATUS))
    _, payloads = artifact_payloads(response.json())
    body = payloads[0]
    assert body["skill"] == SKILL_CORPUS_STATUS
    assert body["chunks"] > 0
    assert body["manifest"]["embedder_fingerprint"]


async def test_empty_question_refuses_cleanly(client):
    response = await client.post("/", json=rpc("   ", skill=SKILL_POLICY_ANSWER))
    _, payloads = artifact_payloads(response.json())
    assert payloads[0]["reason"] == "empty_query"


async def test_unknown_skill_falls_back_to_policy_answer(client):
    response = await client.post("/", json=rpc("vacation leave", skill="not_a_skill"))
    _, payloads = artifact_payloads(response.json())
    assert payloads[0]["skill"] == SKILL_POLICY_ANSWER


# --- guards survive the protocol boundary --------------------------------------


async def test_extended_workforce_guard_is_enforced_over_a2a(client):
    response = await client.post(
        "/", json=rpc("I am a contractor, how much annual leave do I get?", skill=SKILL_POLICY_ANSWER)
    )
    _, payloads = artifact_payloads(response.json())
    assert payloads[0]["decision"] == "ESCALATE"
    assert payloads[0]["reason"] == "extended_workforce_leave"


# --- the entitlement trust boundary (SDD §4.1 / §4.7) --------------------------


async def test_entitlements_in_the_payload_are_ignored(client):
    """A caller must not be able to grant itself an entitlement by asking."""
    response = await client.post(
        "/",
        json=rpc(
            "source defect register",
            skill=SKILL_POLICY_SEARCH,
            entitlements=["hr_operational"],
            top_k=20,
        ),
    )
    _, payloads = artifact_payloads(response.json())
    paths = [h["path"] for h in payloads[0]["hits"]]
    assert not any("references/" in p for p in paths), "payload entitlements must not be honoured"


async def test_entitlements_from_the_header_are_honoured(client):
    response = await client.post(
        "/",
        json=rpc("source defect register conflicts", skill=SKILL_POLICY_SEARCH, top_k=20, doc_types=["reference"]),
        headers={ENTITLEMENTS_HEADER: "general,hr_operational"},
    )
    _, payloads = artifact_payloads(response.json())
    paths = [h["path"] for h in payloads[0]["hits"]]
    assert any("references/" in p for p in paths), "header entitlements must reach the retriever"


async def test_absent_header_defaults_to_general_only(client):
    response = await client.post(
        "/", json=rpc("source defect register conflicts", skill=SKILL_POLICY_SEARCH, top_k=20)
    )
    _, payloads = artifact_payloads(response.json())
    paths = [h["path"] for h in payloads[0]["hits"]]
    assert not any("references/" in p for p in paths)


# --- citations cross the boundary intact ----------------------------------------


async def test_hits_carry_resolvable_citations_over_the_wire(client):
    response = await client.post("/", json=rpc("vacation leave accrual", skill=SKILL_POLICY_SEARCH, top_k=5))
    _, payloads = artifact_payloads(response.json())
    for hit in payloads[0]["hits"]:
        assert hit["citation"]["uri"]
        assert hit["citation"]["resolved"] is True


async def test_response_is_json_serialisable(client):
    response = await client.post("/", json=rpc("vacation leave accrual", skill=SKILL_POLICY_ANSWER))
    json.dumps(response.json())
