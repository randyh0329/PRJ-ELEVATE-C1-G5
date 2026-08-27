"""
Policy Specialist Agent (RAG Knowledge Base).
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.1, §3.2, §3.3 Path 1 (FR-5.1 - FR-5.4, NFR-3.1).
Model: Gemini 3.7 Flash (Pinned).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

from src.core.state import AgentState

logger = logging.getLogger("agents.policy")


@dataclass
class GroundedAnswer:
    """What the knowledge base returned for one query.

    Replaces the `(relevance, content, citations)` tuple this node used to pass
    around, because that shape cannot express an *escalation* - a question the
    corpus recognises but must not answer, such as leave entitlement for a
    contractor. Collapsing those into "no answer" would lose the routing
    instruction, which is the useful part.
    """

    #: Groundedness of the composed answer, i.e. the SDD §3.3 gate this node
    #: enforces. Relevance is the other half and is applied inside the retriever.
    score: float = 0.0
    text: str | None = None
    citations: list[dict[str, str]] = field(default_factory=list)
    #: `answer` | `escalate` | `refuse`
    decision: str = "refuse"
    #: `faiss` (indexed handbook) | `curated` (the mock datastore below)
    source: str = "curated"


class PolicySpecialistNode:
    """
    Policy Specialist Agent node (Gemini 3.7 Flash).
    Executes grounded semantic search across the ACL-governed policy datastore.
    Enforces strict grounding threshold (>= 0.85) and resolvable deep-link citations.

    Retrieval runs against the FAISS index over `okf/altostrat-sg-handbook/` and
    the raw handbook when that index exists. `KNOWLEDGE_BASE` below is the
    pre-corpus mock and is used only as a fallback, because the index is a
    git-ignored build artefact and a fresh clone has none. The two do not agree
    on content or on citation URIs, so `GroundedAnswer.source` reports which one
    ran - see `DualGroundingEngine` for the same split on the REST path.
    """

    AGENT_ID = "pol-1.4.0"
    MODEL_ID = "gemini-3.7-flash@2026-08"

    #: Grounding gate (SDD §3.3 Path 1). The relevance half of the dual gate is
    #: enforced inside the retriever at 0.80; this is the groundedness half.
    GROUNDING_GATE = 0.85

    # Pre-indexed policy knowledge base corpus (Mock Agent Search Datastore)
    KNOWLEDGE_BASE: ClassVar[dict[str, dict[str, Any]]] = {
        "bereavement": {
            "title": "Bereavement Leave Policy",
            "citation": "policies/leave-policy-2026.pdf#bereavement",
            "content": "Employees are eligible for up to 5 consecutive paid business days for immediate family members.",
            "relevance": 0.95,
        },
        "remote work equipment": {
            "title": "Remote Work Policy s4.2",
            "citation": "policies/remote-work-2026.pdf#s4.2-equipment",
            "content": "Remote employees are eligible for one ergonomic home office monitor every 24 months, with a price cap of USD 350. On-site designated employees are not eligible.",
            "relevance": 0.96,
        },
        "short-term medical leave": {
            "title": "Medical & Disability Leave Policy s3.1",
            "citation": "policies/medical-leave-2026.pdf#short-term-medical",
            "content": "Short-term medical leave requires a WorkWeek leave filing under 'Medical' with pending manager approval, accompanied by an IT service ticket for mailbox delegation.",
            "relevance": 0.94,
        },
        "relocation allowance": {
            "title": "Global Mobility & Relocation Policy s2.4",
            "citation": "policies/mobility-policy-2026.pdf#relocation-allowance",
            "content": "Intra-region office transfers (such as US to London) provide a relocation allowance cap of USD 5,000, profile contact update, and Facilities badge access provisioning.",
            "relevance": 0.92,
        },
        "expense": {
            "title": "Expense Reimbursement Policy s5.1",
            "citation": "policies/expense-policy-2026.pdf#hardware",
            "content": "Standard home office peripherals (e.g. noise-canceling headphones up to $150) may be expensed with manager sign-off.",
            "relevance": 0.91,
        },
    }

    def __init__(self, rag: Any | None = None) -> None:
        self._rag = rag
        #: Resolve the backend once rather than retrying a missing index - and
        #: logging the same warning - on every turn.
        self._rag_resolved = rag is not None

    def _rag_service(self) -> Any | None:
        """The FAISS service, or `None` when the index has not been built."""
        if not self._rag_resolved:
            self._rag_resolved = True
            try:
                from src.grounding.faiss_pipeline import faiss_policy_rag

                if faiss_policy_rag.is_ready:
                    self._rag = faiss_policy_rag.service
                else:
                    logger.warning(
                        "[%s] FAISS policy index not built - using the mock datastore. "
                        "Run: python -m src.grounding.policy_rag.cli ingest",
                        self.AGENT_ID,
                    )
            except ImportError:  # pragma: no cover - faiss/numpy not installed
                logger.warning("[%s] policy RAG dependencies unavailable", self.AGENT_ID)
        return self._rag

    async def query_knowledge_base(
        self,
        query: str,
        entitlements: list[str] | None = None,
    ) -> GroundedAnswer:
        """
        Query the ACL-governed policy datastore with grounding attribution.

        `entitlements` must come from the authenticated session, never from the
        prompt (SDD §4.1/§4.7). Absent a caller-to-entitlement mapping the
        retriever's `general` default applies, which is the safe direction.
        """
        service = self._rag_service()
        if service is None:
            return self._query_mock_datastore(query)

        answer = service.answer(query, entitlements=entitlements)
        # `GuardAction` is an uppercase vocabulary; normalise so both backends
        # report the same three words.
        decision = answer.decision.lower()
        return GroundedAnswer(
            score=answer.groundedness,
            # An escalation carries its own routing message; a refusal has
            # nothing to say and lets `execute` emit the FR-5.4 fallback.
            text=answer.text if decision in ("answer", "escalate") else None,
            citations=[{"title": c.title, "uri": c.uri} for c in answer.citations],
            decision=decision,
            source="faiss",
        )

    def _query_mock_datastore(self, query: str) -> GroundedAnswer:
        """Fallback keyword match over `KNOWLEDGE_BASE` when there is no index."""
        q_lower = query.lower()

        # Explicit Hallucination Baits / Absent Policies (Tier 3) -> Strict Refusal.
        # The indexed path needs no such list: a bait scores below the relevance
        # gate and is refused on the evidence. This is here because a five-entry
        # keyword matcher has no notion of "not in the corpus".
        if any(bait in q_lower for bait in ["helicopter", "crypto", "bitcoin", "yacht", "dog transport", "pet transport"]):
            return GroundedAnswer(decision="refuse")

        best_match = None
        best_relevance = 0.0

        for key, doc in self.KNOWLEDGE_BASE.items():
            key_terms = key.split()
            # Require all terms for multi-word keys or strong single-term match
            matched = all(term in q_lower for term in key_terms) or (
                len(key_terms) == 1 and key_terms[0] in q_lower and "reimbursement" in q_lower
            )
            if matched and doc["relevance"] > best_relevance:
                best_match = doc
                best_relevance = doc["relevance"]

        if best_match and best_relevance >= 0.80:
            return GroundedAnswer(
                score=best_relevance,
                text=best_match["content"],
                citations=[{"title": best_match["title"], "uri": best_match["citation"]}],
                decision="answer",
                source="curated",
            )

        return GroundedAnswer(decision="refuse")

    async def execute(self, state: AgentState) -> AgentState:
        """
        Processes policy query turns and guarantees zero-hallucination answers (FR-5.2).
        """
        query = state.get("masked_input", state.get("user_input", ""))
        logger.info("[%s] Executing grounded query for: '%s'", self.AGENT_ID, query)

        result = await self.query_knowledge_base(query)
        state["grounding_score"] = result.score
        state["citations"] = result.citations
        state["grounding_source"] = result.source
        state["policy_decision"] = result.decision

        if result.decision == "escalate" and result.text:
            # The corpus recognises the topic but must not answer it - a
            # contractor leave question, or a rule the source contradicts itself
            # on. Passing the guard's routing message through is the point.
            state["final_response"] = result.text
        elif result.decision == "answer" and result.text and result.score >= self.GROUNDING_GATE:
            state["final_response"] = result.text + self._citation_suffix(result)
        else:
            # Fallback per FR-5.4 / §5.5
            state["final_response"] = (
                "I could not find a verified answer in the official corporate HR policy documents, "
                "so I would rather not guess. Please refer to the HR Portal at hr.corp.internal."
            )

        state["next_node"] = "guardrails_out"
        return state

    @staticmethod
    def _citation_suffix(result: GroundedAnswer) -> str:
        """Append a citation only when the composer has not already done so.

        The extractive composer emits its own resolved **Sources** block, so
        adding one here would print the same links twice.
        """
        if result.source == "faiss" or not result.citations:
            return ""
        first = result.citations[0]
        return f"\n\nSource: [{first['title']}]({first['uri']})"
