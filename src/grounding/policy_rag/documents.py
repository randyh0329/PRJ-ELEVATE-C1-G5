"""Corpus data model.

One `Document` is one source file. One `Chunk` is one retrievable unit carrying
everything a citation needs, so nothing downstream has to re-open the source.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


# Chunk ids are stable content-addressed strings; FAISS needs int64 labels, so
# `Chunk.vector_id` derives one from the same hash. 63 bits of SHA-1 is far more
# than a corpus of this size can collide on, and the derivation is deterministic
# so a rebuild produces identical labels.
def _stable_id(*parts: str) -> str:
    digest = hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def _vector_id(chunk_id: str) -> int:
    return int(chunk_id, 16) & 0x7FFF_FFFF_FFFF_FFFF


@dataclass(frozen=True)
class SourceRef:
    """One entry of an OKF `sources:` frontmatter block."""

    id: str
    title: str
    resource: str
    last_modified: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "resource": self.resource,
            "last_modified": self.last_modified,
        }


@dataclass
class Document:
    """A single ingested source file, before chunking."""

    doc_id: str
    corpus_id: str
    #: Repo-relative path, e.g. `okf/altostrat-sg-handbook/leave/vacation.md`.
    path: str
    title: str
    #: policy | datasheet | computation | reference | skill | nav | code | handbook
    doc_type: str
    #: governing | source
    authority: str
    #: Entitlement required to retrieve any chunk of this document.
    entitlement: str
    body: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    status: str = "unknown"
    stale_after: str | None = None
    sources: list[SourceRef] = field(default_factory=list)
    #: Footnote label -> human-readable source line, from the tail of OKF concepts.
    footnotes: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """A retrievable unit of a document."""

    chunk_id: str
    doc_id: str
    corpus_id: str
    path: str
    doc_title: str
    doc_type: str
    authority: str
    entitlement: str
    #: Heading trail from the document root, e.g. ["Carryover and payout"].
    heading_path: list[str]
    #: URL fragment for the deep link, derived from the last heading.
    anchor: str
    text: str
    ordinal: int
    tags: list[str] = field(default_factory=list)
    status: str = "unknown"
    stale_after: str | None = None
    #: Source refs actually footnoted inside this chunk, narrowed from the
    #: document-level list so a citation points at the section that was used.
    sources: list[SourceRef] = field(default_factory=list)
    #: True when the chunk sits under a `# Conflict...` heading - the corpus
    #: datasheet forbids answering from these, they must be escalated.
    is_conflict: bool = False
    #: True when the chunk sits under a `# Gaps in the source` heading.
    is_gap: bool = False

    @property
    def vector_id(self) -> int:
        return _vector_id(self.chunk_id)

    @property
    def heading_trail(self) -> str:
        return " > ".join(self.heading_path) if self.heading_path else self.doc_title

    def embedding_text(self) -> str:
        """What actually gets embedded.

        The heading trail and document title are prepended because a chunk like
        "Unused days carry over for exactly one additional year" is meaningless
        to a bi-encoder without the words "Vacation Leave" nearby.
        """
        header = self.doc_title
        if self.heading_path:
            header = f"{self.doc_title} - {' > '.join(self.heading_path)}"
        return f"{header}\n\n{self.text}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "corpus_id": self.corpus_id,
            "path": self.path,
            "doc_title": self.doc_title,
            "doc_type": self.doc_type,
            "authority": self.authority,
            "entitlement": self.entitlement,
            "heading_path": self.heading_path,
            "anchor": self.anchor,
            "text": self.text,
            "ordinal": self.ordinal,
            "tags": self.tags,
            "status": self.status,
            "stale_after": self.stale_after,
            "sources": [s.to_dict() for s in self.sources],
            "is_conflict": self.is_conflict,
            "is_gap": self.is_gap,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Chunk:
        return cls(
            chunk_id=raw["chunk_id"],
            doc_id=raw["doc_id"],
            corpus_id=raw["corpus_id"],
            path=raw["path"],
            doc_title=raw["doc_title"],
            doc_type=raw["doc_type"],
            authority=raw["authority"],
            entitlement=raw["entitlement"],
            heading_path=list(raw["heading_path"]),
            anchor=raw["anchor"],
            text=raw["text"],
            ordinal=raw["ordinal"],
            tags=list(raw.get("tags", [])),
            status=raw.get("status", "unknown"),
            stale_after=raw.get("stale_after"),
            sources=[SourceRef(**s) for s in raw.get("sources", [])],
            is_conflict=raw.get("is_conflict", False),
            is_gap=raw.get("is_gap", False),
        )


def make_chunk_id(doc_id: str, heading_path: list[str], ordinal: int) -> str:
    """Content-addressed chunk id.

    Keyed on `doc_id` rather than on the source path: the handbook loader emits
    one document per numbered SECTION, so several documents share a path and
    each restarts its own ordinal counter.
    """
    return _stable_id(doc_id, "/".join(heading_path), str(ordinal))


@dataclass
class Citation:
    """A resolvable pointer to the exact section an answer came from (FR-5.3)."""

    title: str
    #: Deep link into the corpus document, `path#anchor`.
    uri: str
    #: The handbook section the OKF concept traces back to, when known.
    source_title: str | None = None
    source_uri: str | None = None
    #: Set by the citation integrity check in retriever.py.
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "uri": self.uri,
            "source_title": self.source_title,
            "source_uri": self.source_uri,
            "resolved": self.resolved,
        }


@dataclass
class Hit:
    """A scored retrieval result."""

    chunk: Chunk
    #: Raw cosine similarity from FAISS.
    dense_score: float
    #: Lexical overlap score in [0, 1].
    lexical_score: float
    #: Fused, calibrated score in [0, 1] - what the relevance gate compares against.
    relevance: float
    citation: Citation

    def to_dict(self) -> dict[str, Any]:
        return {
            "chunk_id": self.chunk.chunk_id,
            "path": self.chunk.path,
            "doc_title": self.chunk.doc_title,
            "heading": self.chunk.heading_trail,
            "text": self.chunk.text,
            "authority": self.chunk.authority,
            "status": self.chunk.status,
            "dense_score": round(self.dense_score, 4),
            "lexical_score": round(self.lexical_score, 4),
            "relevance": round(self.relevance, 4),
            "citation": self.citation.to_dict(),
        }
