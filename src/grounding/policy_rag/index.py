"""FAISS-backed vector store.

Layout on disk (`config.index.path`):

    faiss.index    the FAISS index itself
    chunks.jsonl   one JSON object per chunk, keyed by vector id
    manifest.json  build provenance: embedder fingerprint, counts, source digests

The index is an `IndexIDMap2` wrapping `IndexFlatIP`. Two reasons for that
choice over a bare flat index:

* explicit int64 labels derived from the content-addressed chunk id, so a
  rebuild produces the same labels and diffs are meaningful; and
* `remove_ids`, which is what makes `PolicyIndex.evict_document` possible - the
  stale-embedding eviction the SDD commits to in SLA-04.

`IndexFlatIP` is exact. At a few thousand chunks that is a sub-millisecond scan
and there is no recall loss to reason about; `hnsw` is available in config for
when the corpus outgrows that.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

from src.grounding.policy_rag.config import IndexConfig
from src.grounding.policy_rag.documents import Chunk

logger = logging.getLogger(__name__)

INDEX_FILENAME = "faiss.index"
CHUNKS_FILENAME = "chunks.jsonl"
MANIFEST_FILENAME = "manifest.json"


@dataclass
class IndexManifest:
    embedder_fingerprint: str
    dimension: int
    index_type: str
    chunk_count: int
    document_count: int
    built_at: str
    corpora: dict[str, int]
    #: sha256 of every ingested source file, so drift is detectable without a rebuild.
    source_digests: dict[str, str]

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, raw: dict) -> IndexManifest:
        return cls(**raw)


class PolicyIndex:
    """A FAISS index plus the chunk metadata that makes results citable."""

    def __init__(
        self,
        faiss_index: faiss.Index,
        chunks: dict[int, Chunk],
        manifest: IndexManifest,
    ) -> None:
        self._index = faiss_index
        self._chunks = chunks
        self.manifest = manifest

    # --- construction -------------------------------------------------------

    @staticmethod
    def _new_index(cfg: IndexConfig, dimension: int) -> faiss.Index:
        if cfg.type == "hnsw":
            base = faiss.IndexHNSWFlat(dimension, cfg.hnsw_m, faiss.METRIC_INNER_PRODUCT)
        elif cfg.type == "flat":
            base = faiss.IndexFlatIP(dimension)
        else:
            raise ValueError(f"unknown index type: {cfg.type!r}")
        return faiss.IndexIDMap2(base)

    @classmethod
    def build(
        cls,
        chunks: list[Chunk],
        vectors: np.ndarray,
        cfg: IndexConfig,
        manifest: IndexManifest,
    ) -> PolicyIndex:
        if len(chunks) != vectors.shape[0]:
            raise ValueError(f"chunk/vector count mismatch: {len(chunks)} vs {vectors.shape[0]}")
        if not chunks:
            raise ValueError("refusing to build an empty index")

        index = cls._new_index(cfg, vectors.shape[1])
        ids = np.array([c.vector_id for c in chunks], dtype=np.int64)
        if len(set(ids.tolist())) != len(ids):
            raise ValueError("duplicate vector ids - chunk id derivation is not unique")
        index.add_with_ids(np.ascontiguousarray(vectors, dtype=np.float32), ids)

        return cls(index, {c.vector_id: c for c in chunks}, manifest)

    # --- persistence --------------------------------------------------------

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(directory / INDEX_FILENAME))
        with (directory / CHUNKS_FILENAME).open("w", encoding="utf-8") as fh:
            for vector_id, chunk in self._chunks.items():
                fh.write(json.dumps({"vector_id": vector_id, **chunk.to_dict()}, ensure_ascii=False) + "\n")
        (directory / MANIFEST_FILENAME).write_text(
            json.dumps(self.manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("wrote index of %d chunks to %s", len(self._chunks), directory)

    @classmethod
    def load(cls, directory: Path) -> PolicyIndex:
        index_file = directory / INDEX_FILENAME
        if not index_file.exists():
            raise FileNotFoundError(
                f"no index at {directory} - run `python -m policy_rag.cli ingest` first"
            )
        faiss_index = faiss.read_index(str(index_file))

        chunks: dict[int, Chunk] = {}
        with (directory / CHUNKS_FILENAME).open(encoding="utf-8") as fh:
            for line in fh:
                raw = json.loads(line)
                vector_id = raw.pop("vector_id")
                chunks[vector_id] = Chunk.from_dict(raw)

        manifest = IndexManifest.from_dict(json.loads((directory / MANIFEST_FILENAME).read_text(encoding="utf-8")))
        return cls(faiss_index, chunks, manifest)

    # --- query --------------------------------------------------------------

    def search(self, query_vector: np.ndarray, k: int) -> list[tuple[Chunk, float]]:
        """Return up to `k` `(chunk, cosine_similarity)` pairs, best first."""
        if self._index.ntotal == 0:
            return []
        query = np.ascontiguousarray(query_vector.reshape(1, -1), dtype=np.float32)
        scores, ids = self._index.search(query, min(k, self._index.ntotal))

        results: list[tuple[Chunk, float]] = []
        for score, vector_id in zip(scores[0], ids[0], strict=True):
            if vector_id == -1:
                continue
            chunk = self._chunks.get(int(vector_id))
            if chunk is None:
                # Only reachable if chunks.jsonl and faiss.index drifted apart.
                logger.warning("vector id %s has no chunk metadata; skipping", vector_id)
                continue
            results.append((chunk, float(score)))
        return results

    # --- maintenance --------------------------------------------------------

    def evict_document(self, path: str) -> int:
        """Remove every chunk of one source document from the index.

        This is the vector-layer half of the SDD §4.6 / SLA-04 purge: when a
        policy document is deleted or superseded upstream, its embeddings stop
        being reachable without a full rebuild.
        """
        doomed = [vid for vid, chunk in self._chunks.items() if chunk.path == path]
        if not doomed:
            return 0
        self._index.remove_ids(np.array(doomed, dtype=np.int64))
        for vid in doomed:
            del self._chunks[vid]
        self.manifest.chunk_count = len(self._chunks)
        logger.info("evicted %d chunks for %s", len(doomed), path)
        return len(doomed)

    # --- introspection ------------------------------------------------------

    def __len__(self) -> int:
        return len(self._chunks)

    @property
    def chunks(self) -> Iterable[Chunk]:
        return self._chunks.values()

    def stats(self) -> dict:
        by_corpus: dict[str, int] = {}
        by_type: dict[str, int] = {}
        for chunk in self._chunks.values():
            by_corpus[chunk.corpus_id] = by_corpus.get(chunk.corpus_id, 0) + 1
            by_type[chunk.doc_type] = by_type.get(chunk.doc_type, 0) + 1
        return {
            "chunks": len(self._chunks),
            "vectors": int(self._index.ntotal),
            "by_corpus": by_corpus,
            "by_doc_type": by_type,
            "manifest": self.manifest.to_dict(),
        }
