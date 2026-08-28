"""Which ServiceImmediately tool a question earns when Gemini is unreachable.

`select_itsm_tool` asks Vertex first and falls back to `_fallback_select_itsm_tool`
on any failure. The fallback is therefore not a nicety: it is what runs during an
outage, during a quota block, and throughout this test suite, which has no Vertex
access at all. Every ITSM turn in CI is routed by the code under test here.

The stakes are asymmetric and that shapes what is asserted. Routing a read to
`create_incident` files a ticket nobody asked for, and an IT queue that fills
with phantom tickets stops being triaged. Routing a create to `list_tickets`
merely fails to help. So the tests lean on the read side: several of them are
ordinary phrasings of "what have I got open", each of which must not write.
"""

from __future__ import annotations

import pytest

from src.integrations.vertex.client import VertexGeminiClient

# Captured at import, which happens at collection - before the autouse fixture in
# `conftest.py` swaps `select_itsm_tool` out for the offline mock. Everywhere else
# that swap is what makes the suite deterministic; the one test below is about the
# live method's own error handling, so it needs the original back.
_REAL_SELECT_ITSM_TOOL = VertexGeminiClient.select_itsm_tool


@pytest.fixture(scope="module")
def select():
    """The fallback alone - no Vertex call, no network, no credentials."""
    client = VertexGeminiClient.__new__(VertexGeminiClient)
    return client._fallback_select_itsm_tool


# --- a stated reference settles it -------------------------------------------


@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("what is the status of INC-5001", "INC-5001"),
        ("what is the status of inc-5001?", "INC-5001"),
        ("any news on (inc-5001)?", "INC-5001"),
        ("checking on 'INC-5001'.", "INC-5001"),
        ("INC_5001 update please", "INC_5001"),
        ("please look at INC0003466", "INC0003466"),
    ],
)
def test_a_ticket_reference_is_lifted_out_of_the_surrounding_prose(select, prompt, expected):
    """Punctuation is how people actually write these, and it must come off."""
    selection = select(prompt)

    assert selection.tool_name == "get_ticket_details"
    assert selection.ticket_id == expected


def test_a_reference_wins_even_when_the_sentence_also_asks_to_open_something(select):
    """Naming a ticket is the least ambiguous thing a caller can do."""
    assert select("open a ticket like INC-5001").tool_name == "get_ticket_details"


@pytest.mark.parametrize("prompt", ["INC-12", "INC-123456789", "the incident number"])
def test_something_that_only_looks_like_a_reference_is_not_treated_as_one(select, prompt):
    """Three to eight digits. `INC-12` is a typo, not a ticket, and looking it
    up would report "not found" instead of helping."""
    assert select(prompt).tool_name != "get_ticket_details"


# --- reads must not write -----------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        "any open tickets for me?",
        "do I have any tickets?",
        "list my tickets",
        "show my tickets",
        "what are my active tickets",
        "all tickets please",
        "what is the status of my ticket?",
        "any news on my incident?",
        "check my open incidents",
        "what is the progress on my ticket",
        "outstanding tickets",
        "current tickets for me",
    ],
)
def test_a_question_about_tickets_is_never_answered_by_filing_one(select, prompt):
    """The bug this module exists for.

    "any open tickets for me?" matched none of the original list phrasings, so
    it fell through to the default and filed a ticket in answer to a question
    about tickets. The employee gets a phantom INC in their name and no answer.
    """
    assert select(prompt).tool_name == "list_tickets"


def test_a_read_with_no_reference_does_not_invent_one(select):
    """It used to answer with a hardcoded INC-5001.

    That is worse than unhelpful. The caller asked about *their* ticket and was
    shown a record they never named - one that belongs to the demo seed, and in
    deployment could belong to somebody else entirely.
    """
    selection = select("what is the status of my ticket?")

    assert selection.tool_name == "list_tickets"
    assert selection.ticket_id is None


# --- writes must still write --------------------------------------------------


@pytest.mark.parametrize(
    "prompt",
    [
        "open a ticket for my vpn",
        "create a ticket",
        "raise a ticket about the printer",
        "file a ticket please",
        "log a ticket for me",
        "submit a ticket",
        "I need a new ticket",
        "report a problem with my monitor",
    ],
)
def test_an_instruction_to_raise_something_new_still_creates(select, prompt):
    """`open a ticket` and `open tickets` differ by one letter and mean opposite
    things, which is why create is decided before the read intents."""
    assert select(prompt).tool_name == "create_incident"


@pytest.mark.parametrize(
    ("prompt", "category"),
    [
        ("my VPN keeps dropping", "IT_NETWORK"),
        ("the office wifi will not authenticate", "IT_NETWORK"),
        ("no internet on my desk", "IT_NETWORK"),
        ("my laptop will not boot", "IT_HARDWARE"),
        ("second monitor is dead", "IT_HARDWARE"),
        ("I cannot get access to the github org", "IT_ACCESS"),
        ("password reset please", "IT_ACCESS"),
        ("the coffee machine is sentient", "IT_GENERAL"),
    ],
)
def test_a_described_problem_is_filed_under_the_queue_that_handles_it(select, prompt, category):
    selection = select(prompt)

    assert selection.tool_name == "create_incident"
    assert selection.category == category
    assert selection.priority == "3 - Moderate"


def test_a_read_verb_about_something_that_is_not_a_ticket_still_creates(select):
    """"check" is a read verb, but this caller is reporting a fault, not asking
    after a ticket. Requiring the word "ticket" is what keeps the two apart."""
    selection = select("my screen is cracked, can you check")

    assert selection.tool_name == "create_incident"
    assert selection.category == "IT_HARDWARE"


def test_a_long_complaint_is_truncated_before_it_becomes_a_title(select):
    """`short_description` is a ticket title, and the queue view truncates it
    anyway - better to cut it here than to store a screenful."""
    selection = select("x" * 300)

    assert len(selection.short_description) == 100


# --- the live path falls back rather than failing -----------------------------


def test_an_unreachable_vertex_falls_back_instead_of_raising(monkeypatch, caplog):
    """An ITSM outage must not become an agent outage. The whole suite depends
    on this path, so it is asserted rather than assumed."""
    client = VertexGeminiClient.__new__(VertexGeminiClient)

    def _unreachable(**kwargs):
        raise RuntimeError("403 PERMISSION_DENIED")

    monkeypatch.setattr(client, "generate_structured", _unreachable)

    with caplog.at_level("WARNING", logger="integrations.vertex"):
        selection = _REAL_SELECT_ITSM_TOOL(client, "any open tickets for me?")

    assert selection.tool_name == "list_tickets"
    assert "deterministic local fallback" in caplog.text
