"""Answer composition and the generation half of the SDD §3.3 dual gate.

The extractive composer is the default because groundedness is 1.0 by
construction. The Gemini composer is the interesting one: it does not trust its
own grounding instruction, it *measures* the result and refuses below 0.85. The
tests below drive it against a stub client, so nothing here needs a network
call. It is the import guard in `__init__` that keeps `google-genai` optional,
and the tests exercise both sides of that guard explicitly rather than relying
on whether the package happens to be installed - it now is, transitively, via
google-adk.
"""

from __future__ import annotations

import sys
import types as pytypes
from types import SimpleNamespace

import pytest

from src.grounding.policy_rag.answer import (
    GROUNDEDNESS_GATE,
    REFUSAL_TEXT,
    Answer,
    ExtractiveComposer,
    GeminiComposer,
    build_composer,
    measure_groundedness,
)
from src.grounding.policy_rag.documents import Citation, Hit
from src.grounding.policy_rag.guards import PLACEHOLDER_REDACTION, GuardAction, GuardDecision
from src.grounding.policy_rag.retriever import RetrievalResult
from tests.policy_rag.conftest import make_chunk

VACATION_TEXT = "Employees accrue 14 days of paid vacation leave per year of continuous service."


def _hit(**overrides) -> Hit:
    chunk = make_chunk(**overrides)
    return Hit(
        chunk=chunk,
        dense_score=0.8,
        lexical_score=0.5,
        relevance=0.91,
        citation=Citation(title=chunk.doc_title, uri=f"{chunk.path}#{chunk.anchor}", resolved=True),
    )


def _result(hits: list[Hit], query: str = "how much vacation leave do I accrue") -> RetrievalResult:
    return RetrievalResult(
        query=query,
        hits=hits,
        rejected=[],
        gate=0.8,
        best_relevance=hits[0].relevance if hits else 0.0,
        searched_corpora=["okf-handbook"],
    )


# --- the answer envelope ------------------------------------------------------


def test_an_answer_serialises_for_the_response_envelope():
    answer = Answer(
        text="Fourteen days.",
        decision=GuardAction.ANSWER.value,
        citations=[Citation(title="Vacation Leave", uri="leave/vacation.md#accrual", resolved=True)],
        hits=[_hit()],
        relevance=0.912345,
        groundedness=1.0,
        notices=["check with People Ops"],
    )

    payload = answer.to_dict()

    assert payload["answer"] == "Fourteen days."
    assert payload["decision"] == "ANSWER"
    assert payload["relevance"] == 0.9123
    assert payload["composer"] == "extractive"
    assert payload["citations"][0]["uri"] == "leave/vacation.md#accrual"
    assert len(payload["chunks"]) == 1


def test_answered_and_action_track_the_guard_vocabulary():
    assert Answer(text="", decision=GuardAction.ANSWER.value).answered is True
    refused = Answer(text=REFUSAL_TEXT, decision=GuardAction.REFUSE.value)
    assert refused.answered is False
    assert refused.action == "REFUSE"


# --- extractive composition ---------------------------------------------------


def test_extraction_quotes_the_corpus_and_lists_its_sources(config):
    answer = ExtractiveComposer(config).compose(_result([_hit(text=VACATION_TEXT)]), GuardDecision())

    assert VACATION_TEXT in answer.text
    assert "**Sources**" in answer.text
    assert "- [Vacation Leave](okf/altostrat-sg-handbook/leave/vacation.md#accrual)" in answer.text
    assert answer.decision == "ANSWER"
    # Verbatim extraction cannot introduce an unsupported claim.
    assert answer.groundedness == 1.0
    assert answer.relevance == 0.91


def test_extraction_separates_passages_so_two_rules_do_not_read_as_one(config):
    hits = [_hit(text=VACATION_TEXT), _hit(chunk_id="1" * 16, doc_title="Sick Leave", text="Fourteen days sick.")]

    answer = ExtractiveComposer(config).compose(_result(hits), GuardDecision())

    assert "\n\n---\n\n" in answer.text
    assert answer.text.count("**Sources**") == 1
    assert len(answer.citations) == 2


def test_guard_notices_are_carried_into_the_answer(config):
    decision = GuardDecision(notices=["The handbook leaves part of this rule unspecified."])

    answer = ExtractiveComposer(config).compose(_result([_hit(text=VACATION_TEXT)]), decision)

    assert "**Please note**" in answer.text
    assert "leaves part of this rule unspecified" in answer.text


def test_a_placeholder_contact_is_redacted_and_flagged(config):
    """The datasheet names this one: `abc@altostrat.com` looks like a working
    address and is not one."""
    answer = ExtractiveComposer(config).compose(
        _result([_hit(text="Write to abc@altostrat.com for help with leave.")]), GuardDecision()
    )

    body, _, note = answer.text.partition("**Please note**")
    assert "abc@altostrat.com" not in body
    assert PLACEHOLDER_REDACTION in body
    # The notice quotes the placeholder deliberately - the caller is told the
    # address in the source is not real, rather than simply not shown it.
    assert "abc@altostrat.com" in note
    assert any("unresolved" in n for n in answer.notices)


def test_a_notice_with_no_hits_still_reaches_the_caller(config):
    """Guard notices survive an empty hit list. Without the citation block there
    is nothing else in the answer, and dropping the notice would leave a caller
    with a blank response and no reason for it."""
    decision = GuardDecision(notices=["Part of the retrieved material sits in a documented source conflict."])

    answer = ExtractiveComposer(config).compose(_result([]), decision)

    assert "**Sources**" not in answer.text
    assert answer.text.startswith("\n\n**Please note**")
    assert answer.relevance == 0.0
    assert answer.citations == []


# --- groundedness -------------------------------------------------------------


def test_groundedness_is_the_fraction_of_supported_content_words():
    hits = [_hit(text=VACATION_TEXT)]

    assert measure_groundedness("14 days of paid vacation leave", hits) == pytest.approx(1.0)
    assert measure_groundedness("14 days of paid sabbatical in Zurich", hits) < GROUNDEDNESS_GATE


# --- the Gemini composer ------------------------------------------------------


class _FakeModels:
    """`client.models`: records the call, then returns or raises what it is told."""

    def __init__(self) -> None:
        self.outcome: object = ""
        self.calls: list[SimpleNamespace] = []

    def generate_content(self, *, model, contents, config):
        self.calls.append(SimpleNamespace(model=model, contents=contents, config=config))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return SimpleNamespace(text=self.outcome)


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self.models = _FakeModels()


class _FakeGenerateContentConfig:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


@pytest.fixture
def genai_stub(monkeypatch):
    """Install a stand-in `google.genai` so the composer can be constructed.

    Patching `sys.modules` alone is not enough. `from google import genai`
    resolves as an attribute lookup on the already-imported `google` package,
    and the real `google-genai` sets that attribute the moment anything imports
    it - google-adk does. Without the `setattr` the composer would reach the
    real client, try to authenticate, and fail on absent credentials.
    """
    import google

    types_module = pytypes.ModuleType("google.genai.types")
    types_module.GenerateContentConfig = _FakeGenerateContentConfig
    genai_module = pytypes.ModuleType("google.genai")
    genai_module.types = types_module
    genai_module.Client = _FakeClient

    monkeypatch.setattr(google, "genai", genai_module, raising=False)
    monkeypatch.setitem(sys.modules, "google.genai", genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_module)
    return genai_module


@pytest.fixture
def gemini(config, genai_stub) -> GeminiComposer:
    return GeminiComposer(config)


def test_the_gemini_composer_is_unavailable_without_its_dependency(config, monkeypatch):
    """It must say which package is missing rather than fail on an attribute.

    The absence has to be staged now that google-adk pulls `google-genai` in:
    both the attribute on the `google` package and the `sys.modules` entry have
    to go, or the import the guard is protecting would quietly succeed and this
    test would assert nothing.
    """
    import google

    monkeypatch.delattr(google, "genai", raising=False)
    monkeypatch.setitem(sys.modules, "google.genai", None)

    with pytest.raises(ImportError, match="pip install google-genai"):
        GeminiComposer(config)


def test_the_model_defaults_and_can_be_overridden(config, genai_stub, monkeypatch):
    assert GeminiComposer(config).model == GeminiComposer.DEFAULT_MODEL

    monkeypatch.setenv("POLICY_RAG_GENERATOR_MODEL", "gemini-2.5-pro")
    assert GeminiComposer(config).model == "gemini-2.5-pro"
    # An explicit argument still wins over the environment.
    assert GeminiComposer(config, model="gemini-2.5-flash-lite").model == "gemini-2.5-flash-lite"


def test_the_context_block_numbers_every_extract():
    hits = [_hit(text="Fourteen days."), _hit(chunk_id="1" * 16, doc_title="Sick Leave", text="Also fourteen.")]

    block = GeminiComposer._context_block(hits)

    assert block.startswith("[1] Vacation Leave - Accrual\nFourteen days.")
    assert "[2] Sick Leave - Accrual\nAlso fourteen." in block


def test_a_grounded_generation_is_returned_with_numbered_sources(gemini):
    gemini._client.models.outcome = "Employees accrue 14 days of paid vacation leave per year. [1]"

    answer = gemini.compose(_result([_hit(text=VACATION_TEXT)]), GuardDecision())

    assert answer.decision == "ANSWER"
    assert answer.composer == "gemini"
    assert answer.groundedness >= GROUNDEDNESS_GATE
    assert "**Sources**" in answer.text
    assert "- [1] [Vacation Leave](okf/altostrat-sg-handbook/leave/vacation.md#accrual)" in answer.text

    call = gemini._client.models.calls[0]
    assert call.model == GeminiComposer.DEFAULT_MODEL
    assert "how much vacation leave do I accrue" in call.contents
    assert VACATION_TEXT in call.contents
    assert call.config.kwargs["temperature"] == 0.0
    assert "Never use outside knowledge" in call.config.kwargs["system_instruction"]


def test_generation_notices_and_placeholders_are_applied_after_the_gate(gemini):
    gemini._client.models.outcome = "Employees accrue 14 days of paid vacation leave. Write to abc@altostrat.com."
    decision = GuardDecision(notices=["Verify with People Ops."])

    answer = gemini.compose(_result([_hit(text=VACATION_TEXT + " Write to abc@altostrat.com.")]), decision)

    body, _, _note = answer.text.partition("**Please note**")
    assert "abc@altostrat.com" not in body
    assert PLACEHOLDER_REDACTION in body
    assert "Verify with People Ops." in answer.notices


def test_an_ungrounded_generation_is_refused_rather_than_shown(gemini, caplog):
    """SDD §3.3: the grounding instruction is not trusted, it is checked. A fluent
    answer that introduces figures the extracts do not contain is the exact
    failure NFR-3.1 prices highest."""
    gemini._client.models.outcome = "Employees may take 30 days of paid sabbatical in Zurich each quarter."

    with caplog.at_level("WARNING", logger="src.grounding.policy_rag.answer"):
        answer = gemini.compose(_result([_hit(text=VACATION_TEXT)]), GuardDecision())

    assert answer.decision == "REFUSE"
    assert answer.reason == "groundedness_gate"
    assert answer.text == REFUSAL_TEXT
    assert answer.groundedness < GROUNDEDNESS_GATE
    assert "below gate" in caplog.text


def test_an_empty_generation_falls_back_to_the_extracts(gemini):
    """A blank response is not a refusal - the corpus did have a match, so the
    passages are shown rather than answering nothing."""
    gemini._client.models.outcome = "   "

    answer = gemini.compose(_result([_hit(text=VACATION_TEXT)]), GuardDecision())

    assert answer.composer == "extractive"
    assert VACATION_TEXT in answer.text


def test_a_failed_generation_degrades_to_the_extracts_and_says_so(gemini):
    """NFR-4.1: degrade to something correct, never to a fabricated answer."""
    gemini._client.models.outcome = RuntimeError("503 model overloaded")

    answer = gemini.compose(_result([_hit(text=VACATION_TEXT)]), GuardDecision())

    assert answer.composer == "extractive"
    assert VACATION_TEXT in answer.text
    assert any("Generated prose was unavailable" in n for n in answer.notices)


def test_a_generation_with_no_hits_is_refused_by_the_groundedness_gate(gemini):
    """With no extracts there is nothing to support the prose, so the measured
    groundedness is 0 and the answer never reaches the caller."""
    gemini._client.models.outcome = "Employees accrue 14 days of paid vacation leave per year."

    answer = gemini.compose(_result([]), GuardDecision())

    assert answer.decision == "REFUSE"
    assert answer.groundedness == 0.0
    assert answer.relevance == 0.0


def test_a_generation_that_clears_the_gate_with_no_hits_carries_no_source_block(gemini, monkeypatch):
    """Defensive: `**Sources**` is only emitted when there is something to cite.

    The gate makes this unreachable today - an empty context scores 0 - so the
    measurement is stubbed to reach the formatting branch. It matters because an
    empty **Sources** heading reads as "cited" while pointing at nothing.
    """
    import src.grounding.policy_rag.answer as answer_module

    monkeypatch.setattr(answer_module, "measure_groundedness", lambda text, hits: 1.0)
    gemini._client.models.outcome = "There is nothing in the handbook about that."

    answer = gemini.compose(_result([]), GuardDecision())

    assert answer.decision == "ANSWER"
    assert "**Sources**" not in answer.text
    assert answer.citations == []


# --- composer selection -------------------------------------------------------


def test_the_default_composer_is_extractive(config, monkeypatch):
    monkeypatch.delenv("POLICY_RAG_COMPOSER", raising=False)

    assert isinstance(build_composer(config), ExtractiveComposer)


def test_the_composer_can_be_selected_by_environment(config, genai_stub, monkeypatch):
    monkeypatch.setenv("POLICY_RAG_COMPOSER", "GEMINI")

    assert isinstance(build_composer(config), GeminiComposer)


def test_an_explicit_name_wins_over_the_environment(config, monkeypatch):
    monkeypatch.setenv("POLICY_RAG_COMPOSER", "gemini")

    assert isinstance(build_composer(config, "extractive"), ExtractiveComposer)


def test_an_unknown_composer_is_refused(config):
    with pytest.raises(ValueError, match="unknown composer: 'claude'"):
        build_composer(config, "claude")
