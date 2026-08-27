"""Embedding providers.

Three implementations behind one interface:

* ``local``  - sentence-transformers on CPU. The default: no cloud credentials,
               no per-query cost, good enough for a corpus this size.
* ``vertex`` - Vertex AI text embeddings, for parity with the SDD target
               platform when this service runs on GCP.
* ``hash``   - deterministic hashed character n-grams. No model download, so CI
               and unit tests stay hermetic. Retrieval quality is poor; it is a
               plumbing fixture, not a fallback for production.

Every provider returns L2-normalised float32 vectors, so FAISS inner product is
cosine similarity.
"""

from __future__ import annotations

import hashlib
import logging
import re
from abc import ABC, abstractmethod
from functools import lru_cache

import numpy as np

from src.grounding.policy_rag.config import EmbeddingConfig

logger = logging.getLogger(__name__)


def l2_normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class EmbeddingProvider(ABC):
    """Produces normalised embeddings for a batch of texts."""

    name: str
    dimension: int

    @abstractmethod
    def encode(self, texts: list[str]) -> np.ndarray:
        """Return an `(len(texts), dimension)` float32 array of unit vectors."""

    def encode_query(self, text: str) -> np.ndarray:
        return self.encode([text])[0]

    def fingerprint(self) -> str:
        """Identity written into the index manifest.

        A query embedded by a different model than the index was built with
        produces silently wrong results, so ingest and serve compare this.
        """
        return f"{self.name}:{self.dimension}"


#: Asymmetric models are trained with an instruction on the query side only.
#: Embedding a query without its prefix costs several points of recall, and the
#: prefix is a property of the checkpoint, so it lives here rather than in config.
_QUERY_PREFIXES: dict[str, str] = {
    "BAAI/bge-small-en-v1.5": "Represent this sentence for searching relevant passages: ",
    "BAAI/bge-base-en-v1.5": "Represent this sentence for searching relevant passages: ",
    "BAAI/bge-large-en-v1.5": "Represent this sentence for searching relevant passages: ",
    "intfloat/e5-small-v2": "query: ",
    "intfloat/e5-base-v2": "query: ",
}
#: Document-side prefix, for the models that want one on both sides.
_PASSAGE_PREFIXES: dict[str, str] = {
    "intfloat/e5-small-v2": "passage: ",
    "intfloat/e5-base-v2": "passage: ",
}


class LocalEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str, batch_size: int = 64) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError(
                "provider 'local' needs sentence-transformers: pip install -e '.[local-embeddings]'"
            ) from exc
        self.name = model_name
        self._batch_size = batch_size
        self._model = SentenceTransformer(model_name)
        self.dimension = int(self._model.get_sentence_embedding_dimension())
        self._query_prefix = _QUERY_PREFIXES.get(model_name, "")
        self._passage_prefix = _PASSAGE_PREFIXES.get(model_name, "")

    def _encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._passage_prefix:
            texts = [f"{self._passage_prefix}{t}" for t in texts]
        return self._encode(texts)

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode([f"{self._query_prefix}{text}"])[0]


class VertexEmbeddingProvider(EmbeddingProvider):
    """Vertex AI text embeddings.

    Requires `google-cloud-aiplatform` and application default credentials;
    reads `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` from the environment.
    """

    #: Vertex rejects oversized batches; 250 is the documented instance ceiling.
    MAX_BATCH = 100

    def __init__(self, model_name: str, batch_size: int = 64) -> None:
        try:
            import vertexai
            from vertexai.language_models import TextEmbeddingModel
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError(
                "provider 'vertex' needs google-cloud-aiplatform: pip install google-cloud-aiplatform"
            ) from exc
        import os

        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
        if not project:
            raise RuntimeError("provider 'vertex' needs GOOGLE_CLOUD_PROJECT to be set")
        vertexai.init(project=project, location=location)

        self.name = model_name
        self._batch_size = min(batch_size, self.MAX_BATCH)
        self._model = TextEmbeddingModel.from_pretrained(model_name)
        probe = self._model.get_embeddings(["dimension probe"])
        self.dimension = len(probe[0].values)

    def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dimension), dtype=np.float32)
        rows: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            rows.extend(e.values for e in self._model.get_embeddings(batch))
        return l2_normalise(np.asarray(rows, dtype=np.float32))


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic hashed word + character trigram bag.

    Enough signal for exact-term matches, which is all the hermetic tests need.
    """

    _TOKEN_RE = re.compile(r"[a-z0-9]+")

    def __init__(self, dimension: int = 384) -> None:
        self.name = f"hash-{dimension}"
        self.dimension = dimension

    def _features(self, text: str) -> list[str]:
        tokens = self._TOKEN_RE.findall(text.lower())
        features = list(tokens)
        joined = " ".join(tokens)
        features.extend(joined[i : i + 3] for i in range(0, max(0, len(joined) - 2)))
        return features

    def encode(self, texts: list[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for feature in self._features(text):
                digest = hashlib.md5(feature.encode("utf-8")).digest()
                bucket = int.from_bytes(digest[:4], "big") % self.dimension
                sign = 1.0 if digest[4] & 1 else -1.0
                matrix[row, bucket] += sign
        return l2_normalise(matrix)


@lru_cache(maxsize=4)
def _cached_provider(provider: str, model: str, dimension: int, batch_size: int) -> EmbeddingProvider:
    if provider == "local":
        return LocalEmbeddingProvider(model, batch_size)
    if provider == "vertex":
        return VertexEmbeddingProvider(model, batch_size)
    if provider == "hash":
        return HashEmbeddingProvider(dimension)
    raise ValueError(f"unknown embedding provider: {provider!r}")


def build_provider(cfg: EmbeddingConfig) -> EmbeddingProvider:
    """Instantiate the configured provider (cached - model loads are expensive)."""
    logger.info("loading embedding provider %s (%s)", cfg.provider, cfg.model)
    return _cached_provider(cfg.provider, cfg.model, cfg.dimension, cfg.batch_size)
