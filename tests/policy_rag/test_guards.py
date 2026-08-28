"""The corpus datasheet's "what must not be answered" rules, as executable checks.

Each test names the datasheet rule it enforces. If a rule is ever relaxed, the
test that fails should be the one that explains what was given up.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.grounding.policy_rag.answer import measure_groundedness
from src.grounding.policy_rag.config import GuardConfig
from src.grounding.policy_rag.documents import Citation, Hit
from src.grounding.policy_rag.guards import (
    PLACEHOLDER_REDACTION,
    GuardAction,
    evaluate,
    redact_placeholders,
)
from tests.policy_rag.conftest import make_chunk

CFG = GuardConfig()
NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


def hit(**overrides) -> Hit:
    chunk = make_chunk(**overrides)
    return Hit(
        chunk=chunk,
        dense_score=0.8,
        lexical_score=0.5,
        relevance=0.9,
        citation=Citation(title=chunk.doc_title, uri=f"{chunk.path}#{chunk.anchor}", resolved=True),
    )


def test_a_decision_serialises_for_the_response_envelope():
    """The action goes out as its string value, not as `GuardAction.ESCALATE` -
    the A2A executor puts this straight into JSON."""
    decision = evaluate("What does Section 11 say?", [hit()], CFG, now=NOW)

    payload = decision.to_dict()

    assert payload["action"] == "ESCALATE"
    assert payload["reason"] == "absent_section"
    assert payload["message"]
    assert payload["notices"] == []
    # A copy, so a caller mutating the payload cannot edit the decision.
    payload["notices"].append("tampered")
    assert decision.notices == []


# --- rule 5: sections that do not exist --------------------------------------


@pytest.mark.parametrize("section", ["11", "15"])
def test_absent_sections_escalate(section):
    decision = evaluate(f"What does Section {section} say?", [hit()], CFG, now=NOW)
    assert decision.action is GuardAction.ESCALATE
    assert decision.reason == "absent_section"
    assert "not evidence" in decision.message


def test_existing_section_is_not_flagged():
    decision = evaluate("What does Section 20 say?", [hit()], CFG, now=NOW)
    assert decision.action is GuardAction.ANSWER


# --- rule 2: extended workforce leave ----------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "I am a contractor, how much annual leave do I get?",
        "What sick leave are vendors entitled to?",
        "Do temps accrue vacation?",
        "As a consultant am I entitled to childcare leave?",
    ],
)
def test_extended_workforce_leave_escalates(query):
    decision = evaluate(query, [hit()], CFG, now=NOW)
    assert decision.action is GuardAction.ESCALATE
    assert decision.reason == "extended_workforce_leave"
    assert "direct employer" in decision.message


def test_extended_workforce_non_leave_question_is_answerable():
    """The exclusion is scoped to leave, not to every question a contractor asks."""
    decision = evaluate("Can a contractor accept a client gift?", [hit()], CFG, now=NOW)
    assert decision.action is GuardAction.ANSWER


def test_employee_leave_question_is_not_caught():
    decision = evaluate("How much annual leave do I get?", [hit()], CFG, now=NOW)
    assert decision.action is GuardAction.ANSWER


# --- rule 1: source contradictions -------------------------------------------


def test_conflict_top_hit_escalates_and_does_not_pick_a_side():
    decision = evaluate(
        "Are interns eligible for bereavement leave?",
        [hit(is_conflict=True, heading_path=["Conflict: are interns eligible?"])],
        CFG,
        now=NOW,
    )
    assert decision.action is GuardAction.ESCALATE
    assert decision.reason == "source_conflict"
    assert "inconsistent" in decision.message
    assert "People Ops" in decision.message


def test_conflict_below_the_top_hit_only_caveats():
    decision = evaluate(
        "How do I request unpaid time off?",
        [hit(), hit(chunk_id="1" * 16, is_conflict=True, heading_path=["Conflicts"])],
        CFG,
        now=NOW,
    )
    assert decision.action is GuardAction.ANSWER
    assert any("source conflict" in n for n in decision.notices)


def test_conflict_guard_can_be_disabled_for_operational_callers():
    cfg = GuardConfig(conflict_sections=False)
    decision = evaluate("anything", [hit(is_conflict=True)], cfg, now=NOW)
    assert decision.action is GuardAction.ANSWER


# --- no hits ------------------------------------------------------------------


def test_no_hits_refuses_rather_than_escalating():
    """Nothing retrieved means the corpus has nothing - a human cannot help either."""
    decision = evaluate("What is the stock vesting schedule?", [], CFG, now=NOW)
    assert decision.action is GuardAction.REFUSE
    assert decision.reason == "no_hits"


# --- notices ------------------------------------------------------------------


def test_gap_section_adds_a_notice():
    decision = evaluate("How are part-days rounded?", [hit(is_gap=True)], CFG, now=NOW)
    assert decision.action is GuardAction.ANSWER
    assert any("unspecified" in n for n in decision.notices)


def test_stale_document_adds_a_notice():
    decision = evaluate("q", [hit(stale_after="2026-01-01T00:00:00Z")], CFG, now=NOW)
    assert any("review-by date" in n for n in decision.notices)


def test_fresh_document_adds_no_staleness_notice():
    decision = evaluate("q", [hit(stale_after="2027-07-01T00:00:00Z")], CFG, now=NOW)
    assert not any("review-by date" in n for n in decision.notices)


def test_unparseable_stale_after_does_not_crash():
    decision = evaluate("q", [hit(stale_after="whenever")], CFG, now=NOW)
    assert decision.action is GuardAction.ANSWER


def test_a_stale_after_without_a_timezone_is_read_as_utc():
    """A naive timestamp compared against an aware `now` raises, and a guard that
    raises takes down the answer it was only meant to caveat."""
    decision = evaluate("q", [hit(stale_after="2026-01-01")], CFG, now=NOW)

    assert decision.action is GuardAction.ANSWER
    assert any("review-by date" in n for n in decision.notices)


def test_the_staleness_check_can_be_turned_off():
    cfg = GuardConfig(staleness=False)

    decision = evaluate("q", [hit(stale_after="2026-01-01T00:00:00Z")], cfg, now=NOW)

    assert decision.notices == []


def test_draft_concept_adds_a_notice():
    decision = evaluate("q", [hit(status="draft")], CFG, now=NOW)
    assert any("draft" in n for n in decision.notices)


# --- rule 3: placeholder contacts ---------------------------------------------


def test_placeholder_address_is_redacted():
    text, notices = redact_placeholders("Write to abc@altostrat.com for help.", CFG)
    assert "abc@altostrat.com" not in text
    assert PLACEHOLDER_REDACTION in text
    assert notices


@pytest.mark.parametrize("token", ["`email`", "`company intranet`", "`Company Website`"])
def test_placeholder_tokens_raise_a_notice(token):
    _, notices = redact_placeholders(f"Request it through {token}.", CFG)
    assert notices
    assert "unresolved placeholder" in notices[0]


def test_clean_text_is_untouched():
    text, notices = redact_placeholders("Speak to your People Partner.", CFG)
    assert text == "Speak to your People Partner."
    assert notices == []


def test_redaction_can_be_disabled():
    cfg = GuardConfig(placeholder_contacts=False)
    text, notices = redact_placeholders("Write to abc@altostrat.com.", cfg)
    assert "abc@altostrat.com" in text
    assert notices == []


# --- groundedness (SDD §3.3, generation half) ---------------------------------


def test_groundedness_is_one_for_quoted_context():
    context = [hit()]
    assert measure_groundedness(context[0].chunk.text, context) == pytest.approx(1.0)


def test_groundedness_falls_when_facts_are_invented():
    context = [hit()]
    invented = "Employees accrue 30 days of paid sabbatical leave in Zurich every quarter."
    assert measure_groundedness(invented, context) < 0.85


def test_groundedness_of_empty_text_is_zero():
    assert measure_groundedness("", [hit()]) == 0.0
