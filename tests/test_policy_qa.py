"""Unit and integration tests for Policy Q&A with clickable citations (UC-1.1).

`DualGroundingEngine` answers from the FAISS index over the Altostrat Singapore
handbook when that index has been built, and from the four curated
`PolicyDocument`s in `okf_store` when it has not. Both branches are covered here,
because they give materially different answers - the curated set is a pre-corpus
demo fixture and contradicts the handbook in places.

The corpus tests skip rather than fail without an index: `var/` is a git-ignored
build artefact, so a fresh clone has none until `policy_rag.cli ingest` runs.
"""
import pytest

from src.core.agent import HREnterpriseAgent
from src.grounding.faiss_pipeline import faiss_policy_rag
from src.grounding.policy_engine import DualGroundingEngine

requires_index = pytest.mark.skipif(
    not faiss_policy_rag.is_ready,
    reason="FAISS index not built; run `python -m src.grounding.policy_rag.cli ingest`",
)


# --- grounded against the real corpus ---------------------------------------


@requires_index
def test_bereavement_leave_policy_qa(agent: HREnterpriseAgent):
    """UC-1.1: Bereavement inquiry returns the handbook's figure and a deep link."""
    prompt = "How many days of bereavement leave do I get under company policy?"
    response = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")

    assert response.intent == "UC_1_1_POLICY_QA"
    # okf/altostrat-sg-handbook/leave/bereavement.md, "Allowance". Note this is
    # *not* what the curated fallback says ("up to 5 consecutive days") - the
    # fixture predates the corpus and is wrong.
    assert "4 weeks" in response.response_text
    assert "20 work days" in response.response_text
    assert response.citations
    assert any("leave/bereavement.md" in citation for citation in response.citations)


@requires_index
def test_citations_are_clickable_deep_links(agent: HREnterpriseAgent):
    """FR-5.3: every citation resolves to a section, not just a document."""
    response = agent.process_message(
        user_prompt="What is the vacation leave accrual policy?", caller_employee_id="EMP-1001"
    )
    assert response.citations
    for citation in response.citations:
        assert citation.startswith("[") and "](" in citation
        assert "#" in citation, f"citation is not section-level: {citation}"


@requires_index
def test_ungrounded_policy_inquiry_no_hallucination(agent: HREnterpriseAgent):
    """NFR-3.1: refuse rather than guess when the corpus has nothing."""
    prompt = "What is the corporate policy regarding bringing pet dragons into the office?"
    response = agent.process_message(user_prompt=prompt, caller_employee_id="EMP-1001")

    assert "could not find" in response.response_text.lower()
    assert response.is_refusal is True
    assert len(response.citations) == 0


@requires_index
def test_extended_workforce_leave_escalates_rather_than_refusing():
    """An escalation is not a refusal - the guard has a routing instruction.

    Goes through the engine rather than the agent because the mock supervisor
    routes on keywords and this question's disposition is decided by the guards,
    not by the router.
    """
    result = DualGroundingEngine().query_policy("Can a contractor take vacation leave?")

    assert result.decision == "escalate"
    assert result.is_grounded is False
    assert "direct employer" in result.answer_text.lower()


@requires_index
def test_grounded_answers_report_their_backend():
    """`source` distinguishes a corpus answer from the degraded fallback."""
    result = DualGroundingEngine().query_policy("bereavement leave allowance")
    assert result.source == "faiss"
    assert result.referenced_section_ids  # chunk paths, not curated section ids


# --- the curated fallback ----------------------------------------------------


def test_curated_fallback_answers_when_the_index_is_missing(monkeypatch):
    """A fresh clone has no index and must still answer rather than crash."""
    monkeypatch.setattr(type(faiss_policy_rag), "is_ready", property(lambda self: False))

    result = DualGroundingEngine().query_policy("What is the bereavement leave policy?")

    assert result.source == "curated"
    assert result.is_grounded is True
    # The handbook's figure, not the demo fixture's. The fixture this register
    # replaced said "5 consecutive days" for immediate family and 3 for
    # extended; the handbook has no such split and grants four weeks per event.
    assert "4 weeks" in result.answer_text
    assert "20 work days" in result.answer_text
    assert "5 consecutive days" not in result.answer_text
    assert (
        "https://github.com/randyh0329/PRJ-ELEVATE-C1-G5/blob/main/"
        "okf/altostrat-sg-handbook/leave/bereavement.md" in result.answer_text
    )


def test_curated_fallback_still_refuses_the_ungrounded(monkeypatch):
    monkeypatch.setattr(type(faiss_policy_rag), "is_ready", property(lambda self: False))

    result = DualGroundingEngine().query_policy("policy on bringing pet dragons into the office")

    assert result.source == "curated"
    assert result.is_grounded is False
    assert result.decision == "refuse"
    assert result.citations == []


def test_curated_only_bypasses_the_corpus():
    """Saga steps cite a stable entitlement rule, not a best-matching passage."""
    result = DualGroundingEngine().query_policy(
        "international relocation allowance london", curated_only=True
    )

    assert result.source == "curated"
    # Handbook Section 4 (Travel & Expense), which is where relocation actually
    # lives. The fixture invented a "Section 14.1" and a £5,000 GBP cap; the
    # handbook caps it at US$10,000 and the currency was wrong too.
    assert result.referenced_section_ids == ["4"]
    assert "US$10,000" in result.answer_text
    assert "£5,000" not in result.answer_text
