"""The retrieve -> guard -> compose sequence, end to end through the façade."""

from __future__ import annotations

from src.grounding.policy_rag.guards import GuardAction


def test_answer_below_the_gate_refuses_rather_than_guessing(service):
    """FR-5.4 / NFR-3.1: a weak match is not an answer."""
    answer = service.answer("What is the stock option vesting schedule?", relevance_gate=1.01)
    assert answer.decision == GuardAction.REFUSE.value
    assert not answer.answered
    assert "could not find" in answer.text
    assert answer.citations == []


def test_extended_workforce_guard_beats_retrieval(service):
    """The guard fires on the query, so it holds even when retrieval is confident."""
    answer = service.answer("I am a contractor, how much annual leave do I get?", relevance_gate=0.0)
    assert answer.decision == GuardAction.ESCALATE.value
    assert answer.reason == "extended_workforce_leave"


def test_absent_section_guard_beats_retrieval(service):
    answer = service.answer("What does handbook Section 15 cover?", relevance_gate=0.0)
    assert answer.decision == GuardAction.ESCALATE.value
    assert answer.reason == "absent_section"


def test_extractive_answer_is_fully_grounded(service):
    """Quoting cannot hallucinate, so groundedness must be 1.0 by construction."""
    answer = service.answer("vacation leave accrual carryover", relevance_gate=0.0)
    assert answer.decision == GuardAction.ANSWER.value
    assert answer.groundedness == 1.0
    assert answer.citations
    assert all(c.resolved for c in answer.citations)


def test_answer_carries_its_retrieval(service):
    answer = service.answer("vacation leave accrual", relevance_gate=0.0)
    assert answer.retrieval is not None
    assert answer.retrieval.gate == 0.0


def test_entitlements_are_honoured_end_to_end(service):
    """A general caller must not receive hr_operational material in an answer."""
    answer = service.answer("source defect register", entitlements=["general"], relevance_gate=0.0)
    assert all("references/" not in h.chunk.path for h in answer.hits)


def test_to_dict_is_json_safe(service):
    import json

    answer = service.answer("vacation leave accrual", relevance_gate=0.0)
    json.dumps(answer.to_dict())


def test_stats_report_the_index(service):
    stats = service.stats()
    assert stats["chunks"] > 0
    assert stats["vectors"] == stats["chunks"]
    assert stats["manifest"]["embedder_fingerprint"]
