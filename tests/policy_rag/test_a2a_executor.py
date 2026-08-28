"""The executor's request parsing, seen from below the JSON-RPC layer.

`test_a2a.py` drives the same executor over a real transport, which is the right
place to prove the protocol works. It is the wrong place to prove what happens
to a malformed JSON data part or a request that carries no message at all: the
client would have to be persuaded to send something no client sends. These tests
call the module functions directly with hand-built `RequestContext` objects, so
the parsing rules - which part is the question, which slot may carry parameters,
and which slot may never carry entitlements - are checked one at a time.
"""

from __future__ import annotations

import pytest
from a2a.server.agent_execution import RequestContext
from a2a.server.context import ServerCallContext
from a2a.server.events import EventQueue
from a2a.types import Message, Part, SendMessageRequest, Task, TaskState
from google.protobuf import struct_pb2

from src.grounding.policy_rag.a2a_app.executor import (
    ENTITLEMENTS_HEADER,
    TRUST_PAYLOAD_ENTITLEMENTS_ENV,
    PolicyRagExecutor,
    _as_str_list,
    _as_top_k,
    _payload_from_message,
    _question_from_message,
    data_part,
    resolve_entitlements,
)
from src.grounding.policy_rag.config import GENERAL_ENTITLEMENT
from src.grounding.policy_rag.retriever import RetrievalResult

ROLE_USER = 1


def _context(
    *,
    parts: list[Part] | None = None,
    message_metadata: dict | None = None,
    params_metadata: dict | None = None,
    headers: dict[str, str] | None = None,
    task: Task | None = None,
) -> RequestContext:
    """A `RequestContext` carrying a message, as the server would build one."""
    message = Message(message_id="msg-1", role=ROLE_USER, parts=parts or [])
    if message_metadata is not None:
        message.metadata.update(message_metadata)
    request = SendMessageRequest(message=message)
    if params_metadata is not None:
        request.metadata.update(params_metadata)
    call_context = ServerCallContext(state={"headers": headers}) if headers is not None else None
    return RequestContext(
        call_context=call_context, request=request, task_id="task-1", context_id="ctx-1", task=task
    )


def _empty_context(*, headers: dict[str, str] | None = None) -> RequestContext:
    """A context with no message at all - the shape a bare task poll arrives in."""
    call_context = ServerCallContext(state={"headers": headers}) if headers is not None else None
    return RequestContext(call_context=call_context, task_id="task-1", context_id="ctx-1")


# --- where parameters may come from -------------------------------------------


def test_parameters_are_merged_from_every_slot_the_spec_offers():
    """A data part, a JSON text part and both metadata slots, in that order of
    precedence: the params envelope is the outermost, so it wins a collision."""
    context = _context(
        parts=[
            Part(text="how much vacation leave do I accrue"),
            data_part({"top_k": 3, "corpora": ["okf-handbook"]}),
            Part(text='{"doc_types": ["policy"]}', media_type="application/json"),
        ],
        message_metadata={"skill": "policy_search", "top_k": 5},
        params_metadata={"top_k": 9},
    )

    payload = _payload_from_message(context)

    assert payload["corpora"] == ["okf-handbook"]
    assert payload["doc_types"] == ["policy"]
    assert payload["skill"] == "policy_search"
    assert payload["top_k"] == 9


def test_a_request_with_no_message_has_no_parameters():
    assert _payload_from_message(_empty_context()) == {}


def test_a_data_part_that_is_not_an_object_is_ignored():
    """`Value` also encodes arrays and scalars; only an object is a parameter set."""
    context = _context(parts=[data_part(["okf-handbook"]), data_part({"top_k": 3})])

    assert _payload_from_message(context) == {"top_k": 3}


def test_a_malformed_json_text_part_is_skipped_rather_than_fatal():
    """An agent-to-agent caller may well be an LLM emitting near-JSON. Dropping
    the part costs a parameter; raising would cost the whole question."""
    context = _context(
        parts=[
            Part(text='{"top_k": 3,', media_type="application/json"),
            Part(text='{"doc_types": ["policy"]}', media_type="application/json"),
        ]
    )

    assert _payload_from_message(context) == {"doc_types": ["policy"]}


def test_a_json_text_part_that_is_not_an_object_is_ignored():
    context = _context(parts=[Part(text="[1, 2, 3]", media_type="application/json")])

    assert _payload_from_message(context) == {}


class _StubMessage:
    """A message whose metadata does not deserialise to a mapping.

    `Message.metadata` is a protobuf `Struct`, so this cannot be built from the
    real type - which is exactly why the guard in `_payload_from_message` is
    worth keeping and why it has to be reached this way.
    """

    parts: tuple = ()
    metadata = struct_pb2.Value(string_value="hr_operational")

    def HasField(self, field: str) -> bool:
        return field == "metadata"


class _StubContext:
    def __init__(self, *, message=None, metadata=None) -> None:
        self.message = message
        self.metadata = metadata


def test_message_metadata_that_is_not_a_mapping_is_ignored():
    payload = _payload_from_message(_StubContext(message=_StubMessage(), metadata={"skill": "policy_search"}))

    assert payload == {"skill": "policy_search"}


def test_params_metadata_that_is_not_a_mapping_is_ignored():
    """Defensive in the same way, and for the same reason: whatever the caller
    put there is not a parameter set, and guessing at it would be worse."""
    assert _payload_from_message(_StubContext(metadata="skill=policy_search")) == {}


# --- what counts as the question ----------------------------------------------


def test_the_question_is_the_plain_text_parts_joined():
    """A JSON text part is a parameter set, not prose; folding it into the
    question would embed a config blob in the retrieval query."""
    context = _context(
        parts=[
            Part(text="  how much vacation leave  "),
            Part(text='{"top_k": 3}', media_type="application/json"),
            Part(text="   "),
            Part(text="do I accrue per year?"),
            data_part({"skill": "policy_answer"}),
        ]
    )

    assert _question_from_message(context, {}) == "how much vacation leave\ndo I accrue per year?"


def test_a_question_can_arrive_as_a_parameter_instead_of_a_text_part():
    """A programmatic caller may send parameters only. Both spellings are
    accepted because the card documents `query` and callers write `question`."""
    assert _question_from_message(_empty_context(), {"query": "  vacation leave  "}) == "vacation leave"
    assert _question_from_message(_empty_context(), {"question": "sick leave"}) == "sick leave"
    assert _question_from_message(_empty_context(), {}) == ""


# --- the entitlement trust boundary (SDD §4.1) --------------------------------


def test_entitlements_are_read_from_the_transport_header():
    context = _context(headers={"X-Altostrat-Entitlements": "hr_operational, general"})

    assert resolve_entitlements(context, {}) == ["hr_operational", "general"]


def test_a_request_with_no_call_context_still_holds_the_general_entitlement():
    """There is no transport to read a header from - a direct in-process call, or
    a poll. That is not a reason to grant nothing, and not a reason to grant more."""
    assert resolve_entitlements(_empty_context(), {}) == [GENERAL_ENTITLEMENT]


def test_payload_entitlements_are_ignored_and_the_attempt_is_logged(caplog):
    context = _context(headers={})

    with caplog.at_level("WARNING", logger="src.grounding.policy_rag.a2a_app.executor"):
        entitlements = resolve_entitlements(context, {"entitlements": ["hr_operational"]})

    assert entitlements == [GENERAL_ENTITLEMENT]
    assert "ignoring caller-supplied entitlements" in caplog.text


def test_the_development_escape_hatch_trusts_the_payload(monkeypatch):
    """For a server run with no gateway in front. It is opt-in per process and
    never reachable from the message itself."""
    monkeypatch.setenv(TRUST_PAYLOAD_ENTITLEMENTS_ENV, "1")

    entitlements = resolve_entitlements(_empty_context(), {"entitlements": ["hr_operational"]})

    assert entitlements == ["hr_operational", GENERAL_ENTITLEMENT]


def test_the_escape_hatch_still_requires_a_list(monkeypatch):
    monkeypatch.setenv(TRUST_PAYLOAD_ENTITLEMENTS_ENV, "1")

    assert resolve_entitlements(_empty_context(), {"entitlements": "hr_operational"}) == [GENERAL_ENTITLEMENT]


def test_the_general_entitlement_is_not_duplicated():
    context = _context(headers={ENTITLEMENTS_HEADER: "general"})

    assert resolve_entitlements(context, {}) == [GENERAL_ENTITLEMENT]


# --- filter coercion ----------------------------------------------------------


def test_top_k_survives_the_json_number_round_trip():
    """The regression this exists for: a protobuf `Struct` has one number type,
    so `{"top_k": 5}` reaches the executor as `5.0`. An integer-only check reads
    that as "no value" and silently returns the default result count instead."""
    assert _as_top_k(5.0) == 5
    assert _as_top_k(5) == 5
    assert _as_top_k("5") == 5


def test_a_top_k_that_is_not_a_usable_count_falls_back_to_the_default():
    assert _as_top_k(None) is None
    assert _as_top_k(0) is None
    assert _as_top_k(-3) is None
    assert _as_top_k(True) is None
    assert _as_top_k("all of them") is None
    assert _as_top_k(["5"]) is None


def test_a_single_filter_value_may_be_sent_as_a_bare_string():
    assert _as_str_list("okf-handbook") == ["okf-handbook"]
    assert _as_str_list(["okf-handbook", "handbook-source"]) == ["okf-handbook", "handbook-source"]


def test_an_absent_or_unusable_filter_means_no_filter():
    """`None` is "unfiltered". So is a number: narrowing on a value the retriever
    cannot match would silently return nothing instead of everything."""
    assert _as_str_list(None) is None
    assert _as_str_list(7) is None


# --- task lifecycle -----------------------------------------------------------


class _RecordingQueue(EventQueue):
    """The producer half of the event queue, kept so the events can be read back."""

    def __init__(self) -> None:
        self.events: list = []

    async def enqueue_event(self, event) -> None:
        self.events.append(event)


@pytest.fixture
def executor(service) -> PolicyRagExecutor:
    return PolicyRagExecutor(service)


async def test_a_fresh_request_publishes_the_task_before_any_status_update():
    """The server rejects a status update for a task it has never seen, so the
    ordering here is a protocol requirement rather than a preference."""
    queue = _RecordingQueue()

    await PolicyRagExecutor._begin(_context(parts=[Part(text="vacation leave")]), queue)

    assert [type(e).__name__ for e in queue.events] == ["Task", "TaskStatusUpdateEvent"]
    task = queue.events[0]
    assert (task.id, task.context_id) == ("task-1", "ctx-1")
    assert len(task.history) == 1


async def test_a_follow_up_message_does_not_re_enqueue_the_task():
    """Re-enqueueing an existing task is ignored with an error log, which turns a
    multi-turn conversation into a stream of noise."""
    queue = _RecordingQueue()
    existing = Task(id="task-1", context_id="ctx-1")

    await PolicyRagExecutor._begin(_context(parts=[Part(text="and for a contractor?")], task=existing), queue)

    assert [type(e).__name__ for e in queue.events] == ["TaskStatusUpdateEvent"]


async def test_cancelling_publishes_a_cancelled_status(executor):
    queue = _RecordingQueue()

    await executor.cancel(_empty_context(), queue)

    assert queue.events[0].status.state == TaskState.TASK_STATE_CANCELED


# --- rendering ----------------------------------------------------------------


def test_a_search_that_clears_nothing_reports_the_gate_it_missed():
    """The number is the point: "no results" leaves a caller unable to tell a
    corpus gap from a gate set too high."""
    result = RetrievalResult(
        query="how do I expense a hot air balloon",
        hits=[],
        rejected=[],
        gate=0.8,
        best_relevance=0.4213,
        searched_corpora=["okf-handbook"],
    )

    text = PolicyRagExecutor._render_search(result)

    assert "No passage cleared the relevance gate (0.8)" in text
    assert "0.421" in text
