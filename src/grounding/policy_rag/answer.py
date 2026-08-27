"""Answer composition and the groundedness half of the SDD §3.3 dual gate.

Two composers ship:

* ``extractive`` (default) - assembles the answer from retrieved passages
  verbatim. Groundedness is 1.0 by construction, so the FR-5.2 "only generate
  answers derived from the ingested policies" requirement holds without needing
  to trust a model. This is what the A2A service returns unless a generator is
  configured.

* ``gemini`` - generates prose from the retrieved passages under a strict
  grounding instruction, then *measures* groundedness and refuses below 0.85
  rather than assuming the instruction was obeyed.

Callers that own their own LLM - the Policy Specialist agent in SDD §3.2, for
instance - normally want ``extractive`` output plus the raw chunks, and do their
own generation. That is the shape the A2A `policy_search` skill returns.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

from src.grounding.policy_rag.config import Config
from src.grounding.policy_rag.documents import Citation, Hit
from src.grounding.policy_rag.guards import GuardAction, GuardDecision, redact_placeholders
from src.grounding.policy_rag.retriever import RetrievalResult, tokenize

logger = logging.getLogger(__name__)

#: SDD §3.3 Path 1, generation half of the dual gate.
GROUNDEDNESS_GATE = 0.85

REFUSAL_TEXT = (
    "I could not find that in the Altostrat Singapore employee handbook, so I would rather "
    "not guess. Please check with People Ops."
)


@dataclass
class Answer:
    text: str
    decision: str
    citations: list[Citation] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    relevance: float = 0.0
    groundedness: float = 0.0
    notices: list[str] = field(default_factory=list)
    reason: str | None = None
    composer: str = "extractive"
    #: The retrieval that produced this answer. Attached by the service so an
    #: evaluation harness can see the rejected hits and the pre-gate best score
    #: without re-running the query.
    retrieval: RetrievalResult | None = None

    @property
    def answered(self) -> bool:
        return self.decision == GuardAction.ANSWER.value

    @property
    def action(self) -> str:
        """Alias for `decision`, matching the `GuardAction` vocabulary."""
        return self.decision

    def to_dict(self) -> dict:
        return {
            "answer": self.text,
            "decision": self.decision,
            "reason": self.reason,
            "relevance": round(self.relevance, 4),
            "groundedness": round(self.groundedness, 4),
            "composer": self.composer,
            "notices": list(self.notices),
            "citations": [c.to_dict() for c in self.citations],
            "chunks": [h.to_dict() for h in self.hits],
        }


def measure_groundedness(answer_text: str, hits: list[Hit]) -> float:
    """Fraction of the answer's content words that appear in the retrieved context.

    A blunt instrument, deliberately: it cannot be gamed by fluent phrasing the
    way an LLM judge can, it needs no second model call on the critical path,
    and it fails in the safe direction - a paraphrase that introduces facts the
    context does not contain scores low. It is a floor under the answer, not a
    semantic entailment check.
    """
    answer_terms = set(tokenize(answer_text))
    if not answer_terms:
        return 0.0
    context_terms: set[str] = set()
    for hit in hits:
        context_terms.update(tokenize(hit.chunk.embedding_text()))
    supported = sum(1 for term in answer_terms if term in context_terms)
    return supported / len(answer_terms)


class ExtractiveComposer:
    """Quotes the corpus rather than paraphrasing it."""

    name = "extractive"

    def __init__(self, config: Config) -> None:
        self.config = config

    def compose(self, result: RetrievalResult, decision: GuardDecision) -> Answer:
        hits = result.hits
        blocks: list[str] = []
        for hit in hits:
            heading = hit.chunk.heading_trail
            blocks.append(f"**{hit.chunk.doc_title} - {heading}**\n\n{hit.chunk.text}")
        body = "\n\n---\n\n".join(blocks)

        body, placeholder_notices = redact_placeholders(body, self.config.guards)
        notices = list(decision.notices) + placeholder_notices

        citations = [hit.citation for hit in hits]
        text = body
        if citations:
            rendered = "\n".join(f"- [{c.title}]({c.uri})" for c in citations)
            text = f"{body}\n\n**Sources**\n{rendered}"
        if notices:
            text = f"{text}\n\n**Please note**\n" + "\n".join(f"- {n}" for n in notices)

        return Answer(
            text=text,
            decision=GuardAction.ANSWER.value,
            citations=citations,
            hits=hits,
            relevance=hits[0].relevance if hits else 0.0,
            groundedness=1.0,  # verbatim extraction
            notices=notices,
            composer=self.name,
        )


class GeminiComposer:
    """Grounded generation via the Gemini API, with a measured groundedness gate."""

    name = "gemini"
    DEFAULT_MODEL = "gemini-2.5-flash"

    SYSTEM_INSTRUCTION = (
        "You answer questions about the Altostrat Singapore employee policy handbook.\n"
        "Rules, in priority order:\n"
        "1. Use ONLY the numbered policy extracts provided. Never use outside knowledge.\n"
        "2. If the extracts do not contain the answer, say so plainly. Do not infer, "
        "estimate, or generalise from a related policy.\n"
        "3. Quote figures, day counts and monetary caps exactly as written.\n"
        "4. Cite the extract number inline, e.g. [1], for every factual claim.\n"
        "5. Be concise. Answer the question asked, not the topic around it."
    )

    def __init__(self, config: Config, model: str | None = None) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError("composer 'gemini' needs google-genai: pip install google-genai") from exc
        self.config = config
        self.model = model or os.environ.get("POLICY_RAG_GENERATOR_MODEL", self.DEFAULT_MODEL)
        self._client = genai.Client()
        self._fallback = ExtractiveComposer(config)

    @staticmethod
    def _context_block(hits: list[Hit]) -> str:
        parts = []
        for i, hit in enumerate(hits, start=1):
            parts.append(f"[{i}] {hit.chunk.doc_title} - {hit.chunk.heading_trail}\n{hit.chunk.text}")
        return "\n\n".join(parts)

    def compose(self, result: RetrievalResult, decision: GuardDecision) -> Answer:
        hits = result.hits
        prompt = (
            f"{self._context_block(hits)}\n\n"
            f"Question: {result.query}\n\n"
            "Answer using only the extracts above."
        )
        try:
            from google.genai import types

            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.SYSTEM_INSTRUCTION,
                    temperature=0.0,
                ),
            )
            generated = (response.text or "").strip()
        except Exception:  # pragma: no cover - network path
            # NFR-4.1: degrade to something correct, never to a fabricated answer.
            logger.exception("generation failed; falling back to extractive composition")
            answer = self._fallback.compose(result, decision)
            answer.notices.append("Generated prose was unavailable; showing the source extracts instead.")
            return answer

        if not generated:
            return self._fallback.compose(result, decision)

        groundedness = measure_groundedness(generated, hits)
        if groundedness < GROUNDEDNESS_GATE:
            logger.warning("groundedness %.2f below gate; refusing generated answer", groundedness)
            return Answer(
                text=REFUSAL_TEXT,
                decision=GuardAction.REFUSE.value,
                reason="groundedness_gate",
                hits=hits,
                relevance=hits[0].relevance if hits else 0.0,
                groundedness=groundedness,
                composer=self.name,
            )

        generated, placeholder_notices = redact_placeholders(generated, self.config.guards)
        notices = list(decision.notices) + placeholder_notices
        citations = [hit.citation for hit in hits]

        text = generated
        if citations:
            rendered = "\n".join(f"- [{i}] [{c.title}]({c.uri})" for i, c in enumerate(citations, start=1))
            text = f"{generated}\n\n**Sources**\n{rendered}"
        if notices:
            text = f"{text}\n\n**Please note**\n" + "\n".join(f"- {n}" for n in notices)

        return Answer(
            text=text,
            decision=GuardAction.ANSWER.value,
            citations=citations,
            hits=hits,
            relevance=hits[0].relevance if hits else 0.0,
            groundedness=groundedness,
            notices=notices,
            composer=self.name,
        )


def build_composer(config: Config, name: str | None = None):
    chosen = (name or os.environ.get("POLICY_RAG_COMPOSER", "extractive")).lower()
    if chosen == "extractive":
        return ExtractiveComposer(config)
    if chosen == "gemini":
        return GeminiComposer(config)
    raise ValueError(f"unknown composer: {chosen!r}")
