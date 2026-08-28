"""The reference consumer, driven against the real server in-process.

`client_demo` is documentation that runs: it is the shape the Policy Specialist
of SDD §3.2 uses to reach this knowledge base. Documentation that runs is only
worth anything if it is run, so these tests point it at the actual A2A app over
httpx's ASGI transport - card discovery, JSON-RPC call and artifact parsing all
happen for real, with no port bound.
"""

from __future__ import annotations

import copy

import httpx
import pytest
from a2a.types import Artifact, Message, Part, Role, StreamResponse, Task, TaskArtifactUpdateEvent

from src.grounding.policy_rag.a2a_app import client_demo
from src.grounding.policy_rag.a2a_app.card import SKILL_CORPUS_STATUS, SKILL_POLICY_ANSWER, SKILL_POLICY_SEARCH
from src.grounding.policy_rag.a2a_app.executor import ENTITLEMENTS_HEADER, data_part
from src.grounding.policy_rag.a2a_app.server import build_app
from src.grounding.policy_rag.embeddings import build_provider
from src.grounding.policy_rag.service import PolicyRagService

BASE_URL = "http://testserver"


@pytest.fixture(scope="module")
def app(config, index):
    """The same open-gate app `test_a2a.py` builds, for the same reason: under the
    hash embedder nothing clears the production gate, so a hit assertion would
    pass without the retrieval path ever running."""
    open_gate = copy.deepcopy(config)
    open_gate.retrieval.relevance_gate = 0.0
    ungated = PolicyRagService(open_gate, index, build_provider(open_gate.embedding))
    return build_app(service=ungated, public_url=BASE_URL)


@pytest.fixture
def in_process(app, monkeypatch):
    """Route the client's own `httpx.AsyncClient` at the ASGI app.

    `ask` constructs its client internally - that is part of what the demo
    demonstrates - so the transport is swapped underneath it rather than
    injected, which leaves the code under test unchanged.
    """
    sent: list[httpx.Headers] = []

    class _Recording(httpx.ASGITransport):
        async def handle_async_request(self, request):
            sent.append(request.headers)
            return await super().handle_async_request(request)

    real_client = httpx.AsyncClient

    def _client(**kwargs):
        return real_client(transport=_Recording(app=app), **kwargs)

    monkeypatch.setattr(client_demo.httpx, "AsyncClient", _client)
    return sent


# --- round trip ---------------------------------------------------------------


async def test_the_demo_client_asks_a_question_and_reads_both_parts(in_process):
    texts, payloads = await client_demo.ask(BASE_URL, "vacation leave accrual")

    assert texts, "the artifact's human-readable part must reach the caller"
    assert payloads[0]["skill"] == SKILL_POLICY_ANSWER
    assert payloads[0]["decision"] in {"ANSWER", "ESCALATE", "REFUSE"}


async def test_the_skill_and_top_k_travel_in_the_message_metadata(in_process):
    _texts, payloads = await client_demo.ask(
        BASE_URL, "vacation leave accrual", skill=SKILL_POLICY_SEARCH, top_k=3
    )

    assert payloads[0]["skill"] == SKILL_POLICY_SEARCH
    assert len(payloads[0]["hits"]) <= 3


async def test_entitlements_are_sent_as_a_header_not_in_the_body(in_process):
    """The whole trust boundary rests on this: a client that put them in the
    payload would be silently downgraded to `general` by the server."""
    _texts, payloads = await client_demo.ask(
        BASE_URL,
        "source defect register conflicts",
        skill=SKILL_POLICY_SEARCH,
        entitlements=["general", "hr_operational"],
        top_k=20,
    )

    assert any(ENTITLEMENTS_HEADER in h for h in in_process)
    assert all("entitlements" not in (h.get("content-type") or "") for h in in_process)
    assert any("references/" in hit["path"] for hit in payloads[0]["hits"])


async def test_a_question_is_optional_for_the_status_skill(in_process):
    _texts, payloads = await client_demo.ask(BASE_URL, "", skill=SKILL_CORPUS_STATUS)

    assert payloads[0]["chunks"] > 0


# --- artifact parsing ---------------------------------------------------------
#
# The server answers a non-streaming call with a Task. The other two response
# shapes are what a streaming server sends, and are parsed here directly rather
# than by standing up a second server to emit them.


def _artifact(*parts: Part) -> Artifact:
    return Artifact(artifact_id="a-1", name="policy-rag-result", parts=list(parts))


def test_a_streamed_artifact_update_is_read_like_a_task_artifact():
    response = StreamResponse(
        artifact_update=TaskArtifactUpdateEvent(
            task_id="t-1",
            context_id="c-1",
            artifact=_artifact(Part(text="Fourteen days."), data_part({"decision": "ANSWER"})),
        )
    )

    texts, payloads = client_demo._artifact_payloads(response)

    assert texts == ["Fourteen days."]
    assert payloads == [{"decision": "ANSWER"}]


def test_a_bare_message_response_carries_text_and_no_payload():
    """A server may answer with a Message instead of a Task - no artifact, so
    there is nothing structured to read, and the prose must still come through."""
    response = StreamResponse(
        message=Message(message_id="m-1", role=Role.ROLE_AGENT, parts=[Part(text="Fourteen days."), Part(text="")])
    )

    assert client_demo._artifact_payloads(response) == (["Fourteen days."], [])


def test_a_data_part_that_is_not_an_object_is_not_a_payload():
    response = StreamResponse(
        task=Task(id="t-1", context_id="c-1", artifacts=[_artifact(data_part(["okf-handbook"]), Part(text=""))])
    )

    assert client_demo._artifact_payloads(response) == ([], [])


def test_a_status_only_response_yields_nothing():
    assert client_demo._artifact_payloads(StreamResponse()) == ([], [])


# --- the command line ---------------------------------------------------------


@pytest.fixture
def stub_ask(monkeypatch):
    """`main` is argument plumbing; the transport is covered above."""
    calls: list[dict] = []

    async def _ask(url, question, *, skill, entitlements, top_k):
        calls.append(
            {"url": url, "question": question, "skill": skill, "entitlements": entitlements, "top_k": top_k}
        )
        return ["Fourteen days."], [{"decision": "ANSWER"}]

    monkeypatch.setattr(client_demo, "ask", _ask)
    return calls


def test_the_cli_prints_the_prose_by_default(stub_ask, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["client_demo", "how much vacation leave"])

    assert client_demo.main() == 0

    assert capsys.readouterr().out.strip() == "Fourteen days."
    assert stub_ask[0] == {
        "url": "http://127.0.0.1:8080",
        "question": "how much vacation leave",
        "skill": SKILL_POLICY_ANSWER,
        "entitlements": None,
        "top_k": None,
    }


def test_the_cli_can_print_the_structured_part_instead(stub_ask, monkeypatch, capsys):
    """`--json` is what makes the demo usable from a shell pipeline."""
    monkeypatch.setattr(
        "sys.argv",
        [
            "client_demo",
            "source defect register",
            "--json",
            "--skill",
            SKILL_POLICY_SEARCH,
            "--entitlement",
            "hr_operational",
            "--top-k",
            "3",
        ],
    )

    assert client_demo.main() == 0

    assert capsys.readouterr().out.strip().startswith("[")
    assert stub_ask[0]["entitlements"] == ["hr_operational"]
    assert stub_ask[0]["top_k"] == 3
    assert stub_ask[0]["skill"] == SKILL_POLICY_SEARCH


def test_the_cli_refuses_a_skill_the_card_does_not_advertise(stub_ask, monkeypatch):
    """argparse exits 2 rather than sending a request the server would silently
    reinterpret as `policy_answer`."""
    monkeypatch.setattr("sys.argv", ["client_demo", "anything", "--skill", "not_a_skill"])

    with pytest.raises(SystemExit) as exit_info:
        client_demo.main()

    assert exit_info.value.code == 2
    assert stub_ask == []
