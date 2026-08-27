"""FAISS implementation of the `BaseRAGPipeline` contract.

`rag_boilerplate.VertexAISearchRAGBoilerplate` declares the same interface
against Vertex AI Search and raises `NotImplementedError` - that integration is
deferred beyond the MVP 1 baseline. This is a working local implementation of
the same two methods, backed by `src.grounding.policy_rag`: an exact-cosine
FAISS index over the Altostrat Singapore handbook and its OKF v0.2 bundle.

Both are `BaseRAGPipeline`, so a caller can be pointed at either without
changing its own code. The differences that matter to a caller:

* `index_documents` takes corpus ids declared in `config/corpus.yaml`, not
  arbitrary GCS URIs. Nothing may introduce a corpus at runtime - the same
  discipline SDD §3.2 applies to the agent/tool registry.
* `semantic_search` applies the SDD §4.7 query-time ACL filter. `entitlements`
  must come from the verified caller; see `policy_rag.a2a_app.executor`.

The index is loaded lazily on first use and cached, because it is a read-only
artefact and the embedding-model load is the expensive part.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.grounding.policy_rag.config import GENERAL_ENTITLEMENT, Config
from src.grounding.policy_rag.service import PolicyRagService
from src.grounding.rag_boilerplate import BaseRAGPipeline, RAGDocumentChunk

logger = logging.getLogger("grounding.faiss_pipeline")


class FaissPolicyRAG(BaseRAGPipeline):
    """Local FAISS vector search over the curated handbook corpora."""

    def __init__(
        self,
        config: Optional[Config] = None,
        service: Optional[PolicyRagService] = None,
    ) -> None:
        self._config = config
        self._service = service

    @property
    def service(self) -> PolicyRagService:
        """The underlying RAG service, loaded on first access."""
        if self._service is None:
            self._service = PolicyRagService.from_config(self._config)
        return self._service

    @property
    def is_ready(self) -> bool:
        """Whether the index is loadable, without raising if it is not.

        The index is a build artefact, absent until `policy-rag ingest` has run.
        A caller deciding whether to route to semantic search needs to ask that
        question without taking an exception.
        """
        try:
            return len(self.service.index) > 0
        except Exception:
            logger.warning("policy RAG index unavailable; run `python -m src.grounding.policy_rag.cli ingest`")
            return False

    async def index_documents(self, gcs_uris: List[str]) -> bool:
        """Rebuild the FAISS index from the corpora declared in config/corpus.yaml.

        The parameter keeps the `BaseRAGPipeline` signature, but this pipeline
        does not read from Cloud Storage - its corpora are files in the
        repository. It is read as a list of corpus ids, which are validated
        against the config so that a caller naming something that does not exist
        is told rather than handed a silently unchanged index.

        The build is always full, even when a subset is named. The index is a
        single artefact rebuilt from scratch, so building only `handbook` would
        *evict* the OKF bundle rather than refresh one corpus in place; a full
        rebuild is the only outcome that leaves retrieval correct.
        """
        from src.grounding.policy_rag.config import load_config
        from src.grounding.policy_rag.ingest import ingest

        config = self._config if isinstance(self._config, Config) else load_config(self._config)
        requested = set(gcs_uris or [])
        declared = {c.id for c in config.corpora}
        undeclared = requested - declared
        if undeclared:
            raise ValueError(f"undeclared corpus id(s): {sorted(undeclared)}; known: {sorted(declared)}")
        if requested and requested != declared:
            logger.info("rebuilding all of %s, not just %s", sorted(declared), sorted(requested))

        ingest(config)
        self._service = None  # force a reload of the rebuilt index
        return True

    async def semantic_search(
        self,
        query: str,
        top_k: int = 5,
        entitlements: Optional[List[str]] = None,
    ) -> List[RAGDocumentChunk]:
        """Dense + lexical retrieval, ACL-filtered, above the relevance gate.

        Returns only hits that cleared `retrieval.relevance_gate`, so an empty
        list means "nothing in the corpus is a good enough match" - which is a
        refusal signal, not an error (BRD FR-5.4 / NFR-3.1).
        """
        result = self.service.search(
            query,
            entitlements=entitlements or [GENERAL_ENTITLEMENT],
            top_k=top_k,
        )
        return [
            RAGDocumentChunk(
                chunk_id=hit.chunk.chunk_id,
                content=hit.chunk.text,
                document_uri=hit.citation.uri,
                similarity_score=hit.relevance,
                metadata=self._metadata(hit),
            )
            for hit in result.hits
        ]

    @staticmethod
    def _metadata(hit) -> Dict[str, Any]:
        """Provenance a citation-rendering caller needs, without the Hit type."""
        return {
            "doc_title": hit.chunk.doc_title,
            "heading": hit.chunk.heading_trail,
            "path": hit.chunk.path,
            "corpus_id": hit.chunk.corpus_id,
            "authority": hit.chunk.authority,
            "status": hit.chunk.status,
            "entitlement": hit.chunk.entitlement,
            "citation_title": hit.citation.title,
            "citation_url": hit.citation.uri,
            "citation_resolved": hit.citation.resolved,
            "source_title": hit.citation.source_title,
            "source_uri": hit.citation.source_uri,
        }


#: Module-level pipeline, matching the `okf_store` / `dual_grounding_engine`
#: singleton convention in this package. Construction is cheap; the index is not
#: touched until the first search.
faiss_policy_rag = FaissPolicyRAG()
