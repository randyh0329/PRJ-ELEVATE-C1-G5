"""
Policy Specialist Agent (RAG Knowledge Base).
Compliant with Enterprise Agentic Solution Design Document (MVP 1) §3.1, §3.2, §3.3 Path 1 (FR-5.1 - FR-5.4, NFR-3.1).
Model: Gemini 3.7 Flash (Pinned).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.core.state import AgentState
from src.grounding.okf_store import PolicyDocument, okf_store

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
    #: `faiss` (semantic search over the indexed handbook) | `curated` (the
    #: deterministic OKF register in `okf_store`). Both read the same corpus;
    #: they differ in how they find the passage, not in what they may quote.
    source: str = "curated"


class PolicySpecialistNode:
    """
    Policy Specialist Agent node (Gemini 3.7 Flash).
    Executes grounded semantic search across the ACL-governed policy datastore.
    Enforces strict grounding threshold (>= 0.85) and resolvable deep-link citations.

    Retrieval runs against the FAISS index over `okf/altostrat-sg-handbook/` and
    the raw handbook when that index exists, and against the deterministic OKF
    register in `okf_store` when it does not - the index is a git-ignored build
    artefact, so a fresh clone has none. Both read the same corpus, so the
    fallback is now degraded in *recall* rather than in *truthfulness*;
    `GroundedAnswer.source` still reports which one ran, because a keyword
    register refuses questions the semantic path answers.

    This class previously carried a five-entry `KNOWLEDGE_BASE` dict of
    hand-written policy text with citation URIs pointing at PDFs that do not
    exist (`policies/leave-policy-2026.pdf#bereavement`). Every figure in it was
    wrong - bereavement leave is four weeks, not five days; the home office
    allowance is US$500, not US$350 - and because the citations could not be
    opened, nothing about reading the answer revealed that. See `okf_store` for
    the full diff and for why the register is now derived from the bundle.
    """

    AGENT_ID = "pol-1.4.0"
    MODEL_ID = "gemini-3.7-flash@2026-08"

    #: Grounding gate (SDD §3.3 Path 1). The relevance half of the dual gate is
    #: enforced inside the retriever at 0.80; this is the groundedness half.
    GROUNDING_GATE = 0.85

    #: Groundedness of a curated answer. 1.0 by construction, on the same
    #: argument the `ExtractiveComposer` makes: the text returned is the corpus
    #: document verbatim, so every claim in it is supported by the passage cited
    #: beside it. Nothing is paraphrased, summarised or generated, so there is no
    #: step at which a claim could detach from its source. What the register can
    #: still get wrong is *which* document - which is the relevance half of the
    #: gate, and is why `okf_store.search_policies` refuses on a near-tie rather
    #: than returning its best guess.
    CURATED_GROUNDEDNESS = 1.0

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
                        "[%s] FAISS policy index not built - using the deterministic OKF register, "
                        "which reads the same corpus but refuses questions semantic search would answer. "
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
            return self._query_curated_store(query)

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

    def _query_curated_store(self, query: str) -> GroundedAnswer:
        """Deterministic OKF register lookup, for when there is no FAISS index.

        There is no hallucination-bait list any more. The old one enumerated
        `helicopter`, `crypto`, `bitcoin`, `yacht` and two spellings of pet
        transport, which caught the baits someone had already thought of and
        nothing else - and it was needed because a five-key keyword matcher
        would otherwise hand "reimbursement for a pet helicopter" to its expense
        entry. `okf_store.search_policies` refuses those on the evidence now,
        the same way the indexed path does: a question the corpus does not cover
        fails the coverage floor, and one it covers ambiguously fails the
        decisiveness margin.
        """
        matches = okf_store.search_policies(query)
        if not matches:
            return GroundedAnswer(decision="refuse")

        top = matches[0]
        return GroundedAnswer(
            score=self.CURATED_GROUNDEDNESS,
            text=self._compose(top),
            citations=[{"title": top.citation_title, "uri": top.citation_url}],
            decision="answer",
            source="curated",
        )

    @staticmethod
    def _compose(document: PolicyDocument) -> str:
        """The document's own words, with the caveats its metadata demands.

        The summary leads because it is the corpus author's one-sentence version
        of the rule and the body can run to several screens. Both are quoted
        verbatim; nothing here rewrites policy text.
        """
        parts = [document.summary, document.details] if document.summary else [document.details]
        if document.has_conflict:
            # The handbook contradicts itself on part of this rule. Saying so is
            # the whole point of the OKF `Conflict` convention - answering as if
            # it were settled would pick a side the source does not pick.
            parts.append(
                "**Note.** The handbook is inconsistent on part of this policy; the disagreement "
                "is recorded above rather than resolved. Confirm with People Ops before relying "
                "on the contested point."
            )
        if document.status == "draft":
            parts.append("**Note.** This concept is a draft and its rules include producer assumptions.")
        return "\n\n".join(p for p in parts if p)

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
