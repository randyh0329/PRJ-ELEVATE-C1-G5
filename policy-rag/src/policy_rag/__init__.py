"""Altostrat HR policy RAG - FAISS retrieval over the handbook and OKF bundle."""

from .answer import Answer
from .config import Config, load_config
from .documents import Chunk, Citation, Document, Hit
from .service import PolicyRagService

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
