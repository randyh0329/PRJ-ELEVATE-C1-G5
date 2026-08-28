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


# --- the curated OKF register fallback ---------------------------------------


@pytest.fixture
def no_index(monkeypatch):
    monkeypatch.setattr(type(faiss_policy_rag), "is_ready", property(lambda self: False))


async def test_node_falls_back_to_the_curated_register(no_index):
    state = await PolicySpecialistNode().execute(_state("what is the bereavement policy"))

    assert state["grounding_source"] == "curated"
    # Both backends now read the same corpus, so both must produce the same
    # figure. The dict this register replaced said "5 consecutive paid business
    # days", and a fallback that quietly contradicts the primary path is worse
    # than one that refuses.
    assert "4 weeks" in state["final_response"]
    assert "5 consecutive paid business days" not in state["final_response"]
    # No composer on this path, so the node appends the citation itself - and it
    # is a URL that opens the cited text, not an invented `hr.corp.internal` one.
    assert "Source: [Bereavement Leave (Global) - Handbook Section 22]" in state["final_response"]
    assert "https://github.com/" in state["final_response"]


async def test_curated_register_refuses_hallucination_baits(no_index):
    """No bait list any more: the coverage floor refuses this on the evidence."""
    state = await PolicySpecialistNode().execute(_state("reimbursement for personal pet helicopter transport"))

    assert state["policy_decision"] == "refuse"
    assert state["grounding_score"] == 0.0
    assert "could not find a verified answer" in state["final_response"]


async def test_curated_register_refuses_what_the_corpus_does_not_cover(no_index):
    """A keyword register has no notion of "not in the corpus" unless one is
    built in, so a query matching nothing must not fall through to the
    highest-scoring near-miss."""
    state = await PolicySpecialistNode().execute(_state("what is the guest wifi password"))

    assert state["policy_decision"] == "refuse"
    assert state["citations"] == []
    assert "could not find a verified answer" in state["final_response"]


async def test_curated_register_refuses_an_ambiguous_topic(no_index):
    """"leave" alone matches eleven leave concepts equally well. Returning
    whichever sorted first would present a coin-flip as a determinate answer."""
    answer = PolicySpecialistNode()._query_curated_store("tell me about leave")

    assert answer.decision == "refuse"


async def test_curated_register_flags_a_documented_source_conflict(no_index):
    """The bereavement concept records a dispute over intern eligibility. The
    OKF `Conflict` convention exists so the register does not silently pick a
    side, and the caveat is how that reaches the employee."""
    answer = PolicySpecialistNode()._query_curated_store("what is the bereavement policy")

    assert answer.decision == "answer"
    assert "inconsistent" in answer.text
    assert "People Ops" in answer.text


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
