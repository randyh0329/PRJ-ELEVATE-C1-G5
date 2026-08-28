"""Altostrat HR policy RAG - FAISS retrieval over the handbook and OKF bundle."""
from typing import Any


def __getattr__(name: str) -> Any:
    if name == "Answer":
        from src.grounding.policy_rag.answer import Answer
        return Answer
    if name in ("Config", "load_config"):
        from src.grounding.policy_rag import config
        return getattr(config, name)
    if name in ("Chunk", "Citation", "Document", "Hit"):
        from src.grounding.policy_rag import documents
        return getattr(documents, name)
    if name == "PolicyRagService":
        from src.grounding.policy_rag.service import PolicyRagService
        return PolicyRagService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Answer",
    "Chunk",
    "Citation",
    "Config",
    "Document",
    "Hit",
    "PolicyRagService",
    "load_config",
]

__version__ = "0.1.0"
