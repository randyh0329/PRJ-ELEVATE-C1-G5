"""`PolicyIndex`: the FAISS store and the chunk metadata that makes hits citable.

The index is an `IndexIDMap2` keyed on ids derived from the content-addressed
chunk id, which buys two things the SDD depends on: a rebuild produces identical
labels, and `remove_ids` makes the SLA-04 stale-embedding eviction possible
without a full rebuild. Both are asserted below, along with the guards that stop
a malformed index being constructed at all.
"""

from __future__ import annotations

import re

import faiss
import numpy as np
import pytest

from src.grounding.policy_rag.config import IndexConfig
from src.grounding.policy_rag.index import IndexManifest, PolicyIndex
from tests.policy_rag.conftest import make_chunk

FLAT = IndexConfig(type="flat")


def _manifest(**overrides) -> IndexManifest:
    base = {
        "embedder_fingerprint": "hash:4",
        "dimension": 4,
        "index_type": "flat",
        "chunk_count": 0,
        "document_count": 0,
        "built_at": "2026-08-27T00:00:00+00:00",
        "corpora": {},
        "source_digests": {},
    }
    base.update(overrides)
    return IndexManifest(**base)


def _chunks() -> list:
    return [
        make_chunk(chunk_id="a" * 16, text="Fourteen days of paid vacation leave per year."),
        make_chunk(
            chunk_id="b" * 16,
            path="okf/altostrat-sg-handbook/leave/sick-and-hospitalisation.md",
            doc_title="Sick Leave",
            text="Fourteen days of outpatient sick leave per year.",
        ),
    ]


VECTORS = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]], dtype=np.float32)


def _index(chunks=None, vectors=None, cfg: IndexConfig = FLAT) -> PolicyIndex:
    chunks = _chunks() if chunks is None else chunks
    vectors = VECTORS if vectors is None else vectors
    return PolicyIndex.build(chunks, vectors, cfg, _manifest(chunk_count=len(chunks)))


# --- construction -------------------------------------------------------------


def test_a_flat_index_holds_every_chunk():
    index = _index()

    assert len(index) == 2
    assert {c.chunk_id for c in index.chunks} == {"a" * 16, "b" * 16}


def test_an_hnsw_index_is_available_for_a_corpus_that_outgrows_flat():
    index = _index(cfg=IndexConfig(type="hnsw", hnsw_m=8))

    assert len(index) == 2
    assert index.stats()["vectors"] == 2


def test_an_unknown_index_type_is_refused():
    """A typo in `corpus.yaml` must fail the build rather than pick a default -
    `flat` and `hnsw` have different recall, and silently swapping one for the
    other would change every retrieval score."""
    with pytest.raises(ValueError, match="unknown index type: 'annoy'"):
        _index(cfg=IndexConfig(type="annoy"))


def test_a_chunk_vector_count_mismatch_is_refused():
    """Chunks and vectors are zipped by position; off by one and every citation
    points at the wrong passage."""
    with pytest.raises(ValueError, match="chunk/vector count mismatch: 2 vs 1"):
        _index(vectors=VECTORS[:1])


def test_an_empty_index_is_refused():
    with pytest.raises(ValueError, match="refusing to build an empty index"):
        _index(chunks=[], vectors=np.zeros((0, 4), dtype=np.float32))


def test_duplicate_vector_ids_are_refused():
    """Two chunks sharing an id means the second overwrites the first in FAISS -
    a policy paragraph missing from retrieval with nothing to show for it."""
    twins = [make_chunk(chunk_id="a" * 16), make_chunk(chunk_id="a" * 16, text="Different text.")]

    with pytest.raises(ValueError, match="duplicate vector ids"):
        _index(chunks=twins)


def test_vector_ids_are_derived_from_the_chunk_id():
    """Deterministic labels are what make two builds of the same corpus diffable.

    FAISS labels are signed int64, so the top bit of the hash is masked off.
    """
    index = _index()

    mask = 0x7FFF_FFFF_FFFF_FFFF
    assert {c.vector_id for c in index.chunks} == {int("a" * 16, 16) & mask, int("b" * 16, 16) & mask}


# --- persistence --------------------------------------------------------------


def test_an_index_round_trips_through_disk(tmp_path):
    original = _index()
    original.save(tmp_path / "index")

    reloaded = PolicyIndex.load(tmp_path / "index")

    assert len(reloaded) == 2
    assert reloaded.manifest.embedder_fingerprint == "hash:4"
    restored = next(c for c in reloaded.chunks if c.chunk_id == "b" * 16)
    assert restored.doc_title == "Sick Leave"
    assert [s.id for s in restored.sources] == ["hb-20"]
    # The vectors survive too, not just the metadata.
    assert reloaded.search(VECTORS[1], k=1)[0][0].chunk_id == "b" * 16


def test_saving_creates_the_directory(tmp_path):
    _index().save(tmp_path / "nested" / "index")

    assert (tmp_path / "nested" / "index" / "faiss.index").is_file()
    assert (tmp_path / "nested" / "index" / "chunks.jsonl").is_file()
    assert (tmp_path / "nested" / "index" / "manifest.json").is_file()


def test_loading_a_directory_with_no_index_says_how_to_build_one(tmp_path):
    with pytest.raises(FileNotFoundError, match=re.escape("run `python -m policy_rag.cli ingest` first")):
        PolicyIndex.load(tmp_path / "missing")


# --- query --------------------------------------------------------------------


def test_search_returns_chunks_best_first():
    index = _index()
    query = np.array([0.9, 0.44, 0.0, 0.0], dtype=np.float32)

    hits = index.search(query, k=2)

    assert [c.chunk_id for c, _ in hits] == ["a" * 16, "b" * 16]
    assert hits[0][1] > hits[1][1]


def test_k_is_clamped_to_what_the_index_holds():
    assert len(_index().search(VECTORS[0], k=50)) == 2


def test_searching_an_empty_index_returns_nothing_rather_than_raising():
    """`ntotal == 0` is reachable after evicting the last document; a caller must
    read it as "no match", not as a broken index."""
    empty = PolicyIndex(faiss.IndexIDMap2(faiss.IndexFlatIP(4)), {}, _manifest())

    assert empty.search(VECTORS[0], k=5) == []


class _StubIndex:
    """A FAISS index whose result row is not all real hits.

    FAISS pads a short result row with `-1`, and a row can name an id that
    `chunks.jsonl` does not carry if the two files drift apart. Neither is
    producible from a well-formed index, which is the point of stubbing it.
    """

    def __init__(self, ids: list[int]) -> None:
        self.ntotal = len(ids)
        self._ids = ids

    def search(self, query: np.ndarray, k: int):
        scores = np.array([[0.9] * len(self._ids)], dtype=np.float32)
        return scores, np.array([self._ids], dtype=np.int64)


def test_padding_ids_are_not_returned_as_hits():
    chunk = make_chunk()
    index = PolicyIndex(_StubIndex([chunk.vector_id, -1, -1]), {chunk.vector_id: chunk}, _manifest())

    assert [c.chunk_id for c, _ in index.search(VECTORS[0], k=3)] == [chunk.chunk_id]


def test_a_vector_with_no_chunk_metadata_is_skipped_and_logged(caplog):
    """Returning it would produce a hit with no text and no citation - worse than
    one fewer result, because the answer composer would cite nothing."""
    chunk = make_chunk()
    index = PolicyIndex(_StubIndex([chunk.vector_id, 424242]), {chunk.vector_id: chunk}, _manifest())

    with caplog.at_level("WARNING", logger="src.grounding.policy_rag.index"):
        hits = index.search(VECTORS[0], k=2)

    assert len(hits) == 1
    assert "no chunk metadata" in caplog.text


# --- maintenance --------------------------------------------------------------


def test_evicting_a_document_removes_its_chunks_from_the_index():
    """SLA-04: a superseded policy stops being retrievable without a rebuild."""
    index = _index()
    doomed = "okf/altostrat-sg-handbook/leave/vacation.md"

    assert index.evict_document(doomed) == 1

    assert len(index) == 1
    assert index.manifest.chunk_count == 1
    assert index.stats()["vectors"] == 1
    assert all(c.path != doomed for c in index.chunks)
    assert index.search(VECTORS[0], k=2)[0][0].chunk_id == "b" * 16


def test_evicting_a_path_the_index_does_not_hold_changes_nothing():
    index = _index()

    assert index.evict_document("okf/altostrat-sg-handbook/leave/nonexistent.md") == 0
    assert len(index) == 2


# --- introspection ------------------------------------------------------------


def test_stats_break_the_corpus_down_by_source_and_type():
    index = _index()

    stats = index.stats()

    assert stats["chunks"] == 2
    assert stats["vectors"] == 2
    assert stats["by_corpus"] == {"okf-handbook": 2}
    assert stats["by_doc_type"] == {"policy": 2}
    assert stats["manifest"]["embedder_fingerprint"] == "hash:4"


def test_the_manifest_round_trips_through_a_plain_dict():
    manifest = _manifest(corpora={"okf-handbook": 7}, source_digests={"a.md": "deadbeef"})

    assert IndexManifest.from_dict(manifest.to_dict()) == manifest
