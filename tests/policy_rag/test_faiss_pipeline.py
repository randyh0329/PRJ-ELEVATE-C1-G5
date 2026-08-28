"""The `BaseRAGPipeline` adapter in `src/grounding/faiss_pipeline.py`.

These tests are about the *seam*, not about retrieval: whether a caller holding
the shared `BaseRAGPipeline` interface gets well-formed `RAGDocumentChunk`s, a
respected `top_k`, and the ACL filter still applied. Retrieval quality lives in
`eval/run_policy_rag_eval.py`; the layers underneath are covered by the sibling
test modules.

The searching tests run against a gate-0 copy of the service. Under the hermetic
`hash` provider nothing scores above ~0.35, so at the production gate of 0.80
every search returns `[]` and an assertion that no `references/` path leaked
would pass without the ACL filter ever running.
"""

from __future__ import annotations

import copy

import pytest

from src.grounding.faiss_pipeline import FaissPolicyRAG
from src.grounding.policy_rag.config import load_config
from src.grounding.policy_rag.embeddings import build_provider
from src.grounding.policy_rag.service import PolicyRagService
from src.grounding.rag_boilerplate import BaseRAGPipeline, RAGDocumentChunk


@pytest.fixture(scope="module")
def pipeline(config, index) -> FaissPolicyRAG:
    open_gate = copy.deepcopy(config)
    open_gate.retrieval.relevance_gate = 0.0
    ungated = PolicyRagService(open_gate, index, build_provider(open_gate.embedding))
    return FaissPolicyRAG(config=open_gate, service=ungated)


def test_it_satisfies_the_shared_pipeline_contract(pipeline):
    """Interchangeable with the Vertex adapter from a caller's point of view."""
    assert isinstance(pipeline, BaseRAGPipeline)
    assert not getattr(FaissPolicyRAG, "__abstractmethods__", frozenset())


async def test_search_returns_well_formed_chunks(pipeline):
    chunks = await pipeline.semantic_search("vacation leave accrual", top_k=3)
    assert chunks
    for chunk in chunks:
        assert isinstance(chunk, RAGDocumentChunk)
        assert chunk.chunk_id and chunk.content
        assert chunk.document_uri
        assert 0.0 <= chunk.similarity_score <= 1.0
        # Provenance is the whole point of this corpus - a chunk that cannot be
        # cited back to a handbook section is unusable for a grounded answer.
        assert chunk.metadata["path"]
        assert chunk.metadata["corpus_id"]
        assert chunk.metadata["authority"]


async def test_top_k_is_respected(pipeline):
    assert len(await pipeline.semantic_search("leave", top_k=2)) <= 2


async def test_scores_are_ordered(pipeline):
    scores = [c.similarity_score for c in await pipeline.semantic_search("leave", top_k=5)]
    assert scores == sorted(scores, reverse=True)


async def test_the_acl_filter_still_applies_through_the_adapter(pipeline):
    """SDD §4.7: entitlements gate retrieval, whichever interface is used.

    The adapter is a thinner surface than the A2A executor and it would be easy
    to leave the filter behind in it. `references/` is `hr_operational`.
    """
    general = await pipeline.semantic_search("source defect register", top_k=10)
    assert general
    assert all("references/" not in c.metadata["path"] for c in general)

    elevated = await pipeline.semantic_search(
        "source defect register", top_k=10, entitlements=["general", "hr_operational"]
    )
    assert any("references/" in c.metadata["path"] for c in elevated)


async def test_the_gate_turns_a_weak_match_into_no_hits(config, index):
    """An empty list is the refusal signal (BRD FR-5.4), not an error.

    This is the same service at the *production* gate. No hash-provider score
    clears 0.80, so every query comes back empty - which is what the caller must
    read as "the corpus has nothing good enough", rather than a failure.
    """
    gated = PolicyRagService(config, index, build_provider(config.embedding))
    pipeline = FaissPolicyRAG(config=config, service=gated)
    assert config.retrieval.relevance_gate >= 0.8
    assert await pipeline.semantic_search("vacation leave accrual") == []


def test_is_ready_reports_false_instead_of_raising(tmp_path, config):
    """A router asking "can I use semantic search?" must not take an exception."""
    missing = copy.deepcopy(config)
    missing.index.path = tmp_path / "nonexistent"
    assert FaissPolicyRAG(config=missing).is_ready is False


def test_is_ready_is_true_for_a_loaded_index(pipeline):
    assert pipeline.is_ready is True


async def test_index_documents_rejects_an_undeclared_corpus(pipeline):
    """Nothing may introduce a corpus at runtime - it has to be in the config.

    The check runs before any embedding work, so this test never builds an index.
    """
    with pytest.raises(ValueError, match="undeclared corpus"):
        await pipeline.index_documents(["gs://some-bucket/handbook.pdf"])


@pytest.fixture
def rebuildable(config, index, monkeypatch):
    """A pipeline whose `ingest` is recorded rather than run.

    Function-scoped and separate from `pipeline`: `index_documents` drops the
    cached service so the next access rebuilds it, which would leave the shared
    module-scoped fixture reloading a real index from disk.
    """
    from src.grounding.policy_rag import ingest as ingest_module

    calls: list = []
    monkeypatch.setattr(ingest_module, "ingest", calls.append)
    pipe = FaissPolicyRAG(
        config=config, service=PolicyRagService(config, index, build_provider(config.embedding))
    )
    return pipe, calls


async def test_naming_every_declared_corpus_rebuilds_the_index(rebuildable, config):
    pipe, calls = rebuildable

    assert await pipe.index_documents([c.id for c in config.corpora]) is True
    assert calls == [config]


async def test_an_empty_request_rebuilds_everything(rebuildable, config):
    """No ids named is "rebuild the index", the only whole-artefact operation
    this pipeline has."""
    pipe, calls = rebuildable

    assert await pipe.index_documents([]) is True
    assert calls == [config]


async def test_naming_a_subset_still_rebuilds_the_whole_index(rebuildable, config, caplog):
    """Building only `handbook` would *evict* the OKF bundle rather than refresh
    one corpus in place, so a partial request is widened - and said so."""
    pipe, calls = rebuildable
    subset = [config.corpora[0].id]
    assert len(config.corpora) > 1

    with caplog.at_level("INFO", logger="grounding.faiss_pipeline"):
        await pipe.index_documents(subset)

    assert calls == [config]
    assert "rebuilding all of" in caplog.text


async def test_a_rebuild_drops_the_cached_service(rebuildable):
    """The old service holds the pre-rebuild index in memory; keeping it would
    serve stale retrieval for the rest of the process's life."""
    pipe, _ = rebuildable

    await pipe.index_documents([])

    assert pipe._service is None


async def test_a_pipeline_given_a_config_path_loads_it_before_rebuilding(monkeypatch, tmp_path):
    """`FaissPolicyRAG(config=...)` also accepts a path, as `load_config` does."""
    from src.grounding.policy_rag import config as config_module
    from src.grounding.policy_rag import ingest as ingest_module

    loaded = load_config()
    monkeypatch.setattr(config_module, "load_config", lambda path=None: loaded)
    calls: list = []
    monkeypatch.setattr(ingest_module, "ingest", calls.append)

    pipe = FaissPolicyRAG(config=str(tmp_path / "corpus.yaml"))
    await pipe.index_documents([])

    assert calls == [loaded]


def test_the_package_exports_the_pipeline_lazily():
    """`from src.grounding import FaissPolicyRAG` works without eager faiss import."""
    from src import grounding

    assert grounding.FaissPolicyRAG is FaissPolicyRAG
    with pytest.raises(AttributeError):
        _ = grounding.NoSuchPipeline
