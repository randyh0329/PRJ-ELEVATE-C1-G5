"""Fixtures for the policy RAG subsystem.

Scoped to this directory rather than merged into `tests/conftest.py`: the names
below (`config`, `index`, `service`) are natural here and ambiguous in a suite
that also covers the HCM, ITSM and Saga agents.

Everything here runs on the `hash` embedding provider so the suite is hermetic:
no model download, no network, deterministic vectors. Retrieval *quality* is not
testable under that provider and is not tested here - that is what
`eval/run_policy_rag_eval.py` and the golden question set are for. These tests
cover the plumbing, the ACL filter and the guards, all of which are
model-independent.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.grounding.policy_rag.config import Config, load_config
from src.grounding.policy_rag.documents import Chunk, SourceRef
from src.grounding.policy_rag.embeddings import build_provider
from src.grounding.policy_rag.index import IndexManifest, PolicyIndex
from src.grounding.policy_rag.ingest import build_chunks, collect_documents
from src.grounding.policy_rag.service import PolicyRagService


@pytest.fixture(scope="session")
def config(tmp_path_factory) -> Config:
    cfg = load_config()
    cfg.embedding.provider = "hash"
    cfg.embedding.model = "hash"
    cfg.index.path = tmp_path_factory.mktemp("index")
    return cfg


@pytest.fixture(scope="session")
def documents(config):
    return collect_documents(config)


@pytest.fixture(scope="session")
def chunks(config, documents):
    built, _ = build_chunks(config, documents)
    return built


@pytest.fixture(scope="session")
def index(config, chunks, documents) -> PolicyIndex:
    embedder = build_provider(config.embedding)
    vectors = embedder.encode([c.embedding_text() for c in chunks])
    manifest = IndexManifest(
        embedder_fingerprint=embedder.fingerprint(),
        dimension=int(vectors.shape[1]),
        index_type=config.index.type,
        chunk_count=len(chunks),
        document_count=len(documents),
        built_at="2026-08-27T00:00:00+00:00",
        corpora={},
        source_digests={},
    )
    return PolicyIndex.build(chunks, np.asarray(vectors, dtype=np.float32), config.index, manifest)


@pytest.fixture(scope="session")
def service(config, index) -> PolicyRagService:
    return PolicyRagService(config, index, build_provider(config.embedding))


def make_chunk(**overrides) -> Chunk:
    """A minimal valid chunk, for tests that need a specific shape.

    A plain helper, not a fixture: `from tests.policy_rag.conftest import make_chunk`.
    """
    base = {
        "chunk_id": "0" * 16,
        "doc_id": "doc",
        "corpus_id": "okf-handbook",
        "path": "okf/altostrat-sg-handbook/leave/vacation.md",
        "doc_title": "Vacation Leave",
        "doc_type": "policy",
        "authority": "governing",
        "entitlement": "general",
        "heading_path": ["Accrual"],
        "anchor": "accrual",
        "text": "Employees accrue 14 days of paid vacation leave per year.",
        "ordinal": 0,
        "tags": ["leave"],
        "status": "stable",
        "stale_after": None,
        "sources": [SourceRef(id="hb-20", title="Handbook Section 20", resource="https://example/hb#20")],
    }
    base.update(overrides)
    return Chunk(**base)
