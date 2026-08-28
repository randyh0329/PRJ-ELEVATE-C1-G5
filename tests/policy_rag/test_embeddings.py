"""The three embedding providers behind one interface.

`local` and `vertex` are driven against stub SDKs. That is not a shortcut: the
whole point of the `hash` provider is that the test suite never downloads a
model or reaches a cloud API, and these two would do both. What is actually
under test is the code around the SDK call - the asymmetric query prefix, the
batch ceiling, the empty-input short circuit and the normalisation - all of
which decide whether a query embedding is comparable to the index it is
searched against.
"""

from __future__ import annotations

import sys
import types as pytypes

import numpy as np
import pytest

from src.grounding.policy_rag.config import EmbeddingConfig
from src.grounding.policy_rag.embeddings import (
    HashEmbeddingProvider,
    LocalEmbeddingProvider,
    VertexEmbeddingProvider,
    _cached_provider,
    build_provider,
    l2_normalise,
)

BGE = "BAAI/bge-small-en-v1.5"
E5 = "intfloat/e5-small-v2"
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@pytest.fixture(autouse=True)
def _clear_provider_cache():
    """`build_provider` memoises on (provider, model, ...); stubbed providers must
    not outlive the test that installed the stub SDK."""
    yield
    _cached_provider.cache_clear()


# --- local (sentence-transformers) --------------------------------------------


class _FakeSentenceTransformer:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.calls: list[tuple[list[str], dict]] = []

    def get_sentence_embedding_dimension(self) -> int:
        return 4

    def encode(self, texts, **kwargs):
        self.calls.append((list(texts), kwargs))
        # float64 on purpose: FAISS needs float32 and the provider must convert.
        return np.array([[1.0, 2.0, 0.0, 0.0]] * len(texts), dtype=np.float64)


@pytest.fixture
def sentence_transformers(monkeypatch):
    module = pytypes.ModuleType("sentence_transformers")
    module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    return module


def test_the_local_provider_reports_the_model_it_loaded(sentence_transformers):
    provider = LocalEmbeddingProvider(BGE)

    assert provider.name == BGE
    assert provider.dimension == 4
    # The fingerprint is what ingest writes into the manifest and what serve
    # compares against; a mismatch there is a silently wrong search.
    assert provider.fingerprint() == f"{BGE}:4"


def test_the_local_provider_returns_float32(sentence_transformers):
    vectors = LocalEmbeddingProvider(BGE).encode(["fourteen days of paid vacation leave"])

    assert vectors.dtype == np.float32
    assert vectors.shape == (1, 4)


def test_encoding_nothing_short_circuits_the_model(sentence_transformers):
    """An empty batch is normal - a corpus filter can remove every candidate -
    and sentence-transformers raises on one."""
    provider = LocalEmbeddingProvider(BGE)

    vectors = provider.encode([])

    assert vectors.shape == (0, 4)
    assert provider._model.calls == []


def test_the_batch_size_and_normalisation_are_passed_through(sentence_transformers):
    provider = LocalEmbeddingProvider(BGE, batch_size=8)

    provider.encode(["a", "b"])

    _texts, kwargs = provider._model.calls[0]
    assert kwargs["batch_size"] == 8
    assert kwargs["normalize_embeddings"] is True
    assert kwargs["convert_to_numpy"] is True
    assert kwargs["show_progress_bar"] is False


def test_an_asymmetric_model_prefixes_the_query_but_not_the_passage(sentence_transformers):
    """bge is trained with an instruction on the query side only. Embedding a
    query without it costs several points of recall, and adding it to passages
    costs more - so the two sides are deliberately not symmetric."""
    provider = LocalEmbeddingProvider(BGE)

    provider.encode(["Employees accrue 14 days."])
    provider.encode_query("how much leave do I get")

    passages, queries = provider._model.calls[0][0], provider._model.calls[1][0]
    assert passages == ["Employees accrue 14 days."]
    assert queries == [f"{BGE_QUERY_PREFIX}how much leave do I get"]


def test_a_model_wanting_both_prefixes_gets_both(sentence_transformers):
    provider = LocalEmbeddingProvider(E5)

    provider.encode(["Employees accrue 14 days."])
    provider.encode_query("how much leave do I get")

    assert provider._model.calls[0][0] == ["passage: Employees accrue 14 days."]
    assert provider._model.calls[1][0] == ["query: how much leave do I get"]


def test_a_model_with_no_declared_prefix_is_left_alone(sentence_transformers):
    provider = LocalEmbeddingProvider("sentence-transformers/all-MiniLM-L6-v2")

    provider.encode_query("how much leave do I get")

    assert provider._model.calls[0][0] == ["how much leave do I get"]


def test_encode_query_returns_one_vector_not_a_matrix(sentence_transformers):
    assert LocalEmbeddingProvider(BGE).encode_query("leave").shape == (4,)


# --- vertex -------------------------------------------------------------------


class _FakeEmbedding:
    def __init__(self, values: list[float]) -> None:
        self.values = values


class _FakeTextEmbeddingModel:
    #: Set by the fixture so a test can inspect the model it did not construct.
    last: _FakeTextEmbeddingModel | None = None

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.batches: list[list[str]] = []

    @classmethod
    def from_pretrained(cls, model_name: str) -> _FakeTextEmbeddingModel:
        cls.last = cls(model_name)
        return cls.last

    def get_embeddings(self, texts: list[str]) -> list[_FakeEmbedding]:
        self.batches.append(list(texts))
        return [_FakeEmbedding([3.0, 4.0, 0.0]) for _ in texts]


@pytest.fixture
def vertexai(monkeypatch):
    initialised: list[dict] = []
    vertexai_module = pytypes.ModuleType("vertexai")
    vertexai_module.init = lambda **kwargs: initialised.append(kwargs)
    language_models = pytypes.ModuleType("vertexai.language_models")
    language_models.TextEmbeddingModel = _FakeTextEmbeddingModel
    vertexai_module.language_models = language_models

    monkeypatch.setitem(sys.modules, "vertexai", vertexai_module)
    monkeypatch.setitem(sys.modules, "vertexai.language_models", language_models)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "elevate-c1-g5")
    monkeypatch.delenv("GOOGLE_CLOUD_LOCATION", raising=False)
    return initialised


def test_vertex_refuses_to_start_without_a_project(vertexai, monkeypatch):
    """Failing here is far cheaper than failing per-query at serve time."""
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT")

    with pytest.raises(RuntimeError, match="needs GOOGLE_CLOUD_PROJECT"):
        VertexEmbeddingProvider("text-embedding-005")


def test_vertex_initialises_the_sdk_and_probes_its_dimension(vertexai):
    """The dimension is discovered, not declared: a config that disagreed with
    the deployed model would build an index FAISS could not search."""
    provider = VertexEmbeddingProvider("text-embedding-005")

    assert vertexai == [{"project": "elevate-c1-g5", "location": "us-central1"}]
    assert provider.dimension == 3
    assert provider.fingerprint() == "text-embedding-005:3"
    assert _FakeTextEmbeddingModel.last.batches == [["dimension probe"]]


def test_vertex_honours_the_configured_location(vertexai, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "asia-southeast1")

    VertexEmbeddingProvider("text-embedding-005")

    assert vertexai[0]["location"] == "asia-southeast1"


def test_vertex_clamps_the_batch_size_to_the_api_ceiling(vertexai):
    """Vertex rejects an oversized request outright, so a config asking for more
    would fail the whole ingest rather than one batch."""
    provider = VertexEmbeddingProvider("text-embedding-005", batch_size=512)

    assert provider._batch_size == VertexEmbeddingProvider.MAX_BATCH


def test_vertex_splits_a_large_corpus_into_batches(vertexai):
    provider = VertexEmbeddingProvider("text-embedding-005", batch_size=2)
    _FakeTextEmbeddingModel.last.batches.clear()

    vectors = provider.encode(["a", "b", "c", "d", "e"])

    assert [len(b) for b in _FakeTextEmbeddingModel.last.batches] == [2, 2, 1]
    assert vectors.shape == (5, 3)


def test_vertex_normalises_so_inner_product_is_cosine(vertexai):
    """FAISS is configured for inner product; unnormalised vectors would make
    every relevance score - and therefore the gate - meaningless."""
    vectors = VertexEmbeddingProvider("text-embedding-005").encode(["anything"])

    assert vectors.dtype == np.float32
    assert np.linalg.norm(vectors[0]) == pytest.approx(1.0)


def test_vertex_encoding_nothing_makes_no_api_call(vertexai):
    provider = VertexEmbeddingProvider("text-embedding-005")
    _FakeTextEmbeddingModel.last.batches.clear()

    assert provider.encode([]).shape == (0, 3)
    assert _FakeTextEmbeddingModel.last.batches == []


# --- normalisation and the hash fixture ---------------------------------------


def test_a_zero_vector_survives_normalisation():
    """A chunk of pure punctuation hashes to nothing; dividing by its norm would
    put NaN into the index and poison every search."""
    normalised = l2_normalise(np.array([[0.0, 0.0], [3.0, 4.0]], dtype=np.float32))

    assert not np.isnan(normalised).any()
    assert np.linalg.norm(normalised[1]) == pytest.approx(1.0)


def test_the_hash_provider_is_deterministic():
    first = HashEmbeddingProvider(64).encode(["fourteen days of paid vacation leave"])
    second = HashEmbeddingProvider(64).encode(["fourteen days of paid vacation leave"])

    assert np.array_equal(first, second)
    assert first.shape == (1, 64)
    assert np.linalg.norm(first[0]) == pytest.approx(1.0)


# --- selection ----------------------------------------------------------------


def test_each_provider_name_builds_its_own_implementation(sentence_transformers, vertexai):
    local = build_provider(EmbeddingConfig(provider="local", model=BGE))
    vertex = build_provider(EmbeddingConfig(provider="vertex", model="text-embedding-005"))
    hashed = build_provider(EmbeddingConfig(provider="hash", model="hash", dimension=64))

    assert isinstance(local, LocalEmbeddingProvider)
    assert isinstance(vertex, VertexEmbeddingProvider)
    assert isinstance(hashed, HashEmbeddingProvider)
    assert hashed.dimension == 64


def test_an_unknown_provider_is_refused():
    with pytest.raises(ValueError, match="unknown embedding provider: 'word2vec'"):
        build_provider(EmbeddingConfig(provider="word2vec", model="none"))


def test_providers_are_cached_so_a_model_loads_once(sentence_transformers):
    """A model load is seconds; doing it per query would blow the SLA-01 budget."""
    cfg = EmbeddingConfig(provider="local", model=BGE)

    assert build_provider(cfg) is build_provider(cfg)
