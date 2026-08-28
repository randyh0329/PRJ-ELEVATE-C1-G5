"""The façade every caller uses: retrieve -> guard -> compose.

`PolicyRagService` is the only object the A2A layer, the CLI and the evaluation
harness talk to. Keeping the order fixed here - and nowhere else - is what makes
"a guard cannot be skipped" a structural property rather than a convention.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.grounding.policy_rag import guards
from src.grounding.policy_rag.answer import REFUSAL_TEXT, Answer, ExtractiveComposer, build_composer
from src.grounding.policy_rag.config import GENERAL_ENTITLEMENT, Config, load_config
from src.grounding.policy_rag.embeddings import EmbeddingProvider, build_provider
from src.grounding.policy_rag.guards import GuardAction
from src.grounding.policy_rag.index import PolicyIndex
from src.grounding.policy_rag.multilingual import localize, understand
from src.grounding.policy_rag.retriever import RetrievalRequest, RetrievalResult, Retriever

logger = logging.getLogger(__name__)


class PolicyRagService:
    def __init__(
        self,
        config: Config,
        index: PolicyIndex,
        embedder: EmbeddingProvider,
        composer=None,
    ) -> None:
        self.config = config
        self.index = index
        self.retriever = Retriever(config, index, embedder)
        self.composer = composer or ExtractiveComposer(config)

    @classmethod
    def from_config(
        cls,
        config_path: str | Path | Config | None = None,
        composer: str | None = None,
    ) -> PolicyRagService:
        # An already-loaded `Config` is accepted so a caller that needs to read
        # settings before constructing the service - the eval harness reads the
        # gate - does not have to parse the YAML twice.
        config = config_path if isinstance(config_path, Config) else load_config(config_path)
        index = PolicyIndex.load(config.index.path)
        embedder = build_provider(config.embedding)
        return cls(config, index, embedder, build_composer(config, composer))

    # --- retrieval only -----------------------------------------------------

    def search(
        self,
        query: str,
        *,
        entitlements: list[str] | None = None,
        top_k: int | None = None,
        corpora: list[str] | None = None,
        doc_types: list[str] | None = None,
        relevance_gate: float | None = None,
        language: str | None = None,
    ) -> RetrievalResult:
        """Retrieve against the index, reading the query in whatever language it is in.

        `language` pins the answer language - pass an `Accept-Language` primary
        tag if the caller has one. Any BCP-47 tag is accepted; there is no
        supported-language list to be outside of. Left `None`, the language is
        read from the query, by Gemini where it is reachable and by the script
        census where it is not.
        """
        reading = understand(query, language)
        if reading.translated:
            logger.info(
                "searching %s query as English: %r -> %r",
                reading.language.code, query, reading.search_text,
            )
        return self.retriever.retrieve(
            RetrievalRequest(
                query=query,
                top_k=top_k,
                entitlements=entitlements or [GENERAL_ENTITLEMENT],
                corpora=corpora,
                doc_types=doc_types,
                relevance_gate=relevance_gate,
                language=reading.language.code,
                search_text=reading.search_text,
            )
        )

    # --- retrieval + guards + composition -----------------------------------

    def answer(
        self,
        query: str,
        *,
        entitlements: list[str] | None = None,
        top_k: int | None = None,
        corpora: list[str] | None = None,
        doc_types: list[str] | None = None,
        relevance_gate: float | None = None,
        language: str | None = None,
    ) -> Answer:
        result = self.search(
            query,
            entitlements=entitlements,
            top_k=top_k,
            corpora=corpora,
            doc_types=doc_types,
            relevance_gate=relevance_gate,
            language=language,
        )
        # Guards run on the English rendering as well as the raw query: their
        # keyword lists are English, and a Korean contractor asking about leave
        # must not walk past the `extended_workforce_leave` escalation simply
        # because the trigger word was in the half of the query the guard could
        # not read. Both are checked; the stricter outcome wins by construction,
        # since a guard that fires on either text fires.
        decision = guards.evaluate(query, result.hits, self.config.guards)
        if result.search_text and result.search_text != query:
            translated_decision = guards.evaluate(
                result.search_text, result.hits, self.config.guards
            )
            if translated_decision.action is not GuardAction.ANSWER:
                decision = translated_decision

        # Every fixed string below is the employee's to read, so it goes out in
        # their language. A refusal they cannot read is indistinguishable from a
        # broken service - and a refusal is the response they are most likely to
        # get when something has already gone wrong.
        if decision.action is GuardAction.ESCALATE:
            return Answer(
                text=localize(decision.message or REFUSAL_TEXT, result.language),
                decision=decision.action.value,
                reason=decision.reason,
                hits=result.hits,
                relevance=result.best_relevance,
                notices=decision.notices,
                composer=self.composer.name,
                retrieval=result,
            )

        if decision.action is GuardAction.REFUSE or not result.passed_gate:
            # FR-5.4 strict grounding: below the retrieval gate the honest
            # answer is "not covered", never a best guess from a weak match.
            return Answer(
                text=localize(REFUSAL_TEXT, result.language),
                decision=GuardAction.REFUSE.value,
                reason=decision.reason or "below_relevance_gate",
                relevance=result.best_relevance,
                composer=self.composer.name,
                retrieval=result,
            )

        answer = self.composer.compose(result, decision)
        answer.retrieval = result
        return answer

    # --- introspection ------------------------------------------------------

    def stats(self) -> dict:
        return self.index.stats()
