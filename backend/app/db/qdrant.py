"""Qdrant client connection and collection helpers for vector storage used in RAG."""

# Collections (Qdrant):
#   reports  — embedded past PPT report chunks for WoW RAG comparison
#   domain   — embedded domain knowledge documents for context_agent

# TODO: initialise QdrantClient with QDRANT_URL from config
# TODO: expose get_qdrant_client() and ensure_collection(name, vector_size) helpers

from qdrant_client import QdrantClient  # qdrant-client

qdrant_client: QdrantClient | None = None  # Placeholder — replace with QdrantClient instance


def get_qdrant_client() -> QdrantClient:
    # Placeholder — implementation pending
    raise NotImplementedError
