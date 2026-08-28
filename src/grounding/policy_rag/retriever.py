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

from src.grounding.citations import blob_url
from src.grounding.policy_rag.chunking import slugify
from src.grounding.policy_rag.config import GENERAL_ENTITLEMENT, Config
from src.grounding.policy_rag.documents import Chunk, Citation, Hit
from src.grounding.policy_rag.embeddings import EmbeddingProvider
from src.grounding.policy_rag.index import PolicyIndex
from src.grounding.policy_rag.language import Language, cjk_terms, resolve

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9$%.-]*")
_WHITESPACE_RE = re.compile(r"\s+")
#: Inline markdown links, including the bare-autolink and image forms.
_MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\([^)]*\)|<https?://[^>]+>")
_STOPWORDS = frozenset(
    ["a", "an", "and", "any", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "how", "i", "if", "in", "into", "is", "it", "may", "me", "my", "not", "of", "on", "or", "our", "should", "so", "that", "the", "their", "there", "they", "this", "to", "us", "was", "we", "what", "when", "where", "which", "who", "will", "with", "would", "you", "your"]
)


def latin_terms(text: str) -> list[str]:
    """Word and number terms in Latin script.

    Split out from `tokenize` because this is precisely the part of a query -
    in *any* language - that an English corpus could echo back verbatim. A
    Japanese question about `Section 20` or a `US$100` cap still carries those
    terms, and they are the only lexical evidence available when the question
    and the handbook are not written in the same script. See
    `Retriever.retrieve` for the corroboration rule built on that.
    """
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


def tokenize(text: str) -> list[str]:
    """Lexical terms: Latin words and numbers, plus CJK character bigrams.

    Text containing no CJK tokenises exactly as it did before bigrams existed,
    which is what keeps the calibration constants in `config/corpus.yaml` - all
    derived against an English golden set - valid across this change.
    """
    return latin_terms(text) + cjk_terms(text)


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
    #: BCP-47-ish code pinning the query language. `None` means detect it from
    #: the text - see `language.resolve`.
    language: str | None = None


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
    #: Language the query was read as. Reported on the wire because a caller
    #: seeing an unexpected answer language needs to know whether detection or
    #: composition got it wrong.
    language: Language = field(default_factory=lambda: resolve("", "en"))

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
            "language": self.language.code,
            "cross_lingual": self.language.cross_lingual,
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
        self._link_density = {c.chunk_id: self._compute_link_density(c) for c in index.chunks}

    # --- navigational chunks ------------------------------------------------

    @staticmethod
    def _compute_link_density(chunk: Chunk) -> float:
        """Fraction of the chunk's visible characters that live inside links.

        A handbook contains two kinds of passage that read alike to an embedding
        model. One states a rule. The other is a signpost - a section index, a
        "related policies" list, an empty heading whose body is three links -
        and it is *about* the rule without stating it.

        A signpost matches a question well precisely because it repeats the
        question's topic words, so dense retrieval ranks it highly and it then
        occupies a slot that a real passage needed. Worse, when it is the only
        hit, the service either refuses a question the corpus can answer or
        cites a page that does not contain the claim, breaking FR-5.2.

        There is no reliable signal for this in the score. There is one in the
        markup: a signpost is mostly link syntax.
        """
        text = chunk.text
        visible = len(_WHITESPACE_RE.sub("", text))
        if visible == 0:
            return 0.0
        linked = sum(len(_WHITESPACE_RE.sub("", m.group(0))) for m in _MARKDOWN_LINK_RE.finditer(text))
        return min(1.0, linked / visible)

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
        """A resolvable deep link to the passage this hit came from (FR-5.3).

        Two different questions get two different answers here, and conflating
        them is how a broken citation ships. `uri` is where the *reader* goes, so
        it is a URL - `blob_url` over the repo-relative path, with the heading
        anchor preserved. `resolved` is whether the citation is *true*, so it is
        checked against the working tree, where the file either exists with that
        heading or does not.

        Emitting the bare `path#anchor` as the uri, which is what this did,
        satisfied neither: it renders as inert text in every chat client, and it
        looks identical whether the file is there or not.
        """
        primary = chunk.sources[0] if chunk.sources else None
        citation = Citation(
            title=f"{chunk.doc_title} - {chunk.heading_trail}" if chunk.heading_path else chunk.doc_title,
            uri=blob_url(chunk.path, chunk.anchor or None),
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

        language = resolve(request.query, request.language)

        query_vector = self.embedder.encode_query(request.query)
        query_terms = tokenize(request.query)
        # What the corroboration rule below is allowed to look at. For an
        # English query this is the whole term list and the rule is unchanged.
        # For a cross-lingual one it is the Latin remainder - section numbers,
        # figures, product names - because CJK bigrams cannot appear in an
        # English chunk and scoring a hit against terms it *cannot* contain
        # measures the corpus language, not the hit.
        corroborating_terms = latin_terms(request.query) if language.cross_lingual else query_terms

        # Over-fetch: ACL, corpus and doc-type filters all cut candidates, and
        # FAISS cannot express them, so the filtering happens after the search.
        candidates = self.index.search(query_vector, cfg.candidate_k)

        scored: list[Hit] = []
        #: chunk_id -> corroboration score, or None when the query offers
        #: nothing the corpus language could echo and the rule cannot run.
        corroboration: dict[str, float | None] = {}
        for chunk, cosine in candidates:
            if chunk.corpus_id not in corpora:
                continue
            if chunk.doc_type not in doc_types:
                continue
            if chunk.entitlement not in entitlements:
                continue
            # Dropped rather than rejected: a signpost is not weak evidence, it
            # is not evidence, so it should not colour `best_relevance` either.
            if self._link_density.get(chunk.chunk_id, 0.0) > cfg.max_link_density:
                continue
            lexical = self._lexical_score(query_terms, chunk)
            corroboration[chunk.chunk_id] = (
                self._lexical_score(corroborating_terms, chunk) if corroborating_terms else None
            )
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
            # A hit can clear the gate on dense similarity while sharing almost
            # no vocabulary with the question. That combination is the signature
            # of a near-miss: the same *subject* discussed under a different
            # rule. `_fuse` deliberately does not penalise missing overlap, so
            # the requirement is expressed here instead, as an admissibility
            # rule rather than a score adjustment.
            #
            # `None` means the rule has nothing to work with: a wholly CJK
            # question against an English corpus shares no vocabulary by
            # construction, so a zero here would be a fact about the two
            # languages rather than about this hit. Skipping it is a real loss
            # of safety, not a free pass - see the cross-lingual caveat in the
            # README - and it is the reason the language is reported back to
            # the caller alongside the answer.
            hit_corroboration = corroboration[hit.chunk.chunk_id]
            if hit_corroboration is not None and hit_corroboration < cfg.min_lexical_corroboration:
                logger.debug(
                    "dropping uncorroborated hit (dense %.3f, corroboration %.3f): %s",
                    hit.dense_score, hit_corroboration, hit.citation.uri,
                )
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
            language=language,
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
