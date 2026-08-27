"""Retrieval: ACL filtering, hybrid scoring, the relevance gate and citations.

The scoring here is deliberately hybrid. A bi-encoder alone is weak on the two
query shapes HR Q&A produces most often - exact figures ("14 days", "US$100")
and section references ("Section 20") - because those are lexical facts, not
semantic ones. An IDF-weighted term-overlap score is fused with the dense score
to cover them.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from src.grounding.policy_rag.chunking import slugify
from src.grounding.policy_rag.config import GENERAL_ENTITLEMENT, Config
from src.grounding.policy_rag.documents import Chunk, Citation, Hit
from src.grounding.policy_rag.embeddings import EmbeddingProvider
from src.grounding.policy_rag.index import PolicyIndex

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9$%.-]*")
_STOPWORDS = frozenset(
    ["a", "an", "and", "any", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "how", "i", "if", "in", "into", "is", "it", "may", "me", "my", "not", "of", "on", "or", "our", "should", "so", "that", "the", "their", "there", "they", "this", "to", "us", "was", "we", "what", "when", "where", "which", "who", "will", "with", "would", "you", "your"]
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


@dataclass
class RetrievalRequest:
    query: str
    top_k: int | None = None
    #: Entitlements held by the caller. Chunks requiring anything else are
    #: invisible - the query-time filter of SDD §4.7, which is the authoritative
    #: control, not the index-side ACL.
    entitlements: list[str] = field(default_factory=lambda: [GENERAL_ENTITLEMENT])
    #: Corpus ids to search. `None` means the config's default search set.
    corpora: list[str] | None = None
    doc_types: list[str] | None = None
    #: Override the configured relevance gate (evaluation harness use only).
    relevance_gate: float | None = None


@dataclass
class RetrievalResult:
    query: str
    hits: list[Hit]
    #: Hits that scored below the gate, retained for observability. Never shown
    #: to a caller as an answer.
    rejected: list[Hit]
    gate: float
    #: Best relevance seen before gating, including rejected hits.
    best_relevance: float
    searched_corpora: list[str]

    @property
    def passed_gate(self) -> bool:
        return bool(self.hits)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "gate": self.gate,
            "best_relevance": round(self.best_relevance, 4),
            "passed_gate": self.passed_gate,
            "searched_corpora": self.searched_corpora,
            "hits": [h.to_dict() for h in self.hits],
            "rejected_count": len(self.rejected),
        }


class Retriever:
    def __init__(self, config: Config, index: PolicyIndex, embedder: EmbeddingProvider) -> None:
        expected = index.manifest.embedder_fingerprint
        actual = embedder.fingerprint()
        if expected != actual:
            raise RuntimeError(
                f"index was built with embedder {expected!r} but {actual!r} is loaded. "
                "Re-run ingest, or set POLICY_RAG_EMBEDDING_PROVIDER to match."
            )
        self.config = config
        self.index = index
        self.embedder = embedder
        self._idf = self._build_idf(index)

    # --- lexical side -------------------------------------------------------

    @staticmethod
    def _build_idf(index: PolicyIndex) -> dict[str, float]:
        document_frequency: Counter[str] = Counter()
        total = 0
        for chunk in index.chunks:
            total += 1
            document_frequency.update(set(tokenize(chunk.embedding_text())))
        if total == 0:
            return {}
        return {
            term: math.log(1.0 + (total - freq + 0.5) / (freq + 0.5))
            for term, freq in document_frequency.items()
        }

    def _lexical_score(self, query_terms: list[str], chunk: Chunk) -> float:
        if not query_terms:
            return 0.0
        chunk_terms = set(tokenize(chunk.embedding_text()))
        # Unknown query terms carry the IDF of a term seen once - an unmatched
        # rare word should cost more than an unmatched common one.
        default_idf = max(self._idf.values(), default=1.0)
        total = sum(self._idf.get(term, default_idf) for term in query_terms)
        matched = sum(self._idf.get(term, default_idf) for term in query_terms if term in chunk_terms)
        return matched / total if total else 0.0

    # --- calibration --------------------------------------------------------

    def _calibrate(self, cosine: float) -> float:
        cfg = self.config.retrieval
        span = cfg.cosine_ceiling - cfg.cosine_floor
        if span <= 0:
            return max(0.0, min(1.0, cosine))
        return max(0.0, min(1.0, (cosine - cfg.cosine_floor) / span))

    def _fuse(self, cosine: float, lexical: float) -> float:
        """Calibrated cosine, lifted by lexical corroboration.

        Not a weighted average of the two. Under an average, a passage that is
        semantically exactly right is *penalised* for phrasing the rule in words
        the question did not use - which is the normal case for policy text, and
        the reason the first calibration of this service could not put a correct
        top-1 hit above the gate. Lexical overlap is corroborating evidence: its
        presence should raise confidence, its absence should not be read as
        evidence of irrelevance.

        The lift is proportional to the headroom left, so the score saturates at
        1.0 and a weak dense match cannot be dragged over the gate by keyword
        overlap alone.
        """
        cfg = self.config.retrieval
        dense = self._calibrate(cosine)
        return dense + cfg.lexical_boost * lexical * (1.0 - dense)

    def _rank_score(self, cosine: float, lexical: float) -> float:
        """Ordering signal: the same fusion applied to the *uncalibrated* cosine.

        Calibration clips at `cosine_ceiling`, which is what makes the gate
        comparable to the SDD's 0.80 - but it also flattens every strong hit to
        exactly 1.0, and sorting on a flattened score discards precisely the
        resolution that decides which passage leads the answer. So the gate uses
        the calibrated score and the ordering uses this one.
        """
        cfg = self.config.retrieval
        return cosine + cfg.lexical_boost * lexical * (1.0 - cosine)

    # --- citations ----------------------------------------------------------

    def _citation_for(self, chunk: Chunk) -> Citation:
        uri = f"{chunk.path}#{chunk.anchor}" if chunk.anchor else chunk.path
        primary = chunk.sources[0] if chunk.sources else None
        citation = Citation(
            title=f"{chunk.doc_title} - {chunk.heading_trail}" if chunk.heading_path else chunk.doc_title,
            uri=uri,
            source_title=primary.title if primary else None,
            source_uri=primary.resource if primary else None,
        )
        citation.resolved = _citation_resolves(self.config.repo_root, chunk.path, chunk.anchor)
        return citation

    # --- main entry point ---------------------------------------------------

    def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        cfg = self.config.retrieval
        top_k = request.top_k or cfg.top_k
        gate = request.relevance_gate if request.relevance_gate is not None else cfg.relevance_gate
        corpora = set(request.corpora or self.config.default_corpora)
        doc_types = set(request.doc_types or cfg.default_doc_types)
        entitlements = set(request.entitlements or [GENERAL_ENTITLEMENT])

        query_vector = self.embedder.encode_query(request.query)
        query_terms = tokenize(request.query)

        # Over-fetch: ACL, corpus and doc-type filters all cut candidates, and
        # FAISS cannot express them, so the filtering happens after the search.
        candidates = self.index.search(query_vector, cfg.candidate_k)

        scored: list[Hit] = []
        for chunk, cosine in candidates:
            if chunk.corpus_id not in corpora:
                continue
            if chunk.doc_type not in doc_types:
                continue
            if chunk.entitlement not in entitlements:
                continue
            lexical = self._lexical_score(query_terms, chunk)
            scored.append(
                Hit(
                    chunk=chunk,
                    dense_score=cosine,
                    lexical_score=lexical,
                    relevance=self._fuse(cosine, lexical),
                    citation=self._citation_for(chunk),
                )
            )

        scored.sort(key=lambda h: self._rank_score(h.dense_score, h.lexical_score), reverse=True)
        # Max, not `scored[0]`: the list is ordered by rank score, and the two
        # orderings can differ in the saturated region.
        best = max((h.relevance for h in scored), default=0.0)

        accepted: list[Hit] = []
        rejected: list[Hit] = []
        per_document: Counter[str] = Counter()
        for hit in scored:
            if hit.relevance < gate:
                rejected.append(hit)
                continue
            # FR-5.3: a citation that does not resolve is not a citation. A hit
            # we cannot point at is dropped rather than shown unattributed.
            if not hit.citation.resolved:
                logger.warning("dropping hit with unresolvable citation: %s", hit.citation.uri)
                rejected.append(hit)
                continue
            if per_document[hit.chunk.doc_id] >= cfg.max_chunks_per_document:
                continue
            per_document[hit.chunk.doc_id] += 1
            accepted.append(hit)
            if len(accepted) >= top_k:
                break

        return RetrievalResult(
            query=request.query,
            hits=accepted,
            rejected=rejected,
            gate=gate,
            best_relevance=best,
            searched_corpora=sorted(corpora),
        )


@lru_cache(maxsize=4096)
def _citation_resolves(repo_root: Path, path: str, anchor: str) -> bool:
    """Citation integrity check (FR-5.4): does `path#anchor` actually exist?"""
    target = repo_root / path
    if not target.is_file():
        return False
    if not anchor:
        return True
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        stripped = line.strip()
        heading = ""
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
        elif stripped.startswith("**") and stripped.count("**") >= 2:
            heading = stripped.split("**")[1].strip()
        if heading and slugify(heading) == anchor:
            return True
    return False
