"""Dual Grounding Engine providing 100% grounded policy answers and citations."""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from src.grounding.okf_store import PolicyDocument, okf_store

logger = logging.getLogger("grounding.policy_engine")


class PolicyQueryResult(BaseModel):
    """Result of policy retrieval and grounding."""
    is_grounded: bool
    answer_text: str
    citations: List[str] = Field(default_factory=list)
    referenced_section_ids: List[str] = Field(default_factory=list)
    confidence_score: float
    #: Which backend answered: `faiss` (the indexed handbook corpus) or
    #: `curated` (the four baseline documents in `okf_store`). Recorded because
    #: the two do not always agree - see the class docstring below.
    source: str = "curated"
    #: Guard disposition from the RAG backend: `answer`, `escalate` or `refuse`.
    #: An escalation is not a refusal: the corpus has something to say, but the
    #: honest response is to route the question to a human.
    decision: str = "answer"


class DualGroundingEngine:
    """Curated OKF rules plus FAISS semantic search over the handbook corpus.

    "Dual" is now literal. Free-text policy questions are answered from the FAISS
    index built over `okf/altostrat-sg-handbook/` and the raw handbook - 480
    chunks, under the SDD §3.3 dual gate, with the corpus-datasheet guards and
    resolved deep-link citations. The four hand-written `PolicyDocument`s in
    `okf_store` stay as a fallback for when that index has not been built: it is
    a git-ignored build artefact, so a fresh clone has none and the agent still
    has to answer rather than crash.

    **The fallback is not equivalent, and that is why it reports itself.** Where
    the two overlap they disagree: the curated entry says bereavement leave is
    "up to 5 consecutive days"; `leave/bereavement.md` in the actual handbook
    says four weeks, 20 work days, and flags that the two source layers dispute
    intern eligibility. The curated set is a demo fixture that predates the
    corpus. `PolicyQueryResult.source` records which one answered so an audit
    event can tell a grounded answer from a degraded one.
    """

    def __init__(self, store: Optional[object] = None, rag: Optional[Any] = None) -> None:
        self._store = store or okf_store
        self._rag = rag
        #: Resolve the backend once. Without this a missing index means a failed
        #: `PolicyIndex.load` on every single turn, and a warning logged on every
        #: single turn, which trains the reader to ignore it.
        self._rag_resolved = rag is not None

    # --- backend selection --------------------------------------------------

    def _rag_service(self) -> Optional[Any]:
        """The FAISS service, or `None` when the index has not been built."""
        if not self._rag_resolved:
            self._rag_resolved = True
            try:
                from src.grounding.faiss_pipeline import faiss_policy_rag

                if faiss_policy_rag.is_ready:
                    self._rag = faiss_policy_rag.service
                else:
                    logger.warning(
                        "FAISS policy index not built - falling back to the curated OKF "
                        "documents, which cover far less and disagree with the handbook "
                        "in places. Run: python -m src.grounding.policy_rag.cli ingest"
                    )
            except ImportError:  # pragma: no cover - faiss/numpy not installed
                logger.warning("policy RAG dependencies unavailable; using curated OKF documents")
        return self._rag

    # --- public API ---------------------------------------------------------

    def query_policy(
        self,
        user_query: str,
        *,
        entitlements: Optional[List[str]] = None,
        curated_only: bool = False,
    ) -> PolicyQueryResult:
        """Search policy knowledge and formulate a grounded response with clickable citations.

        `entitlements` must come from the authenticated caller (SDD §4.1/§4.7).
        There is no employee-to-entitlement mapping in this codebase yet, so the
        default is the `general` set - which is the safe direction: an employee
        asking a self-service question cannot reach `hr_operational` material.

        `curated_only` forces the deterministic register. Use it when a citation
        has to be *stable* rather than *best-matching* - see `_handle_relocation`
        and the equipment flow in `src/core/agent.py`, where the cited rule is the
        entitlement authorising a transaction. A monetary cap that moves because a
        retrieval ranking shifted is a defect, not a better answer.
        """
        service = None if curated_only else self._rag_service()
        if service is not None:
            return self._from_corpus(service, user_query, entitlements)
        return self._from_curated(user_query)

    # --- backends -----------------------------------------------------------

    def _from_corpus(self, service: Any, user_query: str, entitlements: Optional[List[str]]) -> PolicyQueryResult:
        """Retrieve → guard → compose against the indexed handbook."""
        answer = service.answer(user_query, entitlements=entitlements)

        # The composer already appends a resolved source list to the answer text,
        # so this list is the machine-readable form of the same thing rather than
        # something the caller has to splice in.
        citations = [f"[{c.title}]({c.uri})" for c in answer.citations]

        return PolicyQueryResult(
            is_grounded=answer.answered,
            answer_text=answer.text,
            citations=citations,
            referenced_section_ids=[hit.chunk.path for hit in answer.hits],
            confidence_score=answer.relevance,
            source="faiss",
            # `GuardAction` is an uppercase vocabulary; this field is lowercase so
            # that both backends report the same three words.
            decision=answer.decision.lower(),
        )

    def _from_curated(self, user_query: str) -> PolicyQueryResult:
        """The pre-corpus baseline: four documents, keyword-scored."""
        matching_policies = self._store.search_policies(user_query)

        if not matching_policies:
            return PolicyQueryResult(
                is_grounded=False,
                answer_text="I could not find an approved policy on this topic in our handbook. Would you like me to open an HR inquiry ticket?",
                citations=[],
                referenced_section_ids=[],
                confidence_score=0.0,
                source="curated",
                decision="refuse",
            )

        top_policy: PolicyDocument = matching_policies[0]
        citation_md = f"[{top_policy.citation_title}]({top_policy.citation_url})"

        # Synthesize grounded answer
        answer = f"{top_policy.details}\n\nCitation: {citation_md}"

        return PolicyQueryResult(
            is_grounded=True,
            answer_text=answer,
            citations=[citation_md],
            referenced_section_ids=[top_policy.section_id],
            confidence_score=0.98,
            source="curated",
            decision="answer",
        )


# Global singleton grounding engine
dual_grounding_engine = DualGroundingEngine()
