"""Altostrat HR policy RAG - FAISS retrieval over the handbook and OKF bundle."""

from src.grounding.policy_rag.answer import Answer
from src.grounding.policy_rag.config import Config, load_config
from src.grounding.policy_rag.documents import Chunk, Citation, Document, Hit
from src.grounding.policy_rag.service import PolicyRagService

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
