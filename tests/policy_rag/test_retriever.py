"""Retrieval mechanics: ACL, corpus and doc-type filters, gate, citations.

Retrieval *quality* is out of scope here - these run on the `hash` embedder,
which has no semantic signal. See `scripts/eval_retrieval.py`.
"""

from __future__ import annotations

import pytest

from src.grounding.policy_rag.config import GENERAL_ENTITLEMENT
from src.grounding.policy_rag.documents import Chunk
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


def test_lexical_boost_never_lowers_a_score(retriever, config):
    """Absence of shared vocabulary is not evidence of irrelevance.

    Measured strictly inside the calibration band. At or above `cosine_ceiling`
    the calibrated score is already 1.0 and there is no headroom for the boost
    to act on, so a cosine picked from outside the band would make this pass
    vacuously - which is what happened when the ceiling last moved.
    """
    calibration = config.retrieval
    inside = (calibration.cosine_floor + calibration.cosine_ceiling) / 2

    dense_only = retriever._fuse(inside, 0.0)
    corroborated = retriever._fuse(inside, 0.9)

    assert corroborated > dense_only
    assert dense_only == pytest.approx(retriever._calibrate(inside))


def test_lexical_boost_cannot_lift_a_saturated_score_past_one(retriever, config):
    """The lift is proportional to remaining headroom, so 1.0 is a hard ceiling."""
    at_ceiling = config.retrieval.cosine_ceiling
    assert retriever._fuse(at_ceiling, 1.0) == pytest.approx(1.0)
    assert retriever._fuse(at_ceiling + 0.2, 1.0) == pytest.approx(1.0)


def test_lexical_boost_cannot_carry_a_weak_match_over_the_gate(retriever):
    """A keyword-stuffed but semantically wrong passage must stay below 1.0."""
    assert retriever._fuse(0.0, 1.0) < 1.0


# --- navigational chunks and lexical corroboration ---------------------------


def _chunk(text: str, chunk_id: str = "c-1") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id="d-1",
        corpus_id="okf-handbook",
        path="policies/leave.md",
        doc_title="Leave",
        doc_type="policy",
        authority="governing",
        entitlement=GENERAL_ENTITLEMENT,
        heading_path=["Carryover"],
        anchor="carryover",
        text=text,
        ordinal=0,
    )


def test_a_prose_paragraph_has_no_link_density(retriever):
    prose = (
        "Annual leave accrues at 1.25 days per completed month of service. "
        "Unused days carry over to the following year up to a cap of five."
    )
    assert retriever._compute_link_density(_chunk(prose)) == 0.0


def test_a_section_index_is_almost_all_link(retriever):
    """The shape this rule exists to catch: a heading whose body is a link list."""
    signpost = (
        "- [Annual leave](leave/annual.md)\n"
        "- [Medical leave](leave/medical.md)\n"
        "- [Parental leave](leave/parental.md)\n"
    )
    assert retriever._compute_link_density(_chunk(signpost)) > 0.9


def test_link_density_is_a_fraction_even_for_an_empty_chunk(retriever):
    assert retriever._compute_link_density(_chunk("")) == 0.0
    assert retriever._compute_link_density(_chunk("   \n\n  ")) == 0.0


def test_navigational_chunks_are_never_returned(retriever, config):
    """And the corpus really contains some, so the assertion is not vacuous."""
    densities = [retriever._compute_link_density(c) for c in retriever.index.chunks]
    assert max(densities) > config.retrieval.max_link_density, (
        "no navigational chunk in the fixture corpus - this test proves nothing"
    )

    for hit in _all(retriever, query="where do I find the leave policies"):
        assert retriever._link_density[hit.chunk.chunk_id] <= config.retrieval.max_link_density


def test_an_uncorroborated_hit_is_rejected_rather_than_answered(retriever, config):
    """A hit sharing no vocabulary with the question cannot clear the gate.

    Driven with the gate wide open and the corroboration floor raised above
    everything, so the only reason anything can be rejected is this rule - and
    the rejected hits stay visible for observability rather than vanishing.
    """
    config.retrieval.min_lexical_corroboration = 1.01
    try:
        result = retriever.retrieve(
            RetrievalRequest(query="vacation leave accrual", relevance_gate=0.0, top_k=50)
        )
    finally:
        config.retrieval.min_lexical_corroboration = 0.12

    assert result.hits == []
    assert result.rejected
    # `best_relevance` still reports what was found: refusing is not the same as
    # having seen nothing, and the distinction is what makes a refusal debuggable.
    assert result.best_relevance > 0.0


def test_every_answered_hit_carries_some_corroboration(retriever, config):
    for hit in retriever.retrieve(RetrievalRequest(query="vacation leave accrual")).hits:
        assert hit.lexical_score >= config.retrieval.min_lexical_corroboration


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
