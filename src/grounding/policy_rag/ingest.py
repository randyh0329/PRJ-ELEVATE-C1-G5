"""Corpus ingestion: load -> chunk -> embed -> write FAISS index.

Corresponds to the `policy-ingestion` component in SDD §3.2.1. The equivalent
of that component's Eventarc trigger is running this module; the equivalent of
its canary verification probe is `verify_index`, which is called at the end of
every build and fails the ingest rather than publishing a broken index.
"""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.grounding.policy_rag.chunking import chunk_document
from src.grounding.policy_rag.config import Config
from src.grounding.policy_rag.documents import Chunk, Document
from src.grounding.policy_rag.embeddings import build_provider
from src.grounding.policy_rag.index import IndexManifest, PolicyIndex
from src.grounding.policy_rag.loaders import load_corpus
from src.grounding.policy_rag.retriever import RetrievalRequest, Retriever

logger = logging.getLogger(__name__)


@dataclass
class IngestReport:
    documents: int = 0
    chunks: int = 0
    by_corpus: dict[str, int] = field(default_factory=dict)
    by_doc_type: dict[str, int] = field(default_factory=dict)
    skipped_empty: list[str] = field(default_factory=list)
    index_path: str = ""
    embedder: str = ""

    def render(self) -> str:
        lines = [
            f"Indexed {self.chunks} chunks from {self.documents} documents",
            f"  embedder : {self.embedder}",
            f"  index    : {self.index_path}",
            "  by corpus:",
        ]
        lines += [f"    {k:<20} {v}" for k, v in sorted(self.by_corpus.items())]
        lines.append("  by doc type:")
        lines += [f"    {k:<20} {v}" for k, v in sorted(self.by_doc_type.items())]
        if self.skipped_empty:
            lines.append(f"  produced no chunks ({len(self.skipped_empty)}):")
            lines += [f"    {p}" for p in self.skipped_empty]
        return "\n".join(lines)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_documents(config: Config) -> list[Document]:
    documents: list[Document] = []
    for corpus in config.corpora:
        loaded = load_corpus(corpus, config.repo_root)
        logger.info("corpus %s: %d documents", corpus.id, len(loaded))
        documents.extend(loaded)
    return documents


def build_chunks(config: Config, documents: list[Document]) -> tuple[list[Chunk], list[str]]:
    chunks: list[Chunk] = []
    skipped: list[str] = []
    seen: set[str] = set()

    for document in documents:
        produced = chunk_document(document, config.chunking)
        if not produced:
            skipped.append(document.path)
            continue
        for chunk in produced:
            # Chunk ids are content-addressed on (corpus, path, headings,
            # ordinal). The handbook loader emits several documents from one
            # path, so a collision here means the ordinal counter was reused -
            # worth failing loudly rather than silently dropping a chunk.
            if chunk.chunk_id in seen:
                raise ValueError(f"duplicate chunk id {chunk.chunk_id} at {chunk.path}")
            seen.add(chunk.chunk_id)
        chunks.extend(produced)

    return chunks, skipped


def verify_index(config: Config, index: PolicyIndex, embedder, probes: list[tuple[str, str]]) -> None:
    """Canary probe: each query must retrieve its expected document.

    Mirrors SDD §4.7 step 5. A build that cannot answer questions whose answers
    are definitely in the corpus is broken, and publishing it would turn a
    retrieval defect into a wrong answer in production.

    The probes run through the full `Retriever` rather than a bare index scan,
    so they exercise the corpus filter, the doc-type filter and the relevance
    gate exactly as a served query would.
    """
    retriever = Retriever(config, index, embedder)
    failures: list[str] = []
    for query, expected_path_fragment in probes:
        result = retriever.retrieve(RetrievalRequest(query=query, top_k=5))
        paths = [hit.chunk.path for hit in result.hits]
        if not any(expected_path_fragment in p for p in paths):
            failures.append(
                f"{query!r} -> expected {expected_path_fragment}, got {paths or '[gate rejected everything]'} "
                f"(best relevance {result.best_relevance:.3f})"
            )
    if failures:
        raise RuntimeError("index verification probe failed:\n  " + "\n  ".join(failures))


#: Questions whose answers are unambiguously in the corpus, one per top-level
#: OKF folder. Cheap, and it catches an empty or mis-embedded index immediately.
DEFAULT_PROBES: list[tuple[str, str]] = [
    ("How many days of paid vacation leave do I get after 8 years of service?", "leave/vacation.md"),
    ("How many days of outpatient sick leave am I entitled to?", "leave/sick-and-hospitalisation.md"),
    ("What is the gift value threshold that needs pre-approval?", "ethics/"),
    ("Can I have a romantic relationship with someone I manage?", "conduct/personal-relationships.md"),
    ("What is the lodging cap when I travel for work?", "workplace/travel-and-expense.md"),
    ("How do I claim on the company health insurance?", "people-ops/health-insurance.md"),
]


def ingest(config: Config, *, verify: bool = True) -> IngestReport:
    documents = collect_documents(config)
    chunks, skipped = build_chunks(config, documents)
    if not chunks:
        raise RuntimeError("ingestion produced no chunks - check corpus paths in config/corpus.yaml")

    embedder = build_provider(config.embedding)
    logger.info("embedding %d chunks with %s", len(chunks), embedder.fingerprint())
    vectors = embedder.encode([c.embedding_text() for c in chunks])
    if vectors.shape[0] != len(chunks):
        raise RuntimeError("embedder returned the wrong number of vectors")

    by_corpus = Counter(c.corpus_id for c in chunks)
    by_doc_type = Counter(c.doc_type for c in chunks)

    source_digests: dict[str, str] = {}
    for path in sorted({d.path for d in documents}):
        absolute = config.repo_root / path
        if absolute.is_file():
            source_digests[path] = _digest(absolute)

    manifest = IndexManifest(
        embedder_fingerprint=embedder.fingerprint(),
        dimension=int(vectors.shape[1]),
        index_type=config.index.type,
        chunk_count=len(chunks),
        document_count=len(documents),
        built_at=datetime.now(timezone.utc).isoformat(),
        corpora=dict(by_corpus),
        source_digests=source_digests,
    )

    index = PolicyIndex.build(chunks, np.asarray(vectors, dtype=np.float32), config.index, manifest)

    if verify:
        if config.embedding.provider == "hash":
            # The hash embedder is a hermetic test fixture with no semantic
            # signal; holding it to the retrieval probes would be meaningless.
            logger.warning("skipping verification probes: embedding provider is 'hash'")
        else:
            verify_index(config, index, embedder, DEFAULT_PROBES)

    index.save(config.index.path)

    return IngestReport(
        documents=len(documents),
        chunks=len(chunks),
        by_corpus=dict(by_corpus),
        by_doc_type=dict(by_doc_type),
        skipped_empty=skipped,
        index_path=str(config.index.path),
        embedder=embedder.fingerprint(),
    )


def detect_drift(config: Config) -> list[str]:
    """Return source paths whose content no longer matches the built index.

    The cheap, offline half of SLA-07: an operator (or a CI job) can tell that a
    policy changed without re-embedding the corpus to find out.
    """
    index = PolicyIndex.load(config.index.path)
    drifted: list[str] = []
    for path, digest in index.manifest.source_digests.items():
        absolute = config.repo_root / path
        if not absolute.is_file():
            drifted.append(f"{path} (deleted)")
        elif _digest(absolute) != digest:
            drifted.append(f"{path} (modified)")

    known = set(index.manifest.source_digests)
    for document in collect_documents(config):
        if document.path not in known:
            drifted.append(f"{document.path} (new)")
            known.add(document.path)

    return drifted
