"""`PolicySpecialistNode`, the policy leg of the StateGraph pipeline (§3.2, §3.3).

This node had no coverage at all while it answered from a five-entry dict. Now
that it retrieves from the same FAISS corpus as the REST path, the two can drift
apart, so the shared behaviours are asserted on both: the same handbook figure,
the same escalation, the same refusal.
"""
import pytest

from src.core.agents.policy import GroundedAnswer, PolicySpecialistNode
from src.grounding.faiss_pipeline import faiss_policy_rag

requires_index = pytest.mark.skipif(
    not faiss_policy_rag.is_ready,
    reason="FAISS index not built; run `python -m src.grounding.policy_rag.cli ingest`",
)


def _state(prompt: str) -> dict:
    return {"masked_input": prompt, "user_input": prompt}


# --- grounded against the real corpus ---------------------------------------


@requires_index
async def test_node_answers_from_the_handbook_corpus():
    state = await PolicySpecialistNode().execute(_state("How many days of bereavement leave do I get?"))

    assert state["grounding_source"] == "faiss"
    assert state["policy_decision"] == "answer"
    assert "20 work days" in state["final_response"]
    assert state["citations"]
    assert any("bereavement.md" in c["uri"] for c in state["citations"])
    assert state["next_node"] == "guardrails_out"


@requires_index
async def test_node_does_not_duplicate_the_source_block():
    """The extractive composer already appends its own **Sources** list."""
    state = await PolicySpecialistNode().execute(_state("vacation leave accrual"))

    assert state["final_response"].count("**Sources**") == 1
    assert "\n\nSource: [" not in state["final_response"]


@requires_index
async def test_node_escalates_extended_workforce_leave():
    """The guard's routing message is the useful part; do not flatten it to a refusal."""
    state = await PolicySpecialistNode().execute(_state("Can a contractor take vacation leave?"))

    assert state["policy_decision"] == "escalate"
    assert "direct employer" in state["final_response"].lower()
    # Not grounded, but not the generic FR-5.4 fallback either.
    assert "could not find a verified answer" not in state["final_response"]


@requires_index
async def test_node_refuses_what_the_corpus_does_not_cover():
    state = await PolicySpecialistNode().execute(_state("reimbursement limit for pet helicopter transport"))

    assert state["policy_decision"] == "refuse"
    assert "could not find a verified answer" in state["final_response"]
    assert state["citations"] == []


# --- the mock datastore fallback --------------------------------------------


@pytest.fixture
def no_index(monkeypatch):
    monkeypatch.setattr(type(faiss_policy_rag), "is_ready", property(lambda self: False))


async def test_node_falls_back_to_the_mock_datastore(no_index):
    state = await PolicySpecialistNode().execute(_state("what is the bereavement policy"))

    assert state["grounding_source"] == "curated"
    assert "5 consecutive paid business days" in state["final_response"]
    # The mock has no composer, so the node appends the citation itself.
    assert "Source: [Bereavement Leave Policy]" in state["final_response"]


async def test_mock_datastore_refuses_hallucination_baits(no_index):
    state = await PolicySpecialistNode().execute(_state("reimbursement for personal pet helicopter transport"))

    assert state["policy_decision"] == "refuse"
    assert state["grounding_score"] == 0.0
    assert "could not find a verified answer" in state["final_response"]


async def test_mock_datastore_refuses_anything_its_five_entries_do_not_cover(no_index):
    """The bait list is a shortcut for known-absent topics; the default is still
    refusal. A keyword matcher has no notion of "not in the corpus", so a query
    matching nothing must not fall through to the highest-scoring near-miss."""
    state = await PolicySpecialistNode().execute(_state("what is the guest wifi password"))

    assert state["policy_decision"] == "refuse"
    assert state["citations"] == []
    assert "could not find a verified answer" in state["final_response"]


async def test_mock_datastore_needs_every_term_of_a_multi_word_topic(no_index):
    """"leave" alone must not select the bereavement entry - the key is two words."""
    answer = PolicySpecialistNode()._query_mock_datastore("tell me about leave")

    assert answer.decision == "refuse"


# --- the grounding gate ------------------------------------------------------


async def test_answers_below_the_grounding_gate_are_withheld():
    """SDD §3.3: groundedness >= 0.85 or no answer, whatever the backend said."""
    node = PolicySpecialistNode()
    weak = GroundedAnswer(score=0.60, text="A confident-sounding claim.", decision="answer", source="faiss")

    async def _weak(query, entitlements=None):
        return weak

    node.query_knowledge_base = _weak
    state = await node.execute(_state("anything"))

    assert "A confident-sounding claim." not in state["final_response"]
    assert "could not find a verified answer" in state["final_response"]


def test_the_backend_is_resolved_once(monkeypatch):
    """A missing index must not retry a failed load, and warn, on every turn."""
    calls = []

    def _counted(self):
        calls.append(1)
        return False

    monkeypatch.setattr(type(faiss_policy_rag), "is_ready", property(_counted))

    node = PolicySpecialistNode()
    for _ in range(3):
        node._rag_service()

    assert len(calls) == 1
