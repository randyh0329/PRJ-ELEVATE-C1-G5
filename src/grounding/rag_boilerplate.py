"""Boilerplate interface for future Vertex AI Search and Vector RAG pipeline."""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class RAGDocumentChunk(BaseModel):
    """Chunk of unstructured document retrieved via semantic RAG."""
    chunk_id: str
    content: str
    document_uri: str
    similarity_score: float
    metadata: Dict[str, Any] = {}


class BaseRAGPipeline(ABC):
    """Abstract interface for RAG vector search and index operations."""

    @abstractmethod
    async def index_documents(self, gcs_uris: List[str]) -> bool:
        """Ingest and index unstructured PDF/Word handbooks from Cloud Storage."""
        pass

    @abstractmethod
    async def semantic_search(self, query: str, top_k: int = 5) -> List[RAGDocumentChunk]:
        """Perform semantic dense retrieval over the indexed document embeddings."""
        pass


class VertexAISearchRAGBoilerplate(BaseRAGPipeline):
    """Production boilerplate adapter for Google Cloud Vertex AI Search (Discovery Engine)."""

    def __init__(self, datastore_id: Optional[str] = None, project_id: Optional[str] = None) -> None:
        self.datastore_id = datastore_id or "projects/default/locations/global/collections/default_collection/dataStores/hr-handbook"
        self.project_id = project_id

    async def index_documents(self, gcs_uris: List[str]) -> bool:
        """Boilerplate: Trigger Google Cloud Vertex AI Search document ingestion pipeline."""
        # In production:
        # from google.cloud import discoveryengine_v1
        # client = discoveryengine_v1.DocumentServiceClient()
        # client.import_documents(request={...})
        raise NotImplementedError("Vertex AI Search ingestion pipeline is deferred beyond MVP 1 baseline.")

    async def semantic_search(self, query: str, top_k: int = 5) -> List[RAGDocumentChunk]:
        """Boilerplate: Query Vertex AI Search unstructured datastore."""
        # In production:
        # from google.cloud import discoveryengine_v1
        # client = discoveryengine_v1.SearchServiceClient()
        # response = client.search(...)
        raise NotImplementedError("Vertex AI Search semantic query is deferred beyond MVP 1 baseline.")
