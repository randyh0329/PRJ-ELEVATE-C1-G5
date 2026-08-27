"""Dual hybrid grounding package.

Two retrieval backends implement `rag_boilerplate.BaseRAGPipeline`:
`VertexAISearchRAGBoilerplate` (deferred beyond MVP 1) and `FaissPolicyRAG`
(local, working - see `policy_rag/README.md`).

`FaissPolicyRAG` is imported lazily via `__getattr__` so that importing this
package does not pull in faiss, numpy and the embedding stack. Callers that do
not do semantic search should not pay for it.
"""
from typing import Any

from src.grounding.okf_store import OKFPolicyStore, okf_store
from src.grounding.policy_engine import DualGroundingEngine, PolicyQueryResult, dual_grounding_engine
from src.grounding.rag_boilerplate import BaseRAGPipeline, RAGDocumentChunk, VertexAISearchRAGBoilerplate

__all__ = [
    "OKFPolicyStore",
    "okf_store",
    "DualGroundingEngine",
    "PolicyQueryResult",
    "dual_grounding_engine",
    "BaseRAGPipeline",
    "RAGDocumentChunk",
    "VertexAISearchRAGBoilerplate",
    "FaissPolicyRAG",
    "faiss_policy_rag",
]

_LAZY = {"FaissPolicyRAG", "faiss_policy_rag"}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        from src.grounding import faiss_pipeline

        return getattr(faiss_pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
