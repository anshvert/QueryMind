"""
QueryMind — Qdrant Vector DB Client (async)
"""
from qdrant_client import AsyncQdrantClient
from backend.core.config import settings

_qdrant_client: AsyncQdrantClient | None = None


def get_qdrant() -> AsyncQdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = AsyncQdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY or None,
        )
    return _qdrant_client
