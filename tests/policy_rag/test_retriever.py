"""Retrieval mechanics: ACL, corpus and doc-type filters, gate, citations.

Retrieval *quality* is out of scope here - these run on the `hash` embedder,
which has no semantic signal. See `scripts/eval_retrieval.py`.
"""

from __future__ import annotations

import pytest

from src.grounding.policy_rag.config import GENERAL_ENTITLEMENT
from src.grounding.policy_rag.embeddings import build_provider
from src.grounding.policy_rag.index import PolicyIndex
from src.grounding.policy_rag.retriever import RetrievalRequest, Retriever, tokenize


@pytest.fixture(scope="module")
def retriever(config, index):
    return Retriever(config, index, build_provider(config.embedding))


def _all(retriever, **kwargs):
    """Retrieve with the gate open, so filter behaviour is what is under test."""
    kwargs.setdefault("relevance_gate", 0.0)
    kwargs.setdefault("top_k", 50)
    return retriever.retrieve(RetrievalRequest(**kwargs)).hits


# --- entitlements (SDD §4.7) ------------------------------------------------


def test_general_caller_never_sees_hr_operational_chunks(retriever):
    hits = _all(retriever, query="source defect register conflicts", entitlements=[GENERAL_ENTITLEMENT])
    assert all(h.chunk.entitlement == GENERAL_ENTITLEMENT for h in hits)
    assert not any("references/" in h.chunk.path for h in hits)


def test_hr_operational_caller_can_reach_the_register(retriever):
    hits = _all(
        retriever,
        query="source defect register conflicts",
        entitlements=[GENERAL_ENTITLEMENT, "hr_operational"],
        doc_types=["policy", "reference", "datasheet"],
    )
    assert any("references/" in h.chunk.path for h in hits)


def test_empty_entitlement_list_falls_back_to_general_not_to_everything(retriever):
    hits = _all(retriever, query="vacation leave accrual", entitlements=[])
    assert hits
    assert all(h.chunk.entitlement == GENERAL_ENTITLEMENT for h in hits)


# --- corpus and doc-type filters --------------------------------------------


def test_default_search_excludes_the_raw_handbook(retriever):
    """The OKF bundle governs; the raw handbook has the unresolved two-layer split."""
    hits = _all(retriever, query="vacation leave accrual entitlement")
    assert hits
    assert all(h.chunk.corpus_id == "okf-handbook" for h in hits)


def test_raw_handbook_is_reachable_when_named(retriever):
    hits = _all(retriever, query="vacation leave accrual entitlement", corpora=["handbook-source"], doc_types=["handbook"])
    assert hits
    assert all(h.chunk.corpus_id == "handbook-source" for h in hits)


def test_nav_pages_are_excluded_by_default(retriever):
    hits = _all(retriever, query="leave index routing")
    assert all(h.chunk.doc_type != "nav" for h in hits)


# --- gate and ranking --------------------------------------------------------


def test_gate_rejects_below_threshold(retriever):
    result = retriever.retrieve(RetrievalRequest(query="vacation leave", relevance_gate=1.01))
    assert result.hits == []
    assert not result.passed_gate
    assert result.rejected, "rejected hits are retained for observability"


def test_relevance_is_bounded(retriever):
    for hit in _all(retriever, query="vacation leave accrual"):
        assert 0.0 <= hit.relevance <= 1.0


def test_max_chunks_per_document_is_enforced(config, retriever):
    hits = retriever.retrieve(
        RetrievalRequest(query="vacation leave accrual carryover", relevance_gate=0.0, top_k=50)
    ).hits
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit.chunk.doc_id] = counts.get(hit.chunk.doc_id, 0) + 1
    assert max(counts.values()) <= config.retrieval.max_chunks_per_document


def test_lexical_boost_never_lowers_a_score(retriever):
    """Absence of shared vocabulary is not evidence of irrelevance."""
    dense_only = retriever._fuse(0.70, 0.0)
    corroborated = retriever._fuse(0.70, 0.9)
    assert corroborated > dense_only
    assert retriever._fuse(0.70, 0.0) == pytest.approx(retriever._calibrate(0.70))


def test_lexical_boost_cannot_carry_a_weak_match_over_the_gate(retriever):
    """A keyword-stuffed but semantically wrong passage must stay below 1.0."""
    assert retriever._fuse(0.0, 1.0) < 1.0


# --- citations (FR-5.3 / FR-5.4) --------------------------------------------


def test_every_returned_hit_has_a_resolvable_citation(retriever):
    for hit in _all(retriever, query="vacation leave accrual"):
        assert hit.citation.resolved, f"unresolvable citation survived: {hit.citation.uri}"


def test_citation_points_at_a_real_anchor(config, retriever):
    for hit in _all(retriever, query="sick leave medical certificate"):
        path, _, anchor = hit.citation.uri.partition("#")
        assert (config.repo_root / path).is_file()
        if anchor:
            assert anchor == hit.chunk.anchor


# --- fingerprint safety ------------------------------------------------------


def test_embedder_mismatch_is_fatal(config, index):
    """A query embedded by a different model than the index is silently wrong."""

    class Impostor:
        name, dimension = "not-the-index-model", 384

        def fingerprint(self):
            return "not-the-index-model:384"

    with pytest.raises(RuntimeError, match="index was built with embedder"):
        Retriever(config, index, Impostor())


def test_index_roundtrips(config, index, tmp_path):
    index.save(tmp_path / "idx")
    reloaded = PolicyIndex.load(tmp_path / "idx")
    assert len(reloaded.chunks) == len(index.chunks)
    assert reloaded.manifest.embedder_fingerprint == index.manifest.embedder_fingerprint


def test_evict_document_removes_its_vectors(config, chunks, index, tmp_path):
    """SLA-04: a superseded document's embeddings must not outlive it."""
    index.save(tmp_path / "idx")
    working = PolicyIndex.load(tmp_path / "idx")
    path = "okf/altostrat-sg-handbook/leave/vacation.md"
    before = len(working.chunks)
    removed = working.evict_document(path)
    assert removed > 0
    assert len(working.chunks) == before - removed
    assert not any(c.path == path for c in working.chunks)


def test_tokenize_drops_stopwords_but_keeps_figures():
    terms = tokenize("How many days is the US$100 limit in Section 20?")
    assert "us$100" in terms
    assert "20" in terms
    assert "the" not in terms
    assert "how" not in terms
